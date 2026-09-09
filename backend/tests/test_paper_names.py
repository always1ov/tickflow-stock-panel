"""[R247] 模拟盘要带股票名称。

用户: 「我注意到个股没有显示正确的名称只是代码」。

一屏 `600584.SH` 谁也认不出是哪只票 —— 交易软件从来都是名称当主、代码当辅,
因为人记的是「长电科技」不是那串数字。

名称走 repo 的**统一映射**(与自选、今日总览同一份), 这一层不自己维护一套。
取不到就整个空着 —— 界面退回只显示代码, 不编一个假名字, 也不崩。
"""
from __future__ import annotations

from app.api import paper_trading as api


class _Repo:
    def __init__(self, mapping=None, boom=False):
        self.mapping = mapping or {}
        self.boom = boom
        self.asked: list[list[str]] = []

    def get_name_map(self, syms):
        if self.boom:
            raise RuntimeError("名称表读不到")
        self.asked.append(list(syms))
        return {s: self.mapping.get(s) for s in syms}


def test_名称按代码查得出来():
    repo = _Repo({"600584.SH": "长电科技", "000001.SZ": "平安银行"})
    got = api._name_map(repo, ["600584.SH", "000001.SZ"])
    assert got == {"600584.SH": "长电科技", "000001.SZ": "平安银行"}


def test_查不到的那只不留空串():
    """空名字混进去, 界面就会印出一行只有代码没有名字的空壳 —— 那比不给更糟,
    因为看不出是"这只没名字"还是"整批都没查到"。"""
    repo = _Repo({"600584.SH": "长电科技", "000002.SZ": ""})
    got = api._name_map(repo, ["600584.SH", "000002.SZ", "000003.SZ"])
    assert got == {"600584.SH": "长电科技"}


def test_代码去重且大写():
    """持仓、流水、批次三张表的代码合在一起查一次 —— 重复的不该查两遍。"""
    repo = _Repo({"600584.SH": "长电科技"})
    api._name_map(repo, ["600584.sh", "600584.SH", "600584.SH"])
    assert repo.asked == [["600584.SH"]], f"查了 {repo.asked}"


def test_名称表读不到时安静退回而不是把整页搞崩():
    """名称是**锦上添花**, 不是这一页的主体。查不到就只显示代码 ——
    为了一个名字让持仓和流水整个打不开是本末倒置。"""
    assert api._name_map(_Repo(boom=True), ["600584.SH"]) == {}


def test_没有代码时不去打扰_repo():
    repo = _Repo({"X": "x"})
    assert api._name_map(repo, []) == {}
    assert api._name_map(repo, ["", None]) == {}
    assert repo.asked == [], "空清单还去查了一次"


def test_持仓_流水_批次三处都带上名称():
    """接线守卫: 三张表在界面上都印标的, 漏掉任何一张, 那一张就还是一串代码。"""
    import inspect

    src = inspect.getsource(api.get_book)
    assert 'p_["name"] = names.get' in src, "持仓没带名称"
    assert "dict(o, name=names.get" in src, "操作记录没带名称"
    assert 'l["name"] = names.get' in src, "批次没带名称"
