"""[fork 增强 R265] 粘一段话 → AI 抽出提到的个股 → 匹配主数据 → 走同一套候选确认。

## 为什么要有这条路

已有的四条入口(截图 / CSV / TXT / 粘贴代码)都假设**代码就摆在文本里**。可日常
真正想导入的东西长这样:

    今天复盘: 光模块方向中际旭创、新易盛继续走强, 消费电子里立讯精密(002475)
    补涨, 但歌尔股份还在压力位下方, 先观察。

这段话里三只票只有名字没有代码, 而 `extract_codes` 只认六位数字 —— 老路会一只
都抽不出来。这条新路补的就是这个缺口: **让 AI 只负责"这段话提到了哪几只票"**,
匹配交给系统。

## 界限: AI 抽提及, 系统认主数据

**AI 给的代码一律不直接采信。** 模型把「立讯精密」写成 002745 这种错, 光看代码
是合法的六位数, 照单全收就会把另一只完全无关的票导进自选。所以:

- 名称 → 主数据反查 symbol; 代码 → 主数据反查 symbol
- **两边都能查到但对不上 → 判存疑, 不匹配**, 原因写在候选上给人看
- 只有一边能查到 → 按那一边算
- 都查不到 → 未匹配, 把原文提及带回去, 人一眼能看出 AI 抽了个什么

这和 `watchlist_ai_group` 的「只认自选内的代码, 不得编造」是同一条纪律, 只是这里
多一层:名称也要回主数据校验, 因为这条路的输入本来就以名称为主。

## 历史已导入过怎么办

一个字都不用特殊处理 —— 候选结构里带 ``already_in_watchlist``, 前端那套现成的
确认流程(`rowState`)会把已在自选的默认不勾、把已在目标分组的划到"已略过",
写入走 `watchlist.add_batch`(重复添加保留既有分组, 只并入尚未属于的)。**这条新路
只要产出同一个结构, 历史去重就是白捡的。** 本模块自己只做一件相关的事:
同一只票在一段话里被提到多次, 按首次出现去重。

## 边界

除 `generate` 外**全是纯函数, 不碰 I/O 不碰账本** —— 解析与匹配都能脱离 AI 单测。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.services.watchlist_ocr.pipeline import ImportCandidate, build_instrument_lookups

logger = logging.getLogger(__name__)

#: 一次最多送审的正文长度。研报/公众号长文常上万字, 截断比拒绝有用 ——
#: 提到的票基本集中在前半段, 全文送审只是把预算烧在免责声明上。
MAX_TEXT_CHARS = 6000
#: 一段话里最多认多少只。超出通常意味着 AI 把行业成分股列表整个抄了下来。
MAX_MENTIONS = 60

#: 存疑原因(展示给人看的短语, 不讲算法)。
WARN_CONFLICT = "名称与代码对不上, 未采信"
WARN_AMBIGUOUS = "这个名称对应多只证券"
WARN_UNKNOWN = "证券主数据里没有这个名称/代码"

_SYSTEM = """你是 A 股盘面助理。用户会粘来一段话(复盘笔记 / 研报片段 / 群消息 / 公众号正文),
你的唯一任务是**把这段话里提到的个股挑出来**, 不做任何点评。

规则:
1. 只挑**个股**(A 股股票、ETF)。指数(上证指数/创业板指)、板块与题材名(光模块/半导体)、
   行业、概念、基金公司、人名一律不要
2. **名称照抄原文**, 不要改写、不要补全、不要翻译; 原文写简称就给简称
3. 原文里紧挨着写了代码(如"立讯精密(002475)")才填 code, **没写就留空**;
   **绝对不要凭记忆补代码** —— 记错的代码会把完全无关的票导进用户自选
4. 同一只票提到多次只给一条
5. 只是顺带提及(如"不像某某那样")也算提到, 一并给出; 是否导入由用户自己勾选
6. 一只都没提到就返回空数组

只输出一个 JSON 对象, 不要任何解释或代码块围栏:
{"mentions": [{"name": "中际旭创", "code": "", "quote": "光模块方向中际旭创继续走强"}]}
quote 是原文里提到它的那半句(不超过 30 字), 用来让用户核对你有没有抽错。"""

# 名称归一化: 去掉空白(含全角)与常见分隔符, 字母统一大写。
# 主数据里的名称形如 "宁德时代" "TCL科技" "*ST海航" "通信ETF国泰"。
_STRIP_RE = re.compile(r"[\s　·\-—_()（）]+")
# 交易状态前缀: 除权除息/退市整理等挂在名称前, 与"这是哪只票"无关。
_PREFIX_RE = re.compile(r"^(\*?ST|S\*ST|SST|XD|XR|DR|N|C|U|W|V)+")


def normalize_name(raw: str | None) -> str:
    """把名称归一到可比对的形式。纯函数。"""
    if not raw:
        return ""
    return _STRIP_RE.sub("", str(raw)).upper()


def _bare(name: str) -> str:
    """再剥掉交易状态前缀 —— 「*ST海航」与「海航」指的是同一只。"""
    return _PREFIX_RE.sub("", name)


def build_name_lookup(symbol_to_name: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    """名称 → symbol 反查表, 外加一张「这个名称对应多只」的黑名单。

    **重名必须显式记下来而不是先到先得。** 先到先得会让「一段话里提到 X」静默
    解析成两只同名证券里的某一只, 导进去了人还不知道选错了; 记进黑名单之后
    这一条会退回未匹配并写明原因, 由人自己定夺。纯函数。
    """
    lookup: dict[str, str] = {}
    ambiguous: set[str] = set()
    for symbol, name in symbol_to_name.items():
        for key in {normalize_name(name), _bare(normalize_name(name))}:
            if not key:
                continue
            hit = lookup.get(key)
            if hit is None:
                lookup[key] = symbol
            elif hit != symbol:
                ambiguous.add(key)
    return lookup, ambiguous


def _lookup_name(raw: str | None, lookup: dict[str, str],
                 ambiguous: set[str]) -> tuple[str | None, bool]:
    """名称 → (symbol, 是否重名)。原名查不到再试剥前缀的形式。"""
    key = normalize_name(raw)
    if not key:
        return None, False
    for k in (key, _bare(key)):
        if not k:
            continue
        if k in ambiguous:
            return None, True
        hit = lookup.get(k)
        if hit:
            return hit, False
    return None, False


def parse_mentions(text: str | None) -> list[dict[str, str]]:
    """AI 输出 → [{name, code, quote}]。纯函数, 坏数据一律跳过而不是抛。"""
    from app.services.ai_json import extract_json_object

    obj = extract_json_object(text) or {}
    out: list[dict[str, str]] = []
    for m in (obj.get("mentions") or [])[:MAX_MENTIONS]:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or "").strip()[:32]
        code = str(m.get("code") or "").strip()
        # 代码字段可能夹带后缀或杂字("002475.SZ" / "代码002475"), 只取六位数字
        digits = re.search(r"(?<!\d)(\d{6})(?!\d)", code)
        code = digits.group(1) if digits else ""
        if not name and not code:
            continue
        out.append({"name": name, "code": code,
                    "quote": str(m.get("quote") or "").strip()[:40]})
    return out


def resolve_mentions(
    mentions: list[dict[str, str]],
    code_to_symbol: dict[str, str],
    symbol_to_name: dict[str, str],
    existing_symbols: set[str] | None = None,
) -> list[dict[str, Any]]:
    """提及 → 候选列表。**这里是整条路的判定核心**, 纯函数。

    每条提及按「名称查主数据」与「代码查主数据」各查一次, 然后:

    - 两边都中且一致 → 匹配
    - 两边都中但**指向不同的票** → 不匹配, 标 `WARN_CONFLICT`(AI 记错代码的典型样子)
    - 只中一边 → 按中的那边算
    - 都没中 → 不匹配, 把原文提及带回去

    同一只票多次提及按首次出现去重; 未匹配的按「名称+代码」去重, 免得同一个
    抽错的东西刷屏。
    """
    existing = existing_symbols or set()
    name_lookup, ambiguous = build_name_lookup(symbol_to_name)

    out: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    seen_misses: set[str] = set()
    for m in mentions:
        raw_name, code = m.get("name", ""), m.get("code", "")
        by_name, is_ambiguous = _lookup_name(raw_name, name_lookup, ambiguous)
        by_code = code_to_symbol.get(code) if code else None

        warn = ""
        if by_name and by_code and by_name != by_code:
            symbol = None
            warn = WARN_CONFLICT
        else:
            symbol = by_name or by_code
            if symbol is None:
                warn = WARN_AMBIGUOUS if is_ambiguous else WARN_UNKNOWN

        mention = raw_name or code
        if symbol:
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            cand = ImportCandidate(
                code=code or symbol.split(".", 1)[0],
                symbol=symbol,
                name=symbol_to_name.get(symbol) or raw_name or None,
                matched=True,
                already_in_watchlist=symbol in existing,
            )
        else:
            key = f"{normalize_name(raw_name)}|{code}"
            if key in seen_misses:
                continue
            seen_misses.add(key)
            cand = ImportCandidate(
                code=code, symbol=None, name=raw_name or None,
                matched=False, already_in_watchlist=False,
            )
        row = cand.to_dict()
        row["mention"] = mention
        row["quote"] = m.get("quote", "")
        row["warn"] = warn
        out.append(row)
    return out


def _finalize(text: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """组装与截图/CSV 一致的候选响应, 让前端复用同一套确认流程。"""
    matched = sum(1 for c in candidates if c["matched"])
    return {
        "provider": "ai-text",
        "raw_text": text,
        "codes": [c["code"] for c in candidates if c["code"]],
        "candidates": candidates,
        "matched_count": matched,
        "unmatched_count": len(candidates) - matched,
    }


async def generate(
    text: str,
    data_dir: Path,
    *,
    existing_symbols: set[str] | None = None,
) -> dict[str, Any]:
    """整条路: 正文 → AI 抽提及 → 主数据匹配 → 候选。失败返回 {"error": ...}。

    只有这一个函数碰外部世界(AI 调用 + 读 instruments), 上面的都可脱离 AI 单测。
    """
    from app.services.ai_provider import ai_configured, generate_ai_text

    body = (text or "").strip()
    if not body:
        return {"error": "请粘贴要解析的内容"}
    if not ai_configured():
        return {"error": "未配置 AI —— 到设置页填 AI Key 后再试"}

    clipped = body[:MAX_TEXT_CHARS]
    try:
        raw = await generate_ai_text(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps({"text": clipped}, ensure_ascii=False)},
            ],
            temperature=0.1,          # 抽取任务, 不需要发挥
            max_tokens=None,          # [上游标准] 不限制输出(推理模型思考计入预算)
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("watchlist ai-text failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}

    mentions = parse_mentions(raw)
    if not mentions:
        snippet = (raw or "").replace("\n", " ").strip()[:80]
        return {"error": f"这段话里没认出个股(AI 原文开头: {snippet or '空'}…)——可重试或换模型"}

    code_to_symbol, symbol_to_name = build_instrument_lookups(data_dir)
    candidates = resolve_mentions(mentions, code_to_symbol, symbol_to_name, existing_symbols)
    result = _finalize(clipped, candidates)
    if len(body) > MAX_TEXT_CHARS:
        result["truncated"] = True
    return result
