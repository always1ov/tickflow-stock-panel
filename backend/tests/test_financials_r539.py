"""[fork R539] 财务分析整改: 同步状态收成一条、多期报告一张表、手机不折不横滑、不可用提示合一段。

用户: 「剩下的所有页面都需要整改」, 看过财务分析方案图后「确认」。只改表达, 数据/同步/AI 财务分析一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of

PAGE = "pages/Financials.tsx"
DETAIL = "components/financials/StockFinancialDetail.tsx"


def test_R539_同步状态是一条_四样信息都在():
    page = code_of(PAGE)
    assert "lg:grid-cols-5 lg:divide-x" in page
    assert "text-xl font-semibold tabular-nums" not in page, "同步状态又成了大号数字卡"
    for anchor in ("fmtBigNum(info?.rows", "fmtBigNum(info?.symbols", "lsTime", "handleSync(key)"):
        assert anchor in page, f"同步状态少了 {anchor}"


def test_R539_未选股不再重复一块空状态():
    page = code_of(PAGE)
    assert "未选择股票" not in page
    assert "搜索个股查看详细财务数据" in page


def test_R539_按钮与颜色走令牌_不设宽度上限():
    page = code_of(PAGE)
    assert "bg-gradient-to-r" not in page and "emerald" not in page
    assert "max-w-[1440px]" not in page


def test_R539_不可用提示合成一段():
    page = code_of(PAGE)
    assert "关于数据源" not in page
    assert "前往数据源配置" in page


def test_R539_多期一张表_单期三列_手机一期一块():
    d = code_of(DETAIL)
    assert "rows.length === 1 ?" in d
    assert "<table" in d and 'max-sm:hidden' in d and 'space-y-5 sm:hidden' in d
    # 手机上分栏名与报告期不折行
    assert "shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2" in d
