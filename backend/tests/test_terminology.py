"""[R279] 全系统名词表 —— **同一个东西只许有一个名字, 而且前后端一起扫**。

用户: 「全系统的表达都检查一次是否每个名词表述都统一了」。

## 为什么要有这张表, 而不是逐条 assert

R258 已经立过一条同形状的纪律(「界面上不再出现『贵不贵』」), 但它是**一条**
写死的断言, 而且**只扫前端 `.tsx/.ts`**。结果:

    backend/app/services/watchlist_urgency.py   「看『贵不贵』那一行」
    backend/app/indicators/keltner_geometry.py  「再争论『贵不贵』没有意义」

两处后端字符串**照样渲染到界面上**, 在守卫眼皮底下活了下来 —— 纪律定的范围
比守卫扫的范围大, 那多出来的部分等于没人管。这跟 R272 注册表漏登记、
R254 手写死键名单是同一个形状: **靠人记得的地方迟早漏。**

所以这里改成一张表 + 一次扫描, 两侧同时覆盖。加一个概念只要加一行。

## 扫的是「会渲染给用户看的字符串」, 不是全文

- 后端走 **AST**: 只取字符串字面量, 且**排除 docstring**。注释与文档里复述
  历史说法是允许的 —— 讲清楚"以前叫什么、为什么改"恰恰要写出旧名字。
- 前端走 `frontend_source.code_lines`(块级剥注释), 同一个道理。

## 排除项是**核查过的**, 不是图省事

见 `NOT_A_CONFLICT` —— 每一条都写明为什么它不算冲突。这张表过时是安全的
(顶多多扫一个不存在的名字), 而漏掉一个真冲突是危险的(界面上两个名字指同一件事,
读的人得先确认它们是不是一回事)。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.frontend_source import code_lines

ROOT = Path(__file__).resolve().parents[2]
BACKEND_APP = ROOT / "backend" / "app"
FRONTEND_SRC = ROOT / "frontend" / "src"

# ----------------------------------------------------------------------------
# 不扫的地方 —— 每一条都有理由
# ----------------------------------------------------------------------------
SKIP_DIRS = (
    # **作者的策略, 只读**。里面的「粘合」指 MA5/10/20 粘合, 与三档通道的
    # 「重合」是两个东西; 「评分」指策略因子评分, 与「把握分」也是两个东西。
    "strategy",
)
SKIP_FILES = {
    # 送给模型的 prompt, 不是界面。措辞要贴合模型而不是贴合界面用语,
    # 而且里面必须解释清楚每个量是怎么来的 —— 那正是界面上不许说的。
    "services/stock_signal.py",
    "services/livermore_service.py",
    "strategy/ai_generator.py",
}


def _rendered_backend() -> list[tuple[str, int, str]]:
    """后端**会渲染出去**的中文字符串。AST 取字面量, 排除 docstring。"""
    out: list[tuple[str, int, str]] = []
    for p in BACKEND_APP.rglob("*.py"):
        rel = str(p.relative_to(BACKEND_APP))
        if any(part in SKIP_DIRS for part in p.relative_to(BACKEND_APP).parts[:-1]):
            continue
        if rel.replace("\\", "/") in SKIP_FILES:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                       # pragma: no cover
            continue
        docs = {
            ast.get_docstring(n, clean=False)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))
        }
        for n in ast.walk(tree):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value not in docs and re.search(r"[一-鿿]", n.value)):
                out.append((rel, n.lineno, n.value))
    return out


def _rendered_frontend() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for p in FRONTEND_SRC.rglob("*.ts*"):
        rel = str(p.relative_to(FRONTEND_SRC))
        for i, ln in enumerate(code_lines(p.read_text(encoding="utf-8")).splitlines(), 1):
            if re.search(r"[一-鿿]", ln):
                out.append((rel, i, ln))
    return out


# ----------------------------------------------------------------------------
# 名词表: 概念 → 正名 + 不许再出现的旧名
# ----------------------------------------------------------------------------
#
# 只收**核查过确实是同一个东西**的别名。多收一个会把合法文本判成违规,
# 那比漏收更烦人 —— 与 R272 的存储注册表(宁可多收)取舍方向相反, 因为那边
# 漏一个会让体检说假话, 这边多一个只会挡住写文案的人。
TERMS: list[tuple[str, str, tuple[str, ...]]] = [
    # 概念,      正名,       不许出现的别名
    ("三档通道位置合成的那一句结论", "通道结论", ("贵不贵", "位置结论")),
    # [R285] 「这套判定在这只票上灵不灵」的五个档位名, 各加两个字点明是**判断**
    # 而不是**动作**。用户指着「只能用来买」说: 「这类词都加多两个字, 比如
    # 只能用来判断买, 这样表述清楚」。
    #
    # 原来那批名字有歧义 —— 「只能用来买」读起来像在叫人买入, 而它的意思是
    # 「这套判定在这只票上只有买那一侧灵」。**它评的是判定本身好不好使, 不是
    # 今天该干什么**; 少这两个字, 一个统计结论就被读成了操作指令。
    ("这套判定在这只票上两侧都灵", "买卖都能判断", ("买卖都能用",)),
    ("这套判定在这只票上只有买侧灵", "只能用来判断买", ("只能用来买",)),
    ("这套判定在这只票上只有卖侧灵", "只能用来判断卖", ("只能用来卖",)),
    ("这套判定在这只票上是反的", "判断买的反而更差", ("说买的反而更差",)),
    ("这套判定在这只票上没有区分度", "买卖都判断不了", ("看不出差别",)),
    # [R286] 「今天六态状态变了」这件事, 系统里原来有两个名字: 复盘逐日表叫
    # 「转折」, 决策台「该动了」那一档叫「刚变盘」。用户要走势列也标出转折
    # (「走势这一列还要显示今天是不是转折」), 一标出来同一行里就会同时出现
    # 两个词说同一天。统一到「转折」, 两个理由:
    #   · 用户指着复盘那个标记提的需求, 「转折」是他嘴里的词;
    #   · 「变盘」在作者内置策略里是**另一件事**(均线粘合突破的变盘启动点),
    #     那些文件只读, 所以该让路的是我这边。
    # 只禁「刚变盘」不禁「变盘」—— 后者在作者策略和通道文案里另有合法用法,
    # 一禁就会把合法文本判成违规(见本表开头的取舍)。
    ("六态状态今天翻转了", "转折", ("刚变盘",)),
]

# 核查过、**确认不是冲突**的同形词 —— 写下来免得下次又被当成问题重查一遍。
NOT_A_CONFLICT = {
    "转折后第N天/已N天": (
        "[R290] **两个锚点, 不是两个说法**。走势列的「转折后第 N 天」从**六态转折那天**"
        "数起(用户点名要这个说法: 「这类词统一改成出现转折后的第几天」); 结论徽标的"
        "「已N天」是**这一档通道结论**连着多久 —— 两段的起点根本不是同一天, 合成一个"
        "说法反而会让人以为是同一个数。R249 当年把它们统一, 是因为那时走势列写的也是"
        "同一形状的「已N天」; 现在走势列换了锚点, 分开叫才准。"
        "**同一个数只印一处**这条没变, 由 `test_R290_六态天数只印一处且是转折口径` 钉着。"
    ),
    "跟随收益/跟着做": (
        "[R287] **两个口径, 不是两个名字**。作者的 `livermore.backtest_thresholds` "
        "出的「跟随收益」是**转折日收盘**进出(个股分析页的阈值网格在用); 复盘页新增的"
        "「跟着做」是**转折次日开盘**进出。转折要等收盘价定下来才算得出来, 拿同一根"
        "收盘价成交等于假设你提前知道了收盘之后才知道的事 —— 所以两个数必然不同, "
        "差的就是隔夜跳空。统一成一个名字反而会制造「同一个词两个数」。"
        "两处都已在界面上写明各自的口径。"
    ),
    "超额收益/多赚": (
        "[R287] 「超额收益」在本仓库指**个股 vs 大盘基准**(trend_template.rs_6m、"
        "keltner_service); 「按转折买卖」那一栏的「多赚」指**跟着做 vs 一直拿着同一只票**。"
        "参照物不同, 所以刻意没沿用「超额收益」这个词。"
    ),
    "评分": "策略因子评分(strategy/ 与 ScoringEditor), 与今日总览的「把握分」是两套东西",
    "粘合": "作者策略里的 MA5/10/20 粘合, 与三档通道的「重合」不是一回事",
    "利弗莫尔趋势": "外部页面的默认名字(用户可改), 不是六态判定本身",
    "keltner": "字段名/接口路径/日志, 不作为界面文案出现",
    "止盈线/止损线": "「出场线」在不同阶段的两个具体名字, 本来就该分开叫",
    "该动了/要动的": "同一判定的动词与名词形态, 不构成误解; 「只看要动的」是用户自己的措辞",
    "通道态势": (
        "**这一条是这张表自己抓到的**: 第一版把它当成「通道结论」的旧名收进了别名表, "
        "一跑就红在 `decisionBoardExportColumns.ts` 上。查下来它labels 的是"
        "「阶段 + 间距 + 快慢 + 挤了几天」这一束几何量, 而同一份导出里另有一列 "
        "`verdict` 就叫「结论」—— 两者是不同的东西, 不是一个东西的两个名字。"
        "多收一个别名会把合法文案判成违规, 正是这张表最该防的失误。"
    ),
}


@pytest.fixture(scope="module")
def rendered():
    return _rendered_backend(), _rendered_frontend()


def find_hits(words, rendered) -> list[str]:
    """在**两侧**渲染文本里找这些词。抽成函数是为了能被自校验直接调用 ——
    见 `test_R279_两侧都真的接在检查里`。"""
    be, fe = rendered
    out: list[str] = []
    for w in words:
        for side, rows in (("后端", be), ("前端", fe)):
            for f, i, v in rows:
                if w in v:
                    out.append(f"[{side}] {f}:{i} 用了「{w}」")
    return out


@pytest.mark.parametrize("concept,canonical,aliases", TERMS,
                         ids=[t[1] for t in TERMS])
def test_R279_旧名字不许再出现在界面上(concept, canonical, aliases, rendered):
    """一个东西两个名字, 读的人得先确认它们是不是一回事 —— 那一步本不该存在。"""
    bad = find_hits(aliases, rendered)
    assert not bad, (f"「{concept}」的旧名字还在界面上(正名: {canonical}):\n  "
                     + "\n  ".join(bad))


def test_R279_两侧都真的接在检查里(rendered):
    """**这一条守的是 R258 那个病本身。**

    R258 的纪律是「界面上不再出现『贵不贵』」, 而它的守卫**只扫前端** ——
    于是后端两处照样渲染到界面, 在守卫眼皮底下活了下来。

    危险在于: 后端清干净之后, **把扫描面缩回只看前端也照样全绿**。光测"现在没有
    违规"是抓不到这种退化的。所以这里各塞一个**只在那一侧存在**的已知词进去,
    确认两侧都真的被查了。
    """
    be_only = "再争论「通道结论」没有意义"        # 只在 keltner_geometry.py 里
    fe_only = "只看要动的"                        # 只在决策台 tsx 里
    for word, side in ((be_only, "后端"), (fe_only, "前端")):
        hits = find_hits((word,), rendered)
        assert hits, f"{side}这一侧没接进检查 —— 找不到已知存在的「{word}」"
        assert any(h.startswith(f"[{side}]") for h in hits), \
            f"「{word}」命中的不是{side}: {hits}"


def test_R279_正名本身还在():
    """反面: 别把旧名删干净之后连正名也一起没了。"""
    be, fe = _rendered_backend(), _rendered_frontend()
    for _concept, canonical, _aliases in TERMS:
        hit = any(canonical in v for _, _, v in be) or any(canonical in v for _, _, v in fe)
        assert hit, f"正名「{canonical}」在界面上一次都没出现"


def test_R279_这道闸真的扫得到后端():
    """**守卫自己也要validated。**

    R258 那条纪律失效不是因为写错了断言, 而是因为**扫的范围比纪律小** ——
    它只看前端, 于是后端两处「贵不贵」在它眼皮底下活了下来。这里塞一个已知
    存在的后端字符串进去, 确认后端这一侧真的被扫到了。
    """
    be = _rendered_backend()
    assert be, "一条后端字符串都没取到 —— AST 那一步没生效"
    # keltner_geometry 的 phase() 里确实有这句(改名之后的正名版本)
    hit = [v for f, _i, v in be
           if f.endswith("keltner_geometry.py") and "再争论「通道结论」没有意义" in v]
    assert hit, "取不到那句已知存在的后端渲染文本 —— 扫描面还是漏了后端"


def test_R279_docstring不算界面():
    """注释与文档里复述旧说法是**允许的** —— 讲清楚"以前叫什么、为什么改"
    恰恰要写出旧名字。扫到 docstring 会让这类说明写不成。"""
    be = _rendered_backend()
    from app.indicators import keltner_geometry as kg
    doc = kg.__doc__ or ""
    assert doc, "模块 docstring 没了?"
    assert not [v for _f, _i, v in be if v == doc], "docstring 被当成渲染文本扫了"


def test_R279_排除项都写了理由():
    """排除表过时是安全的, 但**没写理由的排除项**下次没人敢动, 也没人知道
    它当初为什么在这儿 —— 那就变成了永久的洞。"""
    for k, why in NOT_A_CONFLICT.items():
        assert why and len(why) > 8, f"排除项「{k}」没写清楚理由"


def test_R279_作者禁区没被扫进来():
    """`strategy/` 是只读的。把它扫进来的话, 一条命中就逼着去改作者的文件 ——
    而那正是本 fork 最硬的一条纪律。"""
    be = _rendered_backend()
    assert not [f for f, _i, _v in be if f.startswith("strategy")], \
        "作者的 strategy/ 被扫进来了"


def test_R279_台账落了加速度原始值():
    """[R278 的后续] 界面分档(±0.05)与主升浪第⑤条(a1 >= 0)之间有一条 16.1%
    的缝, 而台账只存三档的码 —— 落进缝里的那些天全被压成同一个 steady,
    事后无从回答它该归哪边。

    **落原始值而不是分箱**: 现在定分箱边界又是一次没有证据的猜测, 而原始值
    事后可以任意分箱。只记不反馈 —— 不进分, 不改判定。
    """
    from app.api import today
    src = Path(today.__file__).read_text(encoding="utf-8")
    assert '"accel_a1": ((geo or {}).get("accel") or {}).get("a1")' in src, \
        "台账没落加速度原始值 —— 那条缝将永远只能靠猜"


def test_R279_原始值没被登记成分组维度():
    """连续值分不了组。登记进去只会让台账碎成一行一个分组。"""
    from app.services import score_ledger
    src = Path(score_ledger.__file__).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert '"key": "accel_a1"' not in code, "原始值被登记成分组维度了"


def test_R280_AGENTS里那条规矩指向的是这个文件():
    """AGENTS.md 第 12 条把这份名词表写成了执行入口。**指向不存在的文件 = 又一条
    说假话的注释** —— 这仓库刚因为一句「与 SPREAD_CURVE 对齐」栽过(那个名字全仓
    不存在)。规矩与它的执行处得对得上。
    """
    doc = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "全局表达一致" in doc, "AGENTS.md 里那条规矩没了"
    rel = "backend/tests/test_terminology.py"
    assert rel in doc, f"规矩没指向执行处({rel})"
    assert (ROOT / rel).exists()
