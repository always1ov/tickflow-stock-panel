"""[fork R523] 全站手机端自适应 —— 390px 宽体检出来的三处硬伤, 钉住不许回去。

用户: 「这是我手机版看到的。所有页面都要自适应手机端」。
拿 Playwright 在 390×844 下把 31 个路由全过了一遍(横向溢出 / 越界元素 / 被挤成竖排的文字),
剩下的都是这份文件钉的这几处; 其余页面要么本来就自适应, 要么在 R517 / R520 / R522 已经改过。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of


def test_R523_看板顶部两排网格手机两列():
    """四格指数、六格 KPI 在 390px 下硬塞: 标签竖排、数值截断。手机两列, 宽屏照旧四 / 六列。"""
    code = code_of("pages/Dashboard.tsx")
    assert 'className="mb-1.5 grid grid-cols-2 gap-1 sm:grid-cols-4"' in code, "指数条手机不是两列"
    assert 'className="mb-1.5 grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-6"' in code, "KPI 排手机不是两列"
    assert not re.search(r'className="mb-1\.5 grid grid-cols-[46] gap-1"', code), "顶部网格又写死成固定列数了"


def test_R523_KPI读数手机降一号():
    """「2100/200/2900」13 个等宽字, 21px 塞不进半屏。手机 18px, sm 起回到 R453 的 21px。"""
    code = code_of("pages/Dashboard.tsx")
    assert "truncate font-mono text-lg font-semibold leading-none tabular-nums sm:text-xl" in code


def test_R523_数据页存储体积列不折行():
    """「1234.5 MB」在 w-16 里会把 MB 折到下一行, 一列数字参差不齐。"""
    code = code_of("pages/Data.tsx")
    assert code.count("font-mono text-muted w-20 whitespace-nowrap text-right") == 2
    assert "font-mono text-muted w-16 text-right" not in code


def test_R523_Minds笔记条数缺了不拖垮整页():
    """接口回了个空对象时 `items.length` 直接白屏 —— 条数是分栏上的装饰, 缺就缺。"""
    code = code_of("pages/Minds.tsx")
    assert "notes: notesQ.data?.items?.length" in code
    assert "notesQ.data?.items.length" not in code
