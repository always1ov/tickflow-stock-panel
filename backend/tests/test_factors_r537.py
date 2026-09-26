"""[fork R537] 因子页整改: 分栏条走共用 PageTabs、因子库一行一个且手机不横滑、算子说明不折行。

用户: 「剩下的所有页面都需要整改」, 看过因子页方案图后「确认」。只改表达, 因子/公式/检验逻辑一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R537_分栏条走共用件():
    page = code_of("pages/Factors.tsx")
    assert "<PageTabs" in page and "PageTabDef" in page
    assert "SEG_ITEM" not in page, "又手抄了一份分栏条"
    # 切栏仍清掉 focus / edit, 深链键名不变
    assert "next.delete('focus')" in page and "next.delete('edit')" in page


def test_R537_因子库_名字与id一行_手机一行一块():
    lib = code_of("pages/factors/FactorLibrary.tsx")
    assert "sm:min-w-[760px]" in lib and "min-w-[760px] text-xs" not in lib, "手机上又成了横滑的宽表"
    assert "max-sm:hidden', TH_ROW" in lib, "手机上表头没藏"
    assert "max-sm:flex max-sm:flex-wrap" in lib
    # 名字与 id 同一行(不再是两个 div 上下叠)
    assert '<div className="mt-0.5 font-mono text-micro text-muted">{item.id}</div>' not in lib
    assert 'truncate font-mono text-micro text-muted">{item.id}' in lib


def test_R537_算子清单一组一整行():
    ed = code_of("pages/factors/FactorEditor.tsx")
    assert 'grid grid-cols-1 gap-2" role="group" aria-label="插入算子"' in ed
    assert 'sm:grid-cols-2" role="group" aria-label="插入算子"' not in ed
