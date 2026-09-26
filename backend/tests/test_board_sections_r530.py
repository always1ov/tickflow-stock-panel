"""[fork R530] 个股分析只放今天要看的 —— 三段固定名单, 四个筛选撤掉, 判定缺失时不拿全量冒充。

用户: 「我觉得自选页面和个股分析页面有点重复了。希望个股分析页面只显示那些我需要看的, 不然一大堆。
自选页面里面才是一大堆, 当做个收藏夹」; 「替我选择, 我的核心需求就是个股分析页面只看那些我需要看的」。

自选是仓库, 个股分析是工作台。工作台三段: ① 今天要动的(急迫度前四档) ② 持有·无事 ③ 计划中·贴轨(焦点名单过
推送门的两档, 含钉住)。一只票只出现一次, 按①②③归段; 观察档、无事的票不在这一页出现, 要看就搜。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"


def _sections_block(code: str) -> str:
    i = code.index("const sections = useMemo(")
    return code[i:code.index("const sortedRows = useMemo(", i)]


def test_R530_三段固定名单_一只票只出现一次():
    blk = _sections_block(code_of(BOARD))
    assert "rows.filter((r) => r.urg && r.urg.level !== 'idle')" in blk, "①今天要动的 = 急迫度非无事档"
    assert "rows.filter((r) => r.held && !inAct.has(r.symbol))" in blk, "②持有·无事 要排掉已经在①里的"
    assert "if (r.held || inAct.has(r.symbol)) return false" in blk and "t === 'plan' || t === 'band'" in blk, \
        "③计划中·贴轨 = 焦点名单 plan/band 两档, 排掉①②"
    for title in ("'今天要动的'", "'持有 · 无事'", "'计划中 · 贴轨'"):
        assert title in blk, f"段名 {title} 没了"


def test_R530_急迫度没回来时不拿全量冒充():
    """原来「只看要动的」在判定缺失时一律放行 —— 接口一超时, 202 只全体变成"要动的"(用户手机截图)。"""
    code = code_of(BOARD)
    blk = _sections_block(code)
    assert "const act = urgencyReady ? rows.filter(" in blk, "判定没回来时①必须是空的, 不是全量"
    assert "const urgencyReady = !!urgencyQ.data" in code
    # 空着的①要明说是哪种空
    assert "'急迫度没算出来 —— 点右上角刷新再试'" in code
    assert "'急迫度还在算…'" in code
    assert "'今天没有要动的'" in code, "「今天没事」本身就是信息, 得写出来"


def test_R530_四个筛选撤干净():
    code = code_of(BOARD)
    for dead in ("actionableOnly", "flippedOnly", "heldOnly", "groupFilter", "WatchlistGroupMenu",
                 "boardGroupFilter", "boardActionableOnly", "G_UNGROUPED", "inGroup("):
        assert dead not in code, f"筛选残余: {dead}"
    for label in ("只看要动的", "只看转折", "只看持有"):
        assert f">{label}" not in code and f"'{label}'" not in code, f"按钮文案还在: {label}"
    store = code_of("lib/storage.ts")
    assert "boardGroupFilter:" not in store and "boardActionableOnly:" not in store, "本地偏好键没删"


def test_R530_焦点名单走同一个查询键_不另立口径():
    code = code_of(BOARD)
    assert "useQuery({ queryKey: QK.focus, queryFn: api.focusList, staleTime: 30_000 })" in code
    assert "m.set(it.symbol, it.effective)" in code, "要用钉住/静音之后的有效档(effective), 不是原始档"


def test_R530_表头的数与自选总数一直都写():
    code = code_of(BOARD)
    assert "{sortedRows.length} 只 · 持有 {heldInView}" in code
    assert '<span className="opacity-60"> · 自选共 {totalRows}</span>' in code
    # 持有数与「N 只」出自同一批(三段拼起来的那批)
    assert "const heldInView = useMemo(() => sortedRows.filter((r) => r.held).length, [sortedRows])" in code


def test_R530_定位不到时说一声_不静默():
    code = code_of(BOARD)
    i = code.index("const locate = (sym: string, explicit: boolean) => {")
    # code_of 剥掉了注释, 结束锚取下一个 useEffect(补做待定位那一段)
    blk = code[i:code.index("useEffect(", i)]
    assert "今天不在这一页的名单里" in blk and "用搜索打开它" in blk
    assert "setActionableOnly" not in blk and "setGroupFilter" not in blk


def test_R530_六态接口上限与兄弟端点一致():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "api" / "stock_analysis.py").read_text(encoding="utf-8")
    caps = re.findall(r'if s\.strip\(\)\]\[:(\d+)\]', src)
    assert caps and all(c == "300" for c in caps), f"三个批量端点的上限不一致: {caps}(原来 /trends 是 200, 用户 202 只自选被静默截掉)"
