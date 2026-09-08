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
# [R181] **时效**: 与 status(成立了吗)正交的第二个轴 —— 这条多久有效。
#
# R180 给所有消息用了同一个 7 天过期, 那是错的。用户: 「有一些消息是看公司业绩的,
# 这种就是埋伏, 肯定不会立马兑现, 这种怎么办, 有些是类似市场规律的又怎么办」。
#   · 业绩埋伏 7 天后就不注入了 —— 可正是三个月后你快忘了的时候最需要它;
#   · 市场规律("凯特纳贴下轨胜率高")根本不该过期。
#
# 三档的区别不只是活多久, **更是在决策里怎么用**:
HORIZON_NEWS = "news"      # 时效: 政策/突发/消息 —— 影响今天买不买
HORIZON_THESIS = "thesis"  # 埋伏: 业绩/基本面逻辑 —— 影响持有耐心, 别当短线砍了
HORIZON_RULE = "rule"      # 规律: 方法论 —— 影响怎么做, 不针对某只票
HORIZONS = (HORIZON_NEWS, HORIZON_THESIS, HORIZON_RULE)
HORIZON_CN = {HORIZON_NEWS: "时效", HORIZON_THESIS: "埋伏", HORIZON_RULE: "规律"}

# 时效类多少天后不再进决策。埋伏与规律**不受这个数管**。
STALE_DAYS = 7
# 埋伏默认多久回来核对一次(天)。AI 会按内容给建议(如"下个季报"), 给不出就用这个。
THESIS_DEFAULT_DUE_DAYS = 90
# 总结本身多久算陈旧 —— 它是对全部条目的综合, 只要还有埋伏/规律在, 就仍有参考
# 价值, 但太久没重新综合说明它没跟上最近的记录。
SUMMARY_STALE_DAYS = 30
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
    "4) 200 字以内。看不懂或素材无有效内容, digest 就写「无法识别有效内容」。\n\n"
    "然后判断这条素材的**时效类型**(这是分类, 不是让你预测行情):\n"
    "  news   时效  —— 政策、突发、公告、盘面消息。几天内影响判断, 过后就不重要了。\n"
    "  thesis 埋伏  —— 公司业绩、基本面逻辑、行业景气。**不会立刻兑现**, 要等一个\n"
    "                  具体事件(下个季报/年报/某项目投产)才知道对不对。\n"
    "  rule   规律  —— 关于市场本身或方法的经验总结(某形态胜率高、某类行情怎么走)。\n"
    "                  不针对某一只票, 也不会过期。\n"
    "判 thesis 时, 再给一个 due_days: 大概多少天之后该回来核对它兑现了没有\n"
    "(下个季报约 90 天, 年报约 120 天; 拿不准就给 90)。其他两类 due_days 给 null。\n\n"
    "**只输出一个 JSON 对象**, 不要任何其他文字:\n"
    '{"digest": "要点正文", "horizon": "news|thesis|rule", "due_days": 90 或 null}'
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
    return _parse_digest(out)


def _parse_digest(out: str | None) -> dict:
    """模型输出 → {digest, horizon, due_days}。

    **解析失败不算失败。** 拿不到 JSON 就把原文当要点、类型退到"时效" ——
    分类是锦上添花, 要点才是用户要的东西; 为了一个分类把整条凝练判死没道理。
    """
    from app.services.ai_json import extract_json_object

    text = (out or "").strip()
    obj = extract_json_object(text) or {}
    digest = str(obj.get("digest") or "").strip() or text
    horizon = str(obj.get("horizon") or "").strip()
    if horizon not in HORIZONS:
        horizon = HORIZON_NEWS
    due = obj.get("due_days")
    try:
        due_days = int(due) if due is not None else None
    except (TypeError, ValueError):
        due_days = None
    if horizon == HORIZON_THESIS and not due_days:
        due_days = THESIS_DEFAULT_DUE_DAYS
    if horizon != HORIZON_THESIS:
        due_days = None      # 只有埋伏才有兑现检查点
    return {"digest": digest, "horizon": horizon, "due_days": due_days}


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
    "2) **按给你的三个分区分别写, 不要混在一起** —— 它们在决策里的用法完全不同:\n"
    "   【时效】当下几天有效的消息, 影响今天买不买;\n"
    "   【埋伏】还没兑现的基本面逻辑, 影响的是**持有耐心** —— 写清每条在等什么、"
    "什么时候该回来核对, 明确说这些**不构成今天的买卖理由**;\n"
    "   【规律】关于市场本身的经验, 不针对某只票, 也不会过期。\n"
    "3) 每个分区里再点出: 互相矛盾的、已被证伪的(标了「不成立」的尤其要提)。\n"
    "4) 标了「不成立」的**必须**明确写出来它已被证伪 —— 这段总览会被用在之后的"
    "决策里, 留着一条已经错了的判断比没有更糟。\n"
    "5) 800 字以内, 分点, 不写行话套话。\n"
    "6) 你是在**描述用户记了什么**, 不是在给投资建议。不要出现「建议买入/卖出」。"
)


def _items_for_summary(notes: list[dict]) -> list[dict]:
    """挑进综合的条目: 置顶优先, 其余按时间新→旧, 取前 N 条。

    只要有 digest 或正文的条目 —— 一条空记录进去只会占位置。
    """
    usable = [n for n in notes
              if ((n.get("digest") or "").strip() or (n.get("content") or "").strip())
              and _still_relevant(n)]
    pinned = [n for n in usable if n.get("pinned")]
    rest = [n for n in usable if not n.get("pinned")]
    return (pinned + rest)[:MAX_ITEMS_FOR_SUMMARY]


def _still_relevant(note: dict) -> bool:
    """这条现在还该参与综合吗 —— **按它自己的时效判, 不是一刀切**。

      · 时效  超过 STALE_DAYS 天就馊了, 不再进
      · 埋伏  一直留着, 直到用户把它标成已验证/不成立 —— 埋伏最容易失败的方式
              不是记错, 是记了之后忘了。它必须一直在眼前, 到期还要主动提醒。
      · 规律  永不过期
    置顶的一律留着 —— 用户手动钉住就是最强的"我还要它"的信号。
    """
    if note.get("pinned"):
        return True
    # 已经有结论的时效消息没必要再影响今天; 但埋伏/规律的结论本身就是价值
    h = note.get("horizon") if note.get("horizon") in HORIZONS else HORIZON_NEWS
    if h in (HORIZON_THESIS, HORIZON_RULE):
        return True
    age = _age_days(note.get("updated_at") or note.get("created_at"))
    return age is None or age <= STALE_DAYS


_STATUS_CN = {"": "随手记", "pending": "待验证", "verified": "已验证", "rejected": "不成立"}


def build_payload(notes: list[dict]) -> dict:
    """喂给综合的那份东西。**白名单**: 只出要点/日期/状态/时效, 不出附件路径。

    [R181] **按时效分区**。混在一个平表里, 下游只能看到一堆句子, 分不出
    「今天的事」「埋着的」「方法论」—— 而这三样在决策里的用法完全不同。
    """
    buckets: dict[str, list[dict]] = {h: [] for h in HORIZONS}
    for n in _items_for_summary(notes):
        body = (n.get("digest") or "").strip() or (n.get("content") or "").strip()
        h = n.get("horizon") if n.get("horizon") in HORIZONS else HORIZON_NEWS
        item = {
            "日期": str(n.get("updated_at") or n.get("created_at") or "")[:10],
            "状态": _STATUS_CN.get(n.get("status") or "", "随手记"),
            "要点": body[:MAX_DIGEST_IN_SUMMARY],
        }
        if h == HORIZON_THESIS and n.get("due_at"):
            item["该核对的时间"] = str(n["due_at"])[:10]
        buckets[h].append(item)
    return {HORIZON_CN[h]: v for h, v in buckets.items() if v}


def payload_count(payload: dict) -> int:
    return sum(len(v) for v in payload.values())


async def synthesize(notes: list[dict]) -> dict:
    """跑一次综合并落盘。返回存下来的那条。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        raise RuntimeError("未配置 AI")
    payload = build_payload(notes)
    if not payload_count(payload):
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
        "item_count": payload_count(payload),
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


def due_theses(notes: list[dict]) -> list[dict]:
    """[R181] 到了兑现检查点、但还没给结论的埋伏。

    **埋伏最容易失败的方式不是记错, 是记了之后忘了。** 三个月后财报出来, 人早忘了
    当初为什么买。所以到期要主动把它推到眼前, 让用户回来标「已验证」还是「不成立」——
    这一步不做, 消息面就只是一个只进不出的垃圾桶, 那段总的也会越来越脏。

    已经标过 verified/rejected 的不再提醒 —— 那就是"给过结论了"。
    """
    now = datetime.now()
    out = []
    for n in notes:
        if n.get("horizon") != HORIZON_THESIS:
            continue
        if (n.get("status") or "") in ("verified", "rejected"):
            continue
        due = n.get("due_at")
        if not due:
            continue
        try:
            if datetime.fromisoformat(str(due)) <= now:
                out.append(n)
        except (TypeError, ValueError):
            continue
    return out


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
    # [R181] 淘汰的是**总结本身太久没重新综合**, 不再是"7 天一刀切"。
    #
    # R180 那个 7 天是错的: 它把埋伏和规律一起判了死刑。一条业绩埋伏正是三个月后
    # 你快忘了的时候最该被提醒; 一条市场规律根本不会过期。真正会馊的只有时效类,
    # 而那一类是在**综合的时候**按条筛掉的(见 _items_for_summary), 不是在这里
    # 把整段总结丢掉。
    if age is not None and age > SUMMARY_STALE_DAYS:
        logger.info("news desk: summary is %.1f days old (>%d), not injecting",
                    age, SUMMARY_STALE_DAYS)
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
        "并在结论里说明冲突在哪。\n"
        "**三个分区的用法不同, 不要混着用**:\n"
        "· 【时效】才是可以影响今天买卖判断的那部分;\n"
        "· 【埋伏】是还没兑现的逻辑 —— 它影响的是**要不要有耐心继续持有**, "
        "**不能当作今天的买入理由**。一只票正因为某条埋伏被持有时, 短期波动不该"
        "轻易推翻它; 但出场线与生命线仍然优先, 埋伏不是死扛的借口。\n"
        "· 【规律】是方法层面的经验, 用来解释你为什么这么判断, 不针对某一只票。"
    )
