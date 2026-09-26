"""[fork R535] 设置八个子页: 一种卡头、一个宽度, 以及逐栏的版面整理。

用户: 「设置里面的每个子页面也要整改」, 看过方案图后「确认」。只改表达 —— 每个开关、输入框、按钮的
行为与文字, 数据、接口、`?highlight=` 深链都没动。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

S = "pages/settings/"

#: 用上统一卡头的面板(数据源那几张卡是作者的结构, 这一轮只动了它的提示条)
CARD_USERS = ["AI.tsx", "AiProfiles.tsx", "Monitoring.tsx", "System.tsx", "JobTimeoutCard.tsx",
              "MenuSettings.tsx", "ExtPages.tsx"]


def test_R535_卡头只有一个产地():
    for f in CARD_USERS:
        code = code_of(S + f)
        assert "SettingsCard" in code, f"{f} 没走 SettingsCard"
        assert "function Card(" not in code, f"{f} 又手写了一份 Card"
        assert "SectionIntro" not in code, f"{f} 还在用大号开篇块"


def test_R535_宽度只在外壳定一处():
    shell = code_of("pages/Settings.tsx")
    # [R536] 用户「每个子页面都要铺满内容区域」: 外壳不设上限, 八栏一起铺满
    assert '<div className="w-full">' in shell
    assert not re.search(r'<main[^>]*>\s*<div className="w-full max-w-', shell), "设置外壳又加回了宽度上限, 宽屏右边会空一块"
    for f in CARD_USERS + ["DataSources.tsx", "Notifications.tsx", "Timeout.tsx"]:
        code = code_of(S + f)
        # 面板最外层不许再自带上限(弹窗里的 max-w-[380px] 那种不算)
        assert not re.search(r'className="[^"]*\bmax-w-(2xl|3xl|4xl|5xl|6xl)\b', code), f"{f} 又自带了宽度上限"


def test_R535_AI_连接状态并进配置卡_保存在卡头():
    ai = code_of(S + "AI.tsx")
    assert 'title="连接状态"' not in ai, "连接状态又单独成卡了"
    assert "right={saveButtons}" in ai, "「保存配置」不在配置卡的卡头"
    assert "flex-1 justify-center" not in ai, "页底通栏的保存按钮回来了"
    assert "border-warning/20 bg-warning/[0.04]" not in ai, "Key 保存说明又成了橙色提示条"


def test_R535_系统收成常规与维护两张():
    sysp = code_of(S + "System.tsx")
    i = sysp.index("export function SettingsSystemPanel"); j = sysp.index("export function AlertPopupSettings")
    panel = sysp[i:j]
    assert panel.count("<SettingsCard") == 2
    assert 'title="常规"' in panel and 'title="维护"' in panel
    for label in ("进入策略页自动运行策略", "个股详情外链", "版本", "刷新前端缓存"):
        assert label in panel, f"系统栏少了「{label}」"
    assert 'label="数据体检"' in sysp


def test_R535_网络拆成两张_开关只动transform():
    code = code_of(S + "JobTimeoutCard.tsx")
    assert 'title="超时设置"' in code and 'title="数据传输压缩"' in code
    # 原来滑块过渡的是 left(每帧重排), AGENTS.md 动效硬规则第 1 条
    assert "left-[" not in code and "translate-x-" in code


def test_R535_菜单_内置不逐行印_手机上名字保底():
    code = code_of(S + "MenuSettings.tsx")
    assert "'内置'" not in code, "「内置」又逐行印回来了"
    assert "entry.type !== 'builtin'" in code
    cols = re.search(r"const GRID_COLS = '([^']+)'", code).group(1)
    phone = cols.split(" sm:")[0]
    assert "minmax(0,1fr)" in phone and phone.count("_") == 5, "手机上的列数/名字列不对(应 6 列, 名字列保底)"
    assert 'className="max-sm:hidden">类型</div>' in code


def test_R535_外部网页一张卡_扩展页面一张卡():
    code = code_of(S + "ExtPages.tsx")
    assert 'title="外部网页"' in code and 'title="扩展页面"' in code
    assert "把一个外部网页变成菜单里的一页" in code, "大标题那句话并进说明时丢了"


def test_R535_数据源插件说明不再是黄色提示条():
    code = code_of(S + "DataSources.tsx")
    assert "border-warning/40 bg-warning/10" not in code
    assert "数据源已插件化" in code
