"""[fork 增强] 界面上**不许泄露算法** —— 只讲怎么读, 不讲怎么算。

用户原话(R198): 「点击就显示这些东西的含义, 但是**不能告诉别人具体是怎么算出来的**」。
这与把 Keltner 改名成「量化波动通道」是同一个目的: 指标本身是要藏的。

[R259] **决策台角上那个感叹号(词汇表)删掉了** —— 用户: 「删除掉感叹号」。
`GlossaryDialog.tsx` 随之成了孤儿文件, 一并删(守则 R198: 不留没人调的死代码)。
守它那一半测试跟着退役, **但这一条纪律本身留着** ——

    藏不藏得住取决于**最松的那一处**, 不是最严的那一处。

R200 那一轮真的在别处翻出过泄露: 决策台悬停里写着「破轨门槛 2 / 2.5 / 3」,
今日总览的 title 里写着「三条带的交集 / 短带宽度」。R201 又在**导出的 HTML**
里翻出「短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR」—— 那是所有面里
最该守的一个, 因为屏幕上的东西只有本人看得到, 导出的文件是拿去发给别人的。

文案是会漂的, 所以拿测试扫。这是**前端文件的内容检查**, 放在后端测试里只是
因为本仓库没有前端测试运行器(package.json 里没有 vitest/jest)。
"""
import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
_FRONT = _SRC / "components" / "stock-analysis"


# 泄露算法的几类词。分开列是为了失败时一眼看出泄的是哪一类。
FORBIDDEN = {
    "均线周期": ["MA20", "MA60", "MA120", "20 日", "60 日", "120 日", "20日", "60日", "120日"],
    "波动倍数": ["ATR", "2 倍", "2.5 倍", "3 倍"],
    "阈值": ["0.8", "80%", "1.35", "5 个", "2 天", "3 天", "0.05"],
    "构造/公式": ["交集", "除以", "均值", "RMS", "归一化", "滤波", "带通", "傅里叶",
                "Z 变换", "群延迟", "分位", "回归", "标准差", "方差"],
    "指标本名": ["Keltner", "keltner", "利弗莫尔", "Livermore", "Minervini"],
}


# ================================================================
# [R200] 把同一把尺子量到**所有出现在屏幕上、以及能外传出去**的通道文案
#
# R200 那一轮真的在别处翻出了泄露 —— 决策台悬停里
# 写着「破轨门槛 2 / 2.5 / 3」, 今日总览的 title 里写着「三条带的交集 / 短带
# 宽度」「最高/最低收盘 ≤ 1.35」「(9.5:20:30)」。那几处和感叹号一样是**用户
# 眼睛能看到的**, 藏不藏得住取决于最松的那一处, 不是最严的那一处。
#
# 判据仍是"只查显示部分":
# 每个文件都从各自的第一段可显示内容开始扫, 文件头的注释是写给维护者的。

# 文件 → 从哪个标记之后才算"显示区"
SURFACES = {
    _FRONT / "decision-board" / "cells.tsx": "function geoLines",
    # [R269] 三个区块合并重排后锚点跟着挪。挪到 VerdictHeader 是**扩大**了扫描面:
    # 老锚点 ChannelPanel 排在阶段卡与位置结论卡之后, 那两块的文案一直没被扫到。
    _FRONT / "StockReviewDialog.tsx": "function VerdictHeader",
    _SRC / "components" / "today" / "OpportunityTable.tsx":
        '<span className="text-foreground/90">量化波动通道</span>',
    # [R201] **导出的 HTML 是所有面里最该守的一个** —— 屏幕上的东西只有本人看得到,
    # 导出的文件是拿去发给别人的。而它恰恰是 R200 那一轮漏掉的: 页头说明里
    # 白纸黑字写着「短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR」。
    # 这条规则的教训就是"扫描面要跟着**能外传的东西**走, 不是跟着屏幕走"。
    _SRC / "lib" / "decisionBoardHtmlExport.ts": "export function buildBoardHtml",
    # [R292] 「说明」抽屉 —— 它整篇就是解释这些词是什么意思, **是全仓库最容易
    # 顺手把算法一起讲出来的地方**。R259 删掉的那个感叹号词汇表当年守的就是它,
    # 现在这块内容回来了, 守卫也得跟回来(纪律管到哪儿守卫就得扫到哪儿, R279)。
    _FRONT / "ReviewHelpSheet.tsx": "export function HelpButton",
}

# [R292] 后端也有一处**释义文案**: 六态那六句「是什么意思」。前端扫不到它 ——
# 它是后端字符串, 运行时才到界面上。R279 吃过一模一样的亏(纪律管前后端, 守卫
# 只扫前端, 后端两处就在眼皮底下活了下来), 所以这里把那个文件一并扫了。
_BACKEND_SURFACES = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "glossary.py",
)

# 显示区里也躲不开的技术词(它们是数据本身或纯样式), 逐条豁免而不是整类放行。
_ALLOW = ("gain_atr", "compress_avg", "compress_days", "atr", "energy.share",
          "geo.d", "font-mono", "text-muted")


_COMMENT = re.compile(r"/\*.*?\*/|(?<![:'\"])//[^\n]*", re.S)


def _visible(path: Path, marker: str) -> str:
    """显示区 = 标记之后, **去掉注释**。

    注释是写给维护者的, 该讲清楚算法; 去掉它们才分得清"泄给用户"和"写给自己"。
    这也是这组测试第一版的毛病 —— 整段扫下去, JSX 里那些 `{/* ... */}` 的推导
    说明全被当成泄露, 逼着人把注释删掉, 那是把有用的东西删了去迁就测试。
    """
    src = path.read_text(encoding="utf-8")
    assert marker in src, f"{path.name} 里找不到起点标记「{marker}」—— 测试该跟着改"
    body = _COMMENT.sub(" ", src[src.index(marker):])
    # 再滤一次: 只留**带中文的行**。这个仓库里显示给用户的字一律是中文, 而
    # `KeltnerBand` / `KELTNER_CLS` 这类是 TS 类型与样式常量 —— 它们不在屏幕上,
    # 拿泄露去卡它们只会逼人给类型改名, 那是为了测试改代码。
    body = "\n".join(ln for ln in body.splitlines()
                     if any("\u4e00" <= ch <= "\u9fff" for ch in ln))
    for tok in _ALLOW:
        body = body.replace(tok, "")
    return body


@pytest.mark.parametrize("path,marker", sorted(SURFACES.items(), key=lambda kv: kv[0].name))
@pytest.mark.parametrize("kind", ["均线周期", "波动倍数", "阈值", "构造/公式", "指标本名"])
def test_界面上其它通道文案同样不泄露(path: Path, marker: str, kind: str):
    hit = [w for w in FORBIDDEN[kind] if w in _visible(path, marker)]
    assert not hit, f"{path.name} 的「{kind}」泄露了: {hit}"


# ================================================================
# [R200] 大白话 —— 「别用拉开脱开这种词, 不够通俗易懂」
#
# 上面那组守的是"别说太多", 这一组守的是"别说得没人懂"。两件事都会让这些
# 指标白做: 前者暴露, 后者看不明白。

JARGON = ["拉开", "脱开", "粘合", "撕裂", "分离度", "偏离度", "频段",
          "归一化", "带通", "尺度撕裂", "压缩指数"]


@pytest.mark.parametrize("path,marker", sorted(SURFACES.items(),
                                              key=lambda kv: kv[0].name))
def test_界面文案不用行话(path: Path, marker: str):
    hit = [w for w in JARGON if w in _visible(path, marker)]
    assert not hit, f"{path.name} 里还有行话: {hit} —— 换成「挤在一起/走开/间距」这类说法"


def test_后端给界面的那几句话也是大白话():
    """`explain()` / `phase()` / `event()` 的正文是直接摆在界面上的。"""
    from app.indicators import keltner_geometry as kg

    geo = {"accel": {"level": kg.ACCEL_UP, "gain_atr": 1.4, "a1": 0.15},
           "spread": 2.2, "compress": 0.1, "torn": False, "nested": False,
           "stack": kg.STACK_BULL, "d": {"s": 1.2, "m": 2.0, "l": 3.1}}
    runs = {"compress_days": 0, "above_run": 4, "below_run": 0}
    # [R212] explain 现在一行一条 {label,value,why} —— 三样都要扫
    texts = [x for r in kg.explain(geo, runs) for x in (r['label'], r['value'], r['why'])]
    ph = kg.phase(geo, runs)
    texts += [ph["cn"], ph["why"], ph["watch"]]
    ev = kg.event(state="UT", duration=3, geo=geo, run=runs)
    texts += [ev["cn"], ev["why"]]
    texts += list(kg.EVENT_CN.values()) + list(kg.PHASE_CN.values())
    texts += [t for pair in kg.COMBO_NOTES.values() for t in pair]
    blob = " ".join(texts)
    hit = [w for w in JARGON if w in blob]
    assert not hit, f"后端文案里还有行话: {hit}"
    # 单位也不点名 —— 与改名成「量化波动通道」同一个目的
    assert "ATR" not in blob, "界面文案里不该出现指标本名的单位"


@pytest.mark.parametrize("kind", list(FORBIDDEN))
@pytest.mark.parametrize("path", _BACKEND_SURFACES, ids=lambda p: p.name)
def test_R292_后端的释义文案也不许讲算法(path: Path, kind: str):
    """六态那六句「是什么意思」是**新写的界面文案**, 而且住在后端 ——
    前端那把尺子够不着它。

    这正是 R279 那一课的形状: 纪律管前后端两侧, 守卫只扫一侧, 另一侧就在
    眼皮底下活下来。所以这条单独扫这个文件的**字符串**(不含 docstring 与注释:
    那些是写给维护者的, 本来就该讲清楚)。
    """
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    texts = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docs]
    blob = "\n".join(texts)
    bad = [w for w in FORBIDDEN[kind] if w in blob]
    assert not bad, f"{path.name} 的释义文案里泄露了{kind}: {bad}"


def test_R292_说明抽屉的词条真的来自后端():
    """反面: 前端誊抄一份就会漂 —— 底层改了措辞那份就开始说假话, 而且不会报错。
    (R203 的 27 格速查表当初就是为这个理由做成端点的。)"""
    from tests.frontend_source import code_of
    src = code_of("components/stock-analysis/ReviewHelpSheet.tsx")
    assert "api.glossary()" in src, "说明抽屉没走后端那份词条"
    # 六态那六个名字不许出现在**代码**里 —— 出现即意味着誊抄。
    # **先剥注释**: 文件头那段说明里举「自然回撤」当例子是应该的(讲清楚这个抽屉
    # 是干什么用的), 它不渲染。第一版没剥就直接扫, 当场被自己的注释绊倒。
    for name in ("上涨趋势", "自然回升", "次级回升", "次级回撤", "自然回撤", "下跌趋势"):
        assert name not in src, f"「{name}」被誊抄进前端了 —— 名字的正主在后端"
