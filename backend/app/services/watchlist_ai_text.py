"""[fork 增强 R265/R267] 粘一篇 MD → AI 按小分队分好 → 匹配主数据 → 分别导入不同分组。

## 输入长什么样

用户粘的是**公众号长文 / 研报正文**, 不是干净的清单。真实结构大致这样:

    **船舶**
    ...有政策、有需求、有订单, 关注中国船舶、**松发股份**、中船防务、招商轮船。

    **军工**
    ...关注中航成飞、中航沈飞、内蒙一机、**中兵红箭**、中无人机。

    **科技**
    ...我A这边, 紧盯光存芯方向的三个龙头中际、长鑫、寒王...

    光模块——**剑桥科技**
    液冷——**远东股份**、飞龙股份

四件事从这段里读得出来, 缺一件这条路就不好用:

1. **加粗小标题就是小分队** —— 分类是作者已经做好的, 系统照做即可, 不需要 AI 再
   按题材归纳一次(那正是 R267 拆掉「AI 一键分组」的原因: 作者分好的类比模型猜的准)。
2. **取最细的那一层当分队名** —— 剑桥科技归「光模块」而不是「科技」。想合并成一个
   「科技」组是导入界面上点一下的事; 反过来, 粗粒度分完再想拆开就没依据了。
3. **加粗的股票名是作者的重点票** —— 松发股份、中兵红箭、剑桥科技这些。这是原文里
   明摆着的信号, 丢掉可惜, 用 `starred` 带出来。
4. **正文里有简称** —— 「中际」指中际旭创。见下面「简称怎么认」。

## 界限: AI 只做切分与摘取, 主数据说了算

**AI 给的代码一律不直接采信。** 模型把「立讯精密」写成 002745 这种错, 光看代码是
合法的六位数, 照单全收就会把另一只完全无关的票导进自选。所以:

- 名称 → 主数据反查 symbol; 代码 → 主数据反查 symbol
- **两边都能查到但对不上 → 判存疑, 不匹配**, 原因写在候选上给人看
- 只有一边能查到 → 按那一边算
- 都查不到 → 未匹配, 把原文提及带回去, 人一眼能看出 AI 抽了个什么

### 简称怎么认

原文常写「中际」而主数据是「中际旭创」。**只认唯一前缀**: 主数据里以这个简称开头的
证券**有且只有一只**才算数。「中际」只对上中际旭创 → 认; 「中航」对上中航成飞/中航
沈飞/中航电子等一堆 → 不认, 退回去让人自己定。唯一性这道门是关键 —— 没有它, 前缀
匹配就成了"猜一只最像的", 那比不认更糟。

## 一只票进多个分队

同一只票在两个小分队里出现(比如既在「军工」又在「低空经济」), **两个都留着** ——
候选上的 `groups` 是个列表, 导入时它会同时进这两个分组。自选本来就是多组模型。

## 历史已导入过怎么办

一个字都不用特殊处理 —— 候选带 ``already_in_watchlist``, 前端那套现成的确认流程
会把已在自选的默认不勾、已在目标分组的划到「已略过」, 写入走 `watchlist.add_batch`
(重复添加保留既有分组, 只并入尚未属于的)。本模块只管一件相关的事: 同一只票在同一
篇文章里被提到多次, 按首次出现去重。

## 边界

除 `generate` 外**全是纯函数, 不碰 I/O 不碰账本** —— 切分与匹配都能脱离 AI 单测。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.services.watchlist_ocr.pipeline import ImportCandidate, build_instrument_lookups

logger = logging.getLogger(__name__)

#: 一次最多送审的正文长度。
#:
#: [R267] 从 6000 提到 20000: 输入换成整篇公众号文章之后, 6000 字会从中间截断 ——
#: 而这类文章**最有价值的板块清单往往排在后半段**(前半段是时事闲聊与免责声明),
#: 截断等于专挑重点丢。两万字覆盖得住绝大多数单篇。
MAX_TEXT_CHARS = 20000
#: 一篇文章里最多认多少只。超出通常意味着 AI 把行业成分股列表整个抄了下来。
MAX_MENTIONS = 120
#: 最多认多少个小分队。一篇文章分到几十个组通常是把每句话都当成了小标题。
MAX_GROUPS = 24
#: 分队名截断长度 —— 分组名是要显示在页签上的, 太长会把版面挤坏。
MAX_GROUP_NAME = 12

#: 存疑原因(展示给人看的短语, 不讲算法)。
WARN_CONFLICT = "名称与代码对不上, 未采信"
WARN_AMBIGUOUS = "这个名称对应多只证券"
WARN_UNKNOWN = "证券主数据里没有这个名称/代码"

_SYSTEM = """你是 A 股盘面助理。用户会粘来一篇 Markdown 正文(公众号文章 / 研报 / 复盘笔记),
你的唯一任务是**把文章里提到的个股挑出来, 并按文章自己的分节归好类**, 不做任何点评,
不要自己发明分类。

## 怎么切分节(小分队)

文章通常用**加粗小标题**或小节标题分板块, 例如 `**船舶**` `**军工**` `**科技**`;
小节里还可能有更细的一层, 例如 `光模块——剑桥科技` `液冷——远东股份、飞龙股份`。

- **group 取最细的那一层**: 剑桥科技的 group 是「光模块」, 不是「科技」
- group 名**照抄原文**, 不超过 12 个字, 不要自己造名字
- 实在找不到所属小节的(比如开头闲聊里顺带提到), group 填空字符串

## 挑哪些

1. 只挑**个股**(A 股股票、ETF)。指数(上证指数/全A指数/创业板指)、板块与题材名
   (光模块/半导体/稳定币)、行业、国家、人名、外号(懂王/波斯猫)、文章标题一律不要
2. **名称照抄原文**, 不要改写、不要补全、不要翻译; 原文写简称(如「中际」)就给简称
3. 原文里紧挨着写了代码(如"立讯精密(002475)")才填 code, **没写就留空**;
   **绝对不要凭记忆补代码** —— 记错的代码会把完全无关的票导进用户自选
4. 原文里**加粗**的股票名(如 `**松发股份**`)是作者重点标注的, starred 填 true,
   其余填 false
5. 同一只票在同一个小节里提到多次只给一条; 在**不同**小节里都出现则**每个小节各给
   一条** —— 用户的自选允许一只票同时属于多个分组
6. 一只都没提到就返回空数组

只输出一个 JSON 对象, 不要任何解释或代码块围栏:
{"mentions": [
  {"group": "船舶", "name": "松发股份", "code": "", "starred": true, "quote": "关注中国船舶、松发股份"},
  {"group": "光模块", "name": "剑桥科技", "code": "", "starred": true, "quote": "光模块——剑桥科技"}
]}
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

    **重名必须显式记下来而不是先到先得。** 先到先得会让「文章里提到 X」静默
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


#: [R267] 简称至少要这么长才拿去做前缀匹配。
#:
#: 两个字以下的"简称"前缀命中一只纯属巧合(比如「中」「新」), 而正文里这种一两个字
#: 的词几乎都不是股票。门槛压在两个字, 「中际」认得出来, 单字噪音进不来。
MIN_ABBR_LEN = 2


def build_prefix_lookup(symbol_to_name: dict[str, str]) -> dict[str, str]:
    """简称前缀 → symbol, **只收唯一命中的前缀**。纯函数。

    原文常写「中际」而主数据是「中际旭创」。这张表把每个名称的所有前缀都登记一遍,
    **凡是被两只以上共用的前缀一律剔除**: 「中际」只有中际旭创用 → 留; 「中航」被
    中航成飞/中航沈飞/中航电子共用 → 删。

    唯一性这道门是这张表能存在的全部理由 —— 没有它, 前缀匹配就退化成「挑一只最像的」,
    那比认不出来更糟: 认不出来会退回去让人自己定, 挑错了却是无声的。
    """
    counts: dict[str, str | None] = {}
    for symbol, name in symbol_to_name.items():
        key = _bare(normalize_name(name))
        for n in range(MIN_ABBR_LEN, len(key)):     # 不含全名本身 —— 那是 name_lookup 的活
            pre = key[:n]
            hit = counts.get(pre, "")
            if hit == "":
                counts[pre] = symbol
            elif hit != symbol:
                counts[pre] = None                  # 被共用, 作废
    return {k: v for k, v in counts.items() if v}


def _lookup_name(raw: str | None, lookup: dict[str, str], ambiguous: set[str],
                 prefixes: dict[str, str] | None = None) -> tuple[str | None, bool]:
    """名称 → (symbol, 是否重名)。

    三道: 原名 → 剥掉交易状态前缀的原名 → 唯一简称前缀。**全名永远优先于简称** ——
    否则一个恰好是别人前缀的正式名会被判给那只更长的票。
    """
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
    if prefixes:
        hit = prefixes.get(_bare(key))
        if hit:
            return hit, False
    return None, False


def parse_mentions(text: str | None) -> list[dict[str, Any]]:
    """AI 输出 → [{group, name, code, starred, quote}]。纯函数, 坏数据跳过而不是抛。"""
    from app.services.ai_json import extract_json_object

    obj = extract_json_object(text) or {}
    out: list[dict[str, Any]] = []
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
        out.append({
            "group": str(m.get("group") or "").strip()[:MAX_GROUP_NAME],
            "name": name,
            "code": code,
            "starred": bool(m.get("starred")),
            "quote": str(m.get("quote") or "").strip()[:40],
        })
    return out


def group_names(candidates: list[dict[str, Any]]) -> list[str]:
    """按出现先后列出小分队名(去重, 不含无归属的)。纯函数。

    保序要紧: 导入界面按这个顺序摆「小分队 → 目标分组」的映射行, 和用户读文章的
    顺序一致才对得上。
    """
    out: list[str] = []
    for c in candidates:
        for g in c.get("groups") or []:
            if g and g not in out:
                out.append(g)
            if len(out) >= MAX_GROUPS:
                return out
    return out


def resolve_mentions(
    mentions: list[dict[str, Any]],
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

    **一只票只出一条候选, 所属小分队合并进 `groups` 列表。** 同一只票在「军工」和
    「低空经济」两节都出现, 出的是一条带两个分队的候选, 导入时同时进两个分组 ——
    自选本来就是多组模型; 在这里拆成两条候选只会让人勾两次, 还会在"已在自选"的
    判断上互相打架。

    未匹配的按「名称+代码」去重, 免得同一个抽错的东西刷屏。
    """
    existing = existing_symbols or set()
    name_lookup, ambiguous = build_name_lookup(symbol_to_name)
    prefixes = build_prefix_lookup(symbol_to_name)

    out: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for m in mentions:
        raw_name, code = m.get("name", ""), m.get("code", "")
        by_name, is_ambiguous = _lookup_name(raw_name, name_lookup, ambiguous, prefixes)
        by_code = code_to_symbol.get(code) if code else None

        warn = ""
        if by_name and by_code and by_name != by_code:
            symbol = None
            warn = WARN_CONFLICT
        else:
            symbol = by_name or by_code
            if symbol is None:
                warn = WARN_AMBIGUOUS if is_ambiguous else WARN_UNKNOWN

        group = (m.get("group") or "").strip()
        key = symbol or f"?{normalize_name(raw_name)}|{code}"
        hit = seen.get(key)
        if hit is not None:
            _merge_into(hit, group, m)
            continue

        cand = ImportCandidate(
            code=code or (symbol.split(".", 1)[0] if symbol else ""),
            symbol=symbol,
            name=(symbol_to_name.get(symbol) if symbol else None) or raw_name or None,
            matched=bool(symbol),
            already_in_watchlist=bool(symbol and symbol in existing),
        )
        row = cand.to_dict()
        row["mention"] = raw_name or code
        row["quote"] = m.get("quote", "")
        row["warn"] = warn
        row["starred"] = bool(m.get("starred"))
        row["groups"] = [group] if group else []
        out.append(row)
        seen[key] = row
    return out


def _merge_into(row: dict[str, Any], group: str, m: dict[str, Any]) -> None:
    """同一只票的第二次提及: 只并分队与重点标记, 不动首次的名称与原文片段。

    首次那条留着是有意的 —— `quote` 是给人核对 AI 抽得对不对用的, 被后来的覆盖掉
    就等于让人去核对一个跟当初判断无关的句子。
    """
    if group and group not in row["groups"]:
        row["groups"].append(group)
    if m.get("starred"):
        row["starred"] = True


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
        # [R267] 文章里分好的小分队, 保持出现顺序 —— 导入界面据此摆映射行
        "section_names": group_names(candidates),
    }


async def generate(
    text: str,
    data_dir: Path,
    *,
    existing_symbols: set[str] | None = None,
) -> dict[str, Any]:
    """整条路: 正文 → AI 按小分队抽提及 → 主数据匹配 → 候选。失败返回 {"error": ...}。

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
        return {"error": f"这篇里没认出个股(AI 原文开头: {snippet or '空'}…)——可重试或换模型"}

    code_to_symbol, symbol_to_name = build_instrument_lookups(data_dir)
    candidates = resolve_mentions(mentions, code_to_symbol, symbol_to_name, existing_symbols)
    result = _finalize(clipped, candidates)
    if len(body) > MAX_TEXT_CHARS:
        result["truncated"] = True
    return result
