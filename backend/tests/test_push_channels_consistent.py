"""[R334] 推送渠道清单 —— **五个地方必须说同一件事**。

用户截图: 钉钉那一格点「测试」弹出 `Input should be 'feishu', 'wecom',
'custom' or 'email'`。

## 这个 bug 的形状

渠道清单在代码里有五份, 各自维护:

    preferences.PUSH_CHANNELS         权威集合(5 个都在)
    settings.WebhookTestIn.channel    测试按钮           ← 掉了 dingtalk
    settings.WebhookSaveIn.channel    保存按钮
    monitor_rules._VALID_CHANNELS     批量设渠道         ← 掉了 custom/email
    webhook_adapter.send_*            各渠道的发送实现

**两处掉的东西还不一样**: 上游 `5289cde1` 加 custom/email 时整行换掉了测试
按钮那个 `Literal`, fork 的 dingtalk 跟着没了; 而 fork 自己写的批量设渠道那份
又漏了上游后加的 custom/email。**两边各漏各的, 谁都不报错** ——
`Literal` 那处是 422 校验错误(用户看到的), 批量那处更糟, 是**静静滤掉**。

所以这组守卫钉的不是某一处, 是**它们彼此一致**。下次再加渠道, 漏改哪一处都会红。
"""
from __future__ import annotations

import inspect
import typing

from app.api import monitor_rules as mr_api
from app.api import settings as settings_api
from app.services import preferences, webhook_adapter

CHANNELS = preferences.PUSH_CHANNELS


def _literal_values(model, field: str) -> set[str]:
    ann = model.model_fields[field].annotation
    return set(typing.get_args(ann))


def test_R334_权威集合就是这五个():
    assert CHANNELS == {"feishu", "wecom", "dingtalk", "custom", "email"}


def test_R334_测试按钮认全部渠道():
    """用户报的就是这一条: 钉钉点「测试」被 pydantic 拒了。"""
    got = _literal_values(settings_api.WebhookTestIn, "channel")
    assert got == CHANNELS, f"测试按钮少了 {CHANNELS - got}, 多了 {got - CHANNELS}"


def test_R334_测试按钮每个渠道都有实现分支_没有死代码():
    """`Literal` 放行了却没有分支, 会掉进 `else: email` 那一支 —— 点钉钉发出邮件。"""
    src = inspect.getsource(settings_api.test_webhook)
    for ch in CHANNELS - {"email"}:      # email 是最后的 else
        assert f'req.channel == "{ch}"' in src, f"{ch} 没有自己的分支"


def test_R334_批量设渠道认全部渠道():
    """前端明明提供 custom/email, 批量设置时却被静静滤掉 —— 比报错更难查。"""
    assert mr_api._VALID_CHANNELS == CHANNELS, (
        f"批量设渠道的白名单与权威集合不一致: {mr_api._VALID_CHANNELS ^ CHANNELS}")


def test_R334_批量那份直接引用权威集合_不另抄一份():
    from tests.py_source import code_of
    code = code_of(mr_api)
    assert "_VALID_CHANNELS = preferences.PUSH_CHANNELS" in code, (
        "另抄一份就是这个 bug 的来源 —— 必须引用同一个集合")


def test_R334_每个渠道都有发送实现():
    """白名单放行了但没有发送函数, 就是"配了也发不出去"。"""
    for ch in CHANNELS - {"email"}:      # email 走 email_adapter, 不在这个模块
        assert hasattr(webhook_adapter, f"send_{ch}"), f"webhook_adapter 缺 send_{ch}"


def test_R334_源码里不许再出现漏掉某个渠道的硬编码清单():
    """扫 api 层: 任何把 feishu 与 wecom 写在一起的**代码**清单, 要么是全集,
    要么就该改成引用 `PUSH_CHANNELS`。

    **只扫代码, 不扫注释与 docstring** —— 老布尔接口的 docstring 里写着
    「True→['feishu','wecom']」, 那是它**真实的兼容行为**(只转译这两个渠道),
    不是漏列。拿正则扫原文会把它误报成 bug。
    """
    import ast
    import re
    from pathlib import Path

    from tests.py_source import code_of
    bad = []
    for mod in (settings_api, mr_api):
        name = Path(mod.__file__).name
        for i, line in enumerate(code_of(mod).splitlines(), 1):
            if '"feishu"' not in line and "'feishu'" not in line:
                continue
            if '"wecom"' not in line and "'wecom'" not in line:
                continue
            found = set(re.findall(r"['\"](feishu|wecom|dingtalk|custom|email)['\"]", line))
            if found != CHANNELS:
                bad.append(f"{name} 第 {i} 行(剥注释后)只列了 {sorted(found)}"
                           f" —— 缺 {sorted(CHANNELS - found)}")
    assert not bad, "有硬编码的渠道清单没列全:\n" + "\n".join(bad)


def test_R334_同名类不许定义两次():
    """**这个 bug 的真正根因。**

    `WebhookTestIn` 在 settings.py 里被定义了两次: fork 那版带 dingtalk,
    上游那版带 custom/email。Python 用后定义的 —— fork 的 dingtalk 就这么
    悄悄失效了, 而**两个定义都还在文件里, 什么都不报错**。

    合并时两边各留一个同名类是很容易发生的事, 所以这条守卫扫整个文件。
    """
    import ast
    from collections import Counter
    from pathlib import Path

    for mod in (settings_api, mr_api):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        dupes = [n for n, c in Counter(names).items() if c > 1]
        assert not dupes, (
            f"{Path(mod.__file__).name} 里这些类定义了不止一次: {dupes} —— "
            "后定义的会遮蔽前面的, 而且什么都不报错")
