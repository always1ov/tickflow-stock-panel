"""[fork 增强] R117 外部网页 → 固定版式数据: 抓原文, 再让**面板自己的 AI**
把它整理成一份固定结构的 JSON。

链路: `external_fetch.fetch()` 抓原文 → 这里清洗压缩 → AI(走 ai_provider 的
档位链, 与全站同一套 Key) → `extract_json_object` 容错解析 → `normalize_spec`
按固定契约收敛 → 前端固定版式渲染。

设计要点:
  - **用户不写代码**。想要什么由一句大白话说明(hint)控制, 其余交给提示词。
  - **结果要缓存**。AI 调用有钱有延迟, 同一份原文不重复解析: 缓存键 =
    URL + 原文哈希, 原文没变就一直用旧结果, 想强制重来走 force。
  - **契约在服务端定死**。AI 的输出永远当不可信数据: 字段缺了补默认、类型不对
    就丢、行列都有上限, 绝不把 AI 返回的东西直接塞给前端。
  - 不进能力路由矩阵、不落数据湖 —— 这是「看一眼」的展示数据, 不是 A 股行情。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# 送 AI 的原文上限: 太长既贵又容易让模型跑偏。整页新闻站点会被截断, 这是
# 有意的 —— 抓取模式的定位是数据接口 / 榜单小页面。
MAX_SOURCE_CHARS = 12000

MAX_ROWS = 300          # 单张表行数上限(AI 抄不动更多, 界面也不需要)
MAX_COLUMNS = 20
MAX_SECTIONS = 6
MAX_STATS = 12
MAX_NOTES = 10

_TONES = {"up", "down", "flat", "plain", "delta"}
_ALIGNS = {"left", "right", "center"}

_DROP_TAGS = re.compile(
    r"<(script|style|noscript|svg|iframe|canvas|template)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_ATTRS = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


SYSTEM_PROMPT = """你是一个把网页原文整理成结构化数据的工具。你只输出 JSON,不输出任何解释、思考过程或代码块围栏,第一个字符必须是 {。

输出结构(字段固定,只能用下面列出的字段):
{
  "title": "这份数据叫什么(短标题)",
  "subtitle": "可选,一句话补充",
  "updated_at": "可选,原文里写明的数据时间,原样抄,没有就省略",
  "stats": [ {"label":"指标名","value":"数值或文本","hint":"可选备注","tone":"up|down|flat|plain"} ],
  "sections": [ {
      "title": "这张表叫什么",
      "columns": [ {"key":"字段名(英文或拼音,行里用它取值)","label":"列头中文","align":"left|right|center","tone":"plain|delta","unit":"可选单位如 %"} ],
      "rows": [ {"字段名": 值, ...} ]
  } ],
  "notes": ["可选,补充说明,每条一句话"]
}

规则:
1. 只搬运原文里**真实存在**的数据。原文没有的数字绝对不要编,宁可少给字段。
2. 数值一律用 JSON 数字(3.25),不要写成字符串("3.25%")。百分号、单位放到列的 unit 里。
3. 涨跌幅这类有正负含义的列,tone 写 "delta",界面会按正负染成红涨绿跌。
4. rows 里每个对象的键必须来自同一张表的 columns[].key,不要多也不要少。
5. 一张表最多 @MAX_ROWS@ 行;最多 @MAX_SECTIONS@ 张表;stats 最多 @MAX_STATS@ 个。数据更多时只取最重要的部分,并在 notes 里说明"原文还有更多,已截取前 N 条"。
6. 原文如果是一个数据接口(JSON),直接按它的字段整理;如果是网页,只挑正文里的表格/榜单/关键指标,忽略导航、广告、页脚。
7. 如果原文里根本没有可结构化的数据(比如抓回来是登录页、报错页、或纯 JS 壳子),就返回 {"title":"...","notes":["说明为什么没有数据"]},不要硬编。
"""
# 提示词里出现大量 % 与 {}, 用占位符替换而不是 %/format 拼接
SYSTEM_PROMPT = (SYSTEM_PROMPT
                 .replace("@MAX_ROWS@", str(MAX_ROWS))
                 .replace("@MAX_SECTIONS@", str(MAX_SECTIONS))
                 .replace("@MAX_STATS@", str(MAX_STATS)))


def clean_source(text: str, content_type: str = "", limit: int = MAX_SOURCE_CHARS) -> str:
    """把抓回来的原文压成适合喂 AI 的形态(纯函数)。

    JSON 原样保留(结构本身就是信息); HTML 去掉脚本/样式/注释与全部属性, 只留
    标签骨架和文字 —— 保留标签是为了让模型看得出哪些是表格行列。
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    looks_json = "json" in content_type.lower() or raw[:1] in "[{"
    if looks_json:
        try:
            parsed = json.loads(raw)
            raw = json.dumps(parsed, ensure_ascii=False, indent=1)
        except (ValueError, TypeError):
            pass
    else:
        raw = _DROP_TAGS.sub(" ", raw)
        raw = _COMMENTS.sub(" ", raw)
        raw = _ATTRS.sub(r"<\1>", raw)      # 扔掉全部属性(class/style/onclick…)
        raw = _WS.sub(" ", raw)
        raw = _BLANK_LINES.sub("\n", raw)
        raw = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
    if len(raw) > limit:
        raw = raw[:limit] + f"\n…(原文超过 {limit} 字, 已截断)"
    return raw


def build_messages(source: str, url: str, hint: str = "") -> list[dict]:
    """组装送 AI 的消息。hint 是用户的大白话要求, 放在最前面提高权重。"""
    want = (hint or "").strip()
    user = (
        (f"用户想从这个页面里看到的是: {want}\n\n" if want else "")
        + f"页面地址: {url}\n"
        + "页面原文如下(已做清洗):\n"
        + "-----\n"
        + source
        + "\n-----\n"
        + "请按系统提示里的固定结构输出 JSON。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _text(v: Any) -> str:
    if v is None or isinstance(v, (dict, list)):
        return "" if v is None else json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "是" if v else "否"
    return str(v)


def _norm_columns(raw: Any, rows: list[dict]) -> list[dict]:
    cols: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if len(cols) >= MAX_COLUMNS:
            break
        if isinstance(item, str):
            item = {"key": item}
        if not isinstance(item, dict):
            continue
        key = _text(item.get("key") or item.get("field") or item.get("name")).strip()
        if not key:
            continue
        align = item.get("align") if item.get("align") in _ALIGNS else None
        first = rows[0].get(key) if rows else None
        cols.append({
            "key": key,
            "label": _text(item.get("label") or item.get("title")).strip() or key,
            # 没指定对齐时数值列右对齐 —— 表格里读数要对得上位
            "align": align or ("right" if isinstance(first, (int, float)) and not isinstance(first, bool) else "left"),
            "tone": item.get("tone") if item.get("tone") in _TONES else "plain",
            "unit": _text(item.get("unit")).strip() or None,
        })
    if cols:
        return cols
    # AI 没给列定义(或全无效) → 用行里键的并集补, 顺序按首次出现
    seen: list[str] = []
    for row in rows[:50]:
        for k in row:
            if k not in seen:
                seen.append(k)
    return [
        {
            "key": k,
            "label": k,
            "align": "right" if isinstance(rows[0].get(k), (int, float)) and not isinstance(rows[0].get(k), bool) else "left",
            "tone": "plain",
            "unit": None,
        }
        for k in seen[:MAX_COLUMNS]
    ]


def _norm_rows(raw: Any) -> list[dict]:
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if len(out) >= MAX_ROWS:
            break
        if isinstance(item, dict):
            out.append({str(k): v for k, v in item.items()})
        elif isinstance(item, list):
            out.append({f"c{i}": v for i, v in enumerate(item)})
    return out


def _norm_section(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rows = _norm_rows(raw.get("rows") if raw.get("rows") is not None else raw.get("data"))
    cols = _norm_columns(raw.get("columns") if raw.get("columns") is not None else raw.get("cols"), rows)
    if not rows and not cols:
        return None
    return {
        "title": _text(raw.get("title") or raw.get("label")).strip() or None,
        "note": _text(raw.get("note")).strip() or None,
        "columns": cols,
        "rows": rows,
    }


def normalize_spec(raw: Any) -> dict:
    """把 AI 返回的对象收敛成固定契约。内容实在为空时抛 ValueError。

    宽容的地方: 别名(data/cols/summary)、二维数组行、顶层直接给 rows。
    不宽容的地方: 类型不对就丢, 数量超上限就截 —— 前端只认这一种形状。
    """
    if isinstance(raw, list):
        raw = {"sections": [{"rows": raw}]}
    if not isinstance(raw, dict):
        raise ValueError("AI 没有返回 JSON 对象")

    sections: list[dict] = []
    top = _norm_section({
        "rows": raw.get("rows"),
        "columns": raw.get("columns") if raw.get("columns") is not None else raw.get("cols"),
    })
    if top:
        sections.append(top)
    for s in raw.get("sections") if isinstance(raw.get("sections"), list) else []:
        if len(sections) >= MAX_SECTIONS:
            break
        norm = _norm_section(s)
        if norm:
            sections.append(norm)

    stats: list[dict] = []
    stats_raw = raw.get("stats") or raw.get("summary") or raw.get("kpis")
    for item in stats_raw if isinstance(stats_raw, list) else []:
        if len(stats) >= MAX_STATS:
            break
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label") or item.get("name")).strip()
        value = _text(item.get("value"))
        if not label and not value:
            continue
        stats.append({
            "label": label,
            "value": value,
            "hint": _text(item.get("hint") or item.get("desc")).strip() or None,
            "tone": item.get("tone") if item.get("tone") in _TONES else "plain",
        })

    notes_raw = raw.get("notes")
    if isinstance(notes_raw, str):
        notes_raw = [notes_raw]
    notes = [t for t in ( _text(n).strip() for n in (notes_raw or [])[:MAX_NOTES]) if t]

    if not sections and not stats and not notes:
        raise ValueError("AI 返回的内容里没有可显示的数据")

    return {
        "title": _text(raw.get("title")).strip() or None,
        "subtitle": _text(raw.get("subtitle")).strip() or None,
        "updated_at": _text(raw.get("updated_at") or raw.get("updatedAt")).strip() or None,
        "stats": stats,
        "sections": sections,
        "notes": notes,
    }


# ---------------------------------------------------------------- 结果缓存


def _cache_path():
    from app.config import settings
    p = settings.data_dir / "user_data" / "external_page_view.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _source_hash(url: str, source: str, hint: str) -> str:
    h = hashlib.sha256()
    h.update(url.encode("utf-8"))
    h.update(b"\x00")
    h.update(hint.encode("utf-8"))
    h.update(b"\x00")
    h.update(source.encode("utf-8"))
    return h.hexdigest()


# [R146] 「最近一次结果」缓存的有效期。命中期内**连页面都不抓**。
#
# 起因(用户): 「这部分不应该每次点开都需要抓取分析一次」。原来的缓存键是
# `sha256(url + hint + 原文)` —— 要算这个键就**必须先把页面抓回来**, 而这类
# 行情看板的 HTML 里带时间戳/随机 id, 原文哈希几乎从不命中, 于是每次点开都是
# 一次抓取 + 一次 AI 调用。既慢又花钱, 而页面内容其实半小时都不会变多少。
#
# 所以补一层**只按「地址 + 提示词」索引**的最近结果: 命中且没过期 → 直接回,
# 零网络零 AI。过期了才走原来那条(抓取 → 原文哈希 → 必要时 AI)。
# 想立刻重来点「重新解析」(force), 那条路不受这层影响。
LATEST_TTL_S = 30 * 60


def _latest_path():
    from app.config import settings
    p = settings.data_dir / "user_data" / "external_view_latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _latest_key(url: str, hint: str) -> str:
    h = hashlib.sha256()
    h.update((url or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((hint or "").strip().encode("utf-8"))
    return h.hexdigest()


def load_latest(url: str, hint: str) -> dict | None:
    """按地址+提示词取最近一次成功的整理结果; 没有/坏了返回 None。"""
    from app.services.json_store import lock_for
    path = _latest_path()
    with lock_for(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if not isinstance(data, dict):
        return None
    got = data.get(_latest_key(url, hint))
    return got if isinstance(got, dict) else None


def save_latest(url: str, hint: str, payload: dict) -> None:
    """存最近一次结果。按 key 覆盖, 只保留最近若干个地址免得无限长。"""
    from app.services.json_store import atomic_write_json, lock_for
    path = _latest_path()
    with lock_for(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data[_latest_key(url, hint)] = payload
        if len(data) > 20:   # 配过的外部页不会有那么多, 超了按生成时间裁
            data = dict(sorted(data.items(),
                               key=lambda kv: kv[1].get("generated_at") or 0)[-20:])
        atomic_write_json(path, data)


def load_cached(key: str) -> dict | None:
    """取缓存(键不匹配返回 None)。缓存文件坏了按没有处理。"""
    from app.services.json_store import lock_for
    path = _cache_path()
    with lock_for(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return data if isinstance(data, dict) and data.get("key") == key else None


def save_cached(key: str, payload: dict) -> None:
    from app.services.json_store import atomic_write_json, lock_for
    path = _cache_path()
    with lock_for(path):
        atomic_write_json(path, {"key": key, **payload})


async def build_view(url: str, hint: str = "", *, force: bool = False) -> dict:
    """抓原文 → (必要时)调 AI → 归一化 → 缓存。返回给前端渲染的完整载荷。"""
    from app.services import external_fetch
    from app.services.ai_json import extract_json_object
    from app.services.ai_provider import ai_configured, generate_ai_text, last_served_profile_name

    # [R146] 第一层: 最近一次结果还新鲜就**直接回, 连页面都不抓**。
    # 这一层是为了"点开就有", 不是为了省那一次 HTTP —— 省掉的主要是后面那次
    # AI 调用, 以及抓取本身最长 12 秒的等待。
    if not force:
        latest = load_latest(url, (hint or "").strip())
        if latest:
            age = time.time() - float(latest.get("generated_at") or 0)
            if 0 <= age < LATEST_TTL_S:
                return {**latest, "from_cache": True, "cache_kind": "latest",
                        "age_seconds": int(age)}

    fetched = external_fetch.fetch(url, force=force)
    source = clean_source(fetched["text"], fetched.get("content_type", ""))
    if not source:
        raise ValueError("抓回来是空页面, 没有内容可以整理")

    # 第二层: 原文一个字没变就不必再调 AI(过期后重抓, 但页面没更新的常见情形)
    key = _source_hash(fetched["url"], source, (hint or "").strip())
    if not force:
        cached = load_cached(key)
        if cached:
            payload = {**cached, "fetched_at": fetched["fetched_at"]}
            save_latest(url, hint or "", payload)
            return {**payload, "from_cache": True, "cache_kind": "source",
                    "age_seconds": 0}

    if not ai_configured():
        raise ValueError("还没有配置 AI —— 抓取模式要靠面板里的 AI 把页面整理成表格")

    messages = build_messages(source, fetched["url"], hint)
    text = await generate_ai_text(messages, temperature=0.1, max_tokens=None)
    obj = extract_json_object(text)
    if obj is None:
        # [同 R22] 思考型模型偶发格式跑偏 —— 带死命令重试一次, 大多能自愈
        logger.info("external view parse failed, retrying with strict instruction")
        text = await generate_ai_text(
            messages + [{"role": "user", "content":
                         "重要:只输出一个 JSON 对象本身,第一个字符必须是 {,"
                         "不要任何思考过程、解释或代码块围栏。"}],
            temperature=0.0,
            max_tokens=None,
        )
        obj = extract_json_object(text)
    if obj is None:
        raise ValueError(f"AI 返回的不是 JSON, 无法解析。原文开头: {(text or '')[:120]}")

    payload = {
        "spec": normalize_spec(obj),
        "url": fetched["url"],
        "hint": (hint or "").strip(),
        "model": last_served_profile_name() or "",
        "generated_at": time.time(),
        "source_chars": len(source),
        # 抓取时刻存进 payload —— 走"最近一次结果"那条路时不会再抓一次,
        # 界面上那行"抓取于 …"必须是当时那次的时间, 不能是现在
        "fetched_at": fetched["fetched_at"],
    }
    save_cached(key, payload)
    save_latest(url, hint or "", payload)
    return {**payload, "key": key, "from_cache": False, "cache_kind": "fresh",
            "age_seconds": 0}
