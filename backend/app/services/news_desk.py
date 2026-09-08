"""[fork 增强] R180 消息面 —— 逐条 AI 凝练 + 一大段总的 + 注入决策。

用户: 「当作是个消息面, 我上传的数据或者图片都会调度 AI 凝练后保存, 然后还要
凝练一大段总的, 以后每次做出决策性的结论都得参考一次这一大段总的」。

三层:
  ① 逐条凝练  一条消息(文字/图片/文本文件) → 一段要点。图片走多模态。
  ② 一段总的  把全部条目的要点综合成一段"当前消息面是什么样"。
  ③ 注入      AI 做决策时把②带上。

**这一层最需要小心的是③, 所以边界划死:**

  · **只进 AI 层, 绝不进规则层。** 把握分、出场线、六态、通道位置全部是纯规则、
    可复现、可回测的 —— 一段 AI 写的话注进去, 它们就再也不能自证了。注入点只有
    今日 AI 导读·优选 / AI 个股信号 / AI 个股分析 / 模拟交易这几处**本来就是
    AI 在下结论**的地方。

  · **带时效, 而且要说出来。** 消息面是会过期的东西。总结里永远带上"基于几条、
    最后更新于何时", 让下游的 AI 和人都知道自己在参考多旧的东西。超过
    ``STALE_DAYS`` 天直接不注入 —— 与其拿上个月的消息面影响今天的判断,
    不如没有。

  · **可以整体关掉。** ``settings.news_desk_inject`` 关掉后, 所有决策路径立刻
    回到改造前的行为。上线一个会影响每一次决策的东西, 必须留这个开关。

  · **失败即跳过。** 任何一步出错都只是"这次没带上消息面", 绝不让它把
    今日总览或个股信号搞挂。

存 ``user_data/news_desk_summary.json``: 一段总的 + 它基于哪些条目。
逐条的 digest 存在 usage_notes 各自的记录里。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 综合时最多带多少条 —— 消息面攒久了几百条, 全塞进去既烧钱又会让重点被稀释。
# 取最近的 N 条(置顶的优先), 其余不参与。
MAX_ITEMS_FOR_SUMMARY = 60
# 每条 digest 进综合时截断到多少字 —— 综合要的是要点不是原文
MAX_DIGEST_IN_SUMMARY = 400
# 总结超过这么多天就不再注入决策(见模块头)
STALE_DAYS = 7
# 注入给下游的总结最长多少字 —— 它会进每一次 AI 决策的提示词, 不能无限长
MAX_INJECT_CHARS = 3000


def _path() -> Path:
    from app.config import settings
    p = settings.data_dir / "user_data" / "news_desk_summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ======================== ① 逐条凝练 ========================

_ITEM_SYSTEM = (
    "你在帮用户整理**消息面**素材。用户会给你一条素材: 一段文字、一张图(研报截图/"
    "公告截图/行情图), 或一份文本数据。\n"
    "把它凝练成中文要点, 要求:\n"
    "1) **只写素材里有的东西。** 看不清、没写明的一律说「未提及」, 不要补常识、"
    "不要推测、不要展开联想 —— 这条要点之后会被当成事实用在决策里。\n"
    "2) 结构: 先一句话说这是什么(政策/公告/研报/行情/观察), 再分点列关键事实"
    "(带上原文里的数字、时间、主体名称)。\n"
    "3) 如果素材里有明确的方向性判断(利好/利空/看多/看空), 如实转述并注明"
    "「素材观点」; **你自己不要下判断**。\n"
    "4) 200 字以内。看不懂或素材无有效内容, 就只回一句「无法识别有效内容」。"
)


def _image_data_uri(path: Path) -> str | None:
    import base64
    import mimetypes
    try:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception as e:  # noqa: BLE001
        logger.warning("news desk: read image failed %s: %s", path, e)
        return None


async def digest_item(note: dict, *, data_dir: Path) -> str:
    """一条消息 → 一段要点。抛异常交给调用方处理(界面要能说清为什么失败)。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        raise RuntimeError("未配置 AI")

    kind = note.get("kind") or "text"
    text = (note.get("content") or "").strip()
    att = note.get("attachment") or {}

    if kind == "image" and att.get("path"):
        uri = _image_data_uri(data_dir / att["path"])
        if not uri:
            raise RuntimeError("图片读取失败")
        parts: list[dict] = [{"type": "text",
                              "text": text or "这张图里有什么值得记进消息面的信息?"}]
        parts.append({"type": "image_url", "image_url": {"url": uri}})
        messages = [{"role": "system", "content": _ITEM_SYSTEM},
                    {"role": "user", "content": parts}]
    else:
        body = text
        if kind == "file" and att.get("path"):
            body = f"{text}\n\n---- 文件 {att.get('name') or ''} 内容 ----\n" \
                   + _read_text_file(data_dir / att["path"])
        if not body.strip():
            raise RuntimeError("这条没有可凝练的内容")
        messages = [{"role": "system", "content": _ITEM_SYSTEM},
                    {"role": "user", "content": body}]

    try:
        out = await generate_ai_text(messages, temperature=0.2, max_tokens=800)
    except Exception as e:  # noqa: BLE001
        # 模型不支持视觉时上游多半是 400/不认识的字段。给一句人能看懂的,
        # 而不是把原始报错甩到界面上。
        if kind == "image":
            raise RuntimeError(f"图片解读失败(当前模型可能不支持读图): {e}") from e
        raise
    return (out or "").strip()


# 文本文件读进来最多截多少 —— 再长对凝练没有帮助, 只会烧 token
_MAX_FILE_CHARS = 20000


def read_attachment_text(path: Path) -> str:
    """[R180] 供 API 在凝练成功后把文本文件内容并进正文(公开名, 内部同名私有版已并入)。"""
    return _read_text_file(path)


def _read_text_file(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=enc)[:_MAX_FILE_CHARS]
        except UnicodeDecodeError:
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning("news desk: read file failed %s: %s", path, e)
            return ""
    return ""


# ======================== ② 一大段总的 ========================

_SUMMARY_SYSTEM = (
    "你在给用户维护一份**消息面总览**。输入是他这段时间记录的全部消息要点"
    "(每条带日期与状态: 待验证/已验证/不成立)。\n"
    "把它们综合成一段中文总览, 要求:\n"
    "1) **只用给你的这些要点。** 不许补充外部信息、不许推测行情走势。\n"
    "2) 结构: ①当前主导的几条线索(政策/资金/行业, 各带上支撑它的条目日期); "
    "②互相矛盾或已被证伪的(标了「不成立」的要点尤其要提); ③目前还悬着、"
    "等待验证的。\n"
    "3) 标了「不成立」的**必须**明确写出来它已被证伪 —— 这段总览会被用在之后的"
    "决策里, 留着一条已经错了的判断比没有更糟。\n"
    "4) 600 字以内, 分点, 不写行话套话。\n"
    "5) 你是在**描述用户记了什么**, 不是在给投资建议。不要出现「建议买入/卖出」。"
)


def _items_for_summary(notes: list[dict]) -> list[dict]:
    """挑进综合的条目: 置顶优先, 其余按时间新→旧, 取前 N 条。

    只要有 digest 或正文的条目 —— 一条空记录进去只会占位置。
    """
    usable = [n for n in notes
              if (n.get("digest") or "").strip() or (n.get("content") or "").strip()]
    pinned = [n for n in usable if n.get("pinned")]
    rest = [n for n in usable if not n.get("pinned")]
    return (pinned + rest)[:MAX_ITEMS_FOR_SUMMARY]


_STATUS_CN = {"": "随手记", "pending": "待验证", "verified": "已验证", "rejected": "不成立"}


def build_payload(notes: list[dict]) -> list[dict]:
    """喂给综合的那份东西。**白名单**: 只出要点/日期/状态, 不出附件路径。"""
    out = []
    for n in _items_for_summary(notes):
        body = (n.get("digest") or "").strip() or (n.get("content") or "").strip()
        out.append({
            "日期": str(n.get("updated_at") or n.get("created_at") or "")[:10],
            "状态": _STATUS_CN.get(n.get("status") or "", "随手记"),
            "要点": body[:MAX_DIGEST_IN_SUMMARY],
        })
    return out


async def synthesize(notes: list[dict]) -> dict:
    """跑一次综合并落盘。返回存下来的那条。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        raise RuntimeError("未配置 AI")
    payload = build_payload(notes)
    if not payload:
        raise RuntimeError("消息面还没有可综合的内容")

    text = await generate_ai_text(
        [{"role": "system", "content": _SUMMARY_SYSTEM},
         {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)}],
        temperature=0.3, max_tokens=2000)
    text = (text or "").strip()
    if not text:
        raise RuntimeError("综合结果为空")

    entry = {
        "text": text,
        "as_of": _now(),
        "item_count": len(payload),
        # 存下当时综合的是哪些条目 —— 之后回看这段总览时能追溯它的依据
        "item_ids": [n.get("id") for n in _items_for_summary(notes)],
    }
    _write(entry)
    return entry


def _write(entry: dict) -> None:
    from app.services.json_store import atomic_write_json, lock_for
    try:
        with lock_for(_path()):
            atomic_write_json(_path(), entry)
    except Exception as e:  # noqa: BLE001
        logger.warning("news desk summary write failed: %s", e)


def latest() -> dict | None:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("text") else None
    except (OSError, ValueError):
        return None


# ======================== ③ 注入决策 ========================

def _inject_enabled() -> bool:
    """总开关。取不到配置一律当**开** —— 用户明确要求"每次决策都参考"，
    默认行为应该是带上; 但任何一处想关掉都能立刻关掉。"""
    try:
        from app.config import settings
        return bool(getattr(settings, "news_desk_inject", True))
    except Exception:  # noqa: BLE001
        return True


def _age_days(as_of: str | None) -> float | None:
    try:
        return (datetime.now() - datetime.fromisoformat(str(as_of))).total_seconds() / 86400
    except (TypeError, ValueError):
        return None


def context_for_ai() -> str:
    """给决策路径的那段话。没有/过期/关掉一律返回空串, 调用方按"没有"处理。

    **返回的文本自带时效说明**, 因为下游是 AI: 它看不到我们这里的判断,
    只能靠这段话本身知道自己在参考多旧的东西。
    """
    if not _inject_enabled():
        return ""
    cur = latest()
    if not cur:
        return ""
    age = _age_days(cur.get("as_of"))
    if age is not None and age > STALE_DAYS:
        # 与其拿上个月的消息面影响今天的判断, 不如没有
        logger.info("news desk: summary is %.1f days old, not injecting", age)
        return ""
    text = str(cur.get("text") or "").strip()[:MAX_INJECT_CHARS]
    if not text:
        return ""
    when = str(cur.get("as_of") or "")[:16].replace("T", " ")
    aged = f"{age:.1f} 天前" if age is not None else "时间未知"
    return (
        "## 用户维护的消息面总览\n"
        f"(综合自 {cur.get('item_count', 0)} 条记录, 生成于 {when}, 距今 {aged})\n\n"
        f"{text}\n\n"
        "**怎么用这一段**: 它是用户自己记录并让 AI 综合的消息面, 不是行情数据, "
        "也未经核实。把它当作背景与倾向参考, **不要拿它推翻价格与规则层给出的事实"
        "(趋势状态、出场线、通道位置、把握分)**。两者冲突时以价格与规则为准, "
        "并在结论里说明冲突在哪。"
    )
