"""[R429] 个股弹窗的新头部(用户给的排版图, 重做弹窗的第一块)。

用户: 「我想重做整个弹窗, 我发你一点就修改一点」→ 头部的图。定了的几条:
新头部加在最前面、旧顶栏先留着; 60 / 120 / 250 日放头部, 与复盘页同一个值;
补一个 AI 四维分析入口; 「结论」和两个新按钮先占位。
"""
import re

from tests.frontend_source import code_of

HERO = "components/stock-preview/PreviewHero.tsx"
PILL = "components/stock-preview/pill.ts"   # [R430] 按钮样式从头部挪出来, 新区块共用
DLG = "components/StockPreviewDialog.tsx"


def _const(src: str, name: str) -> str:
    m = re.search(rf"const {name} = ([^\n]+(?:\n  \+ [^\n]+)*)", src)
    assert m, f"找不到 {name}"
    return m.group(1)


def test_R429_新头部在最前面_旧顶栏还在():
    dlg = code_of(DLG)
    assert "<PreviewHero" in dlg, "弹窗里没有新头部"
    # 用户: 「后面等我叫你删除旧的」—— 在那之前旧顶栏得在, 而且排在新头部之后
    assert dlg.index("<PreviewHero") < dlg.index("onClick={() => setView('levels')}"), (
        "新头部没排在旧顶栏前面")


def test_R429_天数是同一个值_头部与复盘页共用():
    dlg = code_of(DLG)
    hero = dlg[dlg.index("<PreviewHero"):]
    hero = hero[:hero.index("/>")]
    assert "days={reviewDays} onDaysChange={setReviewDays}" in hero
    panel = dlg[dlg.index("<StockReviewPanel"):]
    panel = panel[:panel.index("/>")]
    assert "days={reviewDays}" in panel and "onDaysChange={setReviewDays}" in panel, (
        "复盘页没接弹窗持有的天数 —— 头部点了 60 日, 复盘页还是 120 日")
    assert "export const HERO_DAYS = [60, 120, 250] as const" in code_of(HERO)


def test_R429_切到另一只票天数复位():
    """原来复盘页 `key={symbol}` 重建会把天数一并复位; 提到弹窗里之后得自己复位。"""
    dlg = code_of(DLG)
    eff = dlg[dlg.index("prevSymbolRef.current = symbol"):]
    eff = eff[:eff.index("}, [symbol])")]
    assert "setReviewDays(HERO_DAYS_DEFAULT)" in eff, "切股时天数没复位 —— 上一只的「60 日」带到了下一只"
    assert "useState<number>(HERO_DAYS_DEFAULT)" in dlg


def test_R429_AI入口与占位按钮():
    hero = code_of(HERO)
    assert "onClick={() => onAiAnalyze(symbol, name)} disabled={aiBusy}" in hero
    assert "todo('导出复盘')" in hero, "「导出复盘」占位按钮不见了"
    # [R447] 用户: 「删掉导出复盘后面的使用说明按钮, 不需要了」
    assert "使用说明" not in hero, "「使用说明」按钮又回来了"


def test_R429_星星方框不叠冲突的内边距():
    """第一版方框写成 `${PILL} w-8 px-0`, 而 PILL 里有 `px-3`: 同一元素上两个 px-*
    谁生效看样式表先后, 结果 `px-3` 赢, 32px 的方框左右各吃掉 12px, 星星被挤成 6px 宽。"""
    hero = code_of(HERO)
    styles = code_of(PILL)
    box = _const(styles, "BOX")
    square = _const(styles, "SQUARE")
    assert not re.search(r"\bpx-", box), "公共形状里带了横向内边距 —— 方框会跟它打架"
    assert not re.search(r"\bpx-", square), "方框自带了横向内边距"
    assert not re.search(r"\btext-(foreground|muted)\b", box + square), "公共形状里带了字色"
    consts = {n: _const(styles, n) for n in ("BOX", "PILL", "SQUARE")}
    # [R449] 两种状态的配色挪进了全站按钮, pill.ts 里只是转出去
    btn = code_of("components/ui/Button.tsx")
    consts["PILL_IDLE"] = _const(btn, "OUTLINE")
    consts["PILL_ON"] = _const(btn, "SELECTED")

    def expand(expr: str) -> str:
        for _ in range(4):  # PILL / SQUARE 里还套着 ${BOX}
            expr = re.sub(r"\$\{(\w+)\}", lambda m: consts.get(m.group(1), ""), expr)
        return expr

    uses = re.findall(r"[cC]lassName=\{([^}]*(?:\}[^}]*)*?)\}>", hero)
    assert uses, "没找到任何 className"
    for expr in uses:
        full = expand(expr) + " " + " ".join(consts[n] for n in consts if re.search(rf"\b{n}\b", expr))
        pads = set(re.findall(r"\bpx-[\w.]+", expand(full)))
        assert len(pads) <= 1, f"同一个元素叠了多个横向内边距: {pads} ← {expr}"


def test_R472_新头部有刷新_与旧顶栏是同一个函数():
    """[R472] 用户指着量化MACD 副图上「稍后点右上角刷新重试」: 「图片里面提到的刷新按钮没有了,
    加回来」。刷新原来只在旧顶栏, 旧顶栏自 R432 起排到了新块后面, 右上角看不见它。"""
    hero, dlg = code_of(HERO), code_of(DLG)
    assert "onClick={onRefresh}" in hero and "<RefreshCw" in hero, "新头部没有刷新按钮"
    call = dlg[dlg.index("<PreviewHero"):dlg.index("/>", dlg.index("<PreviewHero"))]
    assert "onRefresh={handleRefresh}" in call, "新头部的刷新没接到弹窗那一个 handleRefresh"
    # 那句提示说的就是量化MACD: 刷新得真的重取它
    fn = dlg[dlg.index("const handleRefresh"):dlg.index("const selectIntradayDays")]
    assert "QK.stockQuantMacd(symbol)" in fn, "刷新不重取量化MACD —— 图上的「点右上角刷新重试」是空话"
