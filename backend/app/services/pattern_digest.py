"""[fork 增强] R175 「回头看」的 AI 提炼层 —— 让 AI 念表, 不让 AI 算数。

用户想要的是: 偶尔回头看一眼, 看看这些结论**最近**在走什么调调, 让 AI 试着
提炼两句。这个模块就干这一件事, 但把边界划死:

**AI 拿到的只有一张已经算完的统计表。**
不给原始行、不给个股、不给价格。它的活是**措辞**, 不是统计 —— 分组、胜率、
背离全部由 ``score_ledger._by_label`` 用代码算完, AI 只负责把那几行数字讲成
人话。这样它说错了也只是话不好听, 底下的数字不会跟着错。

刻意的取舍(与 ai_pick_ledger / score_ledger 同源, 都是同一条规矩的延伸):

  - **只念表, 不许发挥**。提示词里写死: 只能引用表里出现过的数字; 样本不足
    的档必须明说"还看不出来", 不许绕过去给一个像模像样的判断。这条是这个
    模块存在的前提 —— 一旦允许它从别处取数, 它就会开始编。

  - **每天定稿后跑一次, 存起来。** 不是每次打开弹窗现算。除了省钱, 更要紧的
    是: 同一批数据问两次 AI 会给两套说法, 而"今天和昨天说的不一样"会让人以为
    行情变了, 其实只是采样噪声。存一份, 一天就是一句话。

  - **AI 说的话本身进台账。** 这条容易被跳过, 但它才是关键: 不存的话,
    "上个月 AI 说主线在轮动"就又是一句说了不算数的话 —— 跟用户想解决的
    问题一模一样。存下来, 三个月后能回头看它当时准不准。

  - **不回流。** 提炼结果不参与打分、不进任何提示词的输入。守 score_ledger
    那条"只记, 不反馈"。

存 ``user_data/pattern_digest.json``: {"entries": [...]}, 一天一条, 最多 240 天。
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

MAX_ENTRIES = 240
# 一次最多把多少档喂给 AI。表本身可能有几十档, 但尾部全是个位数样本的噪声,
# 塞进去只会让它抓着没意义的档说事。
TOP_ITEMS_PER_DIM = 6


def _path():
    from app.config import settings
    p = settings.data_dir / "user_data" / "pattern_digest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read() -> list[dict]:
    import json
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _write(entries: list[dict]) -> None:
    from app.services.json_store import atomic_write_json
    try:
        atomic_write_json(_path(), {"entries": entries[-MAX_ENTRIES:]})
    except Exception as e:  # noqa: BLE001
        logger.warning("pattern digest write failed: %s", e)


def build_table(res: dict) -> list[dict]:
    """evaluate() 的结果 → 喂给 AI 的那张表。**白名单, 只出数字。**

    刻意不传: 个股代码、价格、任何原始行。AI 看不见它们, 也就编不出来。
    """
    min_n = int(res.get("min_label_n") or 15)
    out = []
    for dim in res.get("labels") or []:
        items = []
        for it in (dim.get("items") or [])[:TOP_ITEMS_PER_DIM]:
            a = (it.get("stats") or {}).get("t5") or {}
            b = (it.get("recent_stats") or {}).get("t5") or {}
            enough = (a.get("n") or 0) >= min_n
            items.append({
                "取值": it.get("value"),
                "全期样本": a.get("n") or 0,
                "全期胜率": a.get("win_rate") if enough else None,
                "全期均值": a.get("avg") if enough else None,
                "最近样本": b.get("n") or 0,
                "最近胜率": b.get("win_rate") if (b.get("n") or 0) >= min_n else None,
                "背离": (it.get("shift") or {}).get("text"),
            })
        if items:
            out.append({"维度": dim.get("label"), "各档": items})
    return out


def _system_prompt(min_n: int, recent_days: int) -> str:
    return (
        "你在帮用户回看一套 A 股选股系统里那些**不参与打分的标签**"
        "(通道结论、六态趋势、主线归属、龙虎榜)最近好不好使。\n"
        "用户给你的是一张**已经算好的**统计表: 每档标签的全期胜率、"
        f"最近 {recent_days} 个交易日的胜率、以及两者的背离。T+5 口径, "
        "收盘价对收盘价。\n\n"
        "硬性要求:\n"
        f"1) **只能引用表里出现过的数字。** 表里没有的一律不许提 —— 不许推算、"
        "不许估计、不许拿常识补。你的任务是把这张表讲成人话, 不是做分析。\n"
        f"2) 胜率写成 null 的档表示**样本不足**(不到 {min_n} 个)。这些档只能说"
        "「还看不出来」, 绝对不许给倾向性判断。\n"
        "3) 重点讲**背离**: 全期和最近差得多的那几档才是用户想看的。"
        "全期最高的那档如果最近塌了, 这就是最该说的一句。\n"
        "4) 如果整张表都没有值得说的背离, 就直说「这段时间没有明显变化」。"
        "**不要为了有话说而找话说。**\n"
        "5) 中文, 300 字以内, 分点。每个结论后面用括号带上它依据的数字。\n"
        "6) 不要给操作建议, 不要提个股。你在描述历史, 不在推荐。"
    )


async def generate(res: dict) -> str:
    """跑一次提炼。调用方负责判断"今天要不要跑"。"""
    import json

    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        raise RuntimeError("未配置 AI")
    table = build_table(res)
    if not table:
        raise RuntimeError("台账还没有可统计的标签数据")

    payload = {
        "记录天数": res.get("recorded_days"),
        "最近窗口交易日数": res.get("recent_days"),
        "样本门槛": res.get("min_label_n"),
        "表": table,
    }
    text = await generate_ai_text(
        [{"role": "system",
          "content": _system_prompt(int(res.get("min_label_n") or 15),
                                    int(res.get("recent_days") or 20))},
         {"role": "user",
          "content": json.dumps(payload, ensure_ascii=False, indent=1)}],
        temperature=0.2,    # 念表的活, 不需要发挥
        max_tokens=1200,
    )
    return (text or "").strip()


def latest() -> dict | None:
    entries = _read()
    return entries[-1] if entries else None


def history(limit: int = 30) -> list[dict]:
    """倒序返回最近几条 —— 用来回看"上个月它是怎么说的"。"""
    return list(reversed(_read()[-limit:]))


def record(as_of: str, text: str, table: list[dict]) -> dict:
    """落一条。同一天重复跑就覆盖(与 today_ai_store 的"今天只有一份"一致)。"""
    from app.services.json_store import lock_for

    entry = {
        "as_of": as_of,
        "text": text,
        # 存下当时那张表 —— 否则三个月后回看这句话, 没法判断它当时依据的是什么
        "table": table,
        "created_at": date.today().isoformat(),
    }
    with lock_for(_path()):
        entries = [e for e in _read() if str(e.get("as_of")) != str(as_of)]
        entries.append(entry)
        entries.sort(key=lambda e: str(e.get("as_of")))
        _write(entries)
    return entry


async def refresh_if_stale(res: dict) -> dict | None:
    """今天还没跑过就跑一次。**这是唯一该被定时任务调的入口。**

    失败只记 WARNING 返回 None —— 提炼是个锦上添花的东西, 不该让它把台账
    统计或者页面拖垮。
    """
    as_of = res.get("last_day")
    if not as_of:
        return None
    cur = latest()
    if cur and str(cur.get("as_of")) == str(as_of):
        return cur     # 今天的已经有了, 不重复烧钱也不换一套说法
    try:
        text = await generate(res)
    except Exception as e:  # noqa: BLE001
        logger.warning("pattern digest generate skipped: %s", e)
        return None
    if not text:
        return None
    return record(str(as_of), text, build_table(res))
