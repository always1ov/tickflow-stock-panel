"""[fork 增强] R56 多 AI 档位与按优先级兜底。

在这之前只有单个 provider / 单个 key / 单个模型 —— 一家用完额度整个 AI 功能就
停摆, **没有任何自动切换**(用户以为有, 其实没有)。这里把它改成一个有序列表:
排在前面的先用, 那一档服务不了就顺位往下试。

两条分寸是这个功能的全部要害:

  1. **只有"这一档服务不了"才换档**。请求本身构造错了换谁都一样失败, 挨个试
     一遍等于把每个 key 都白烧一次往返, 还会把真正的错误埋进一句"都失败了"。
  2. **流式只在吐出第一个字之前能换档**。已经流给用户的收不回来, 中途换档会
     把两家的输出接在一起 —— 那比直接报错更糟, 因为读起来是通顺的。
"""
from __future__ import annotations

import pytest

from app import secrets_store
from app.services import ai_provider as ap


class _StatusError(Exception):
    """带 status_code 的假上游错误(openai SDK 的错误就是这个形状)。"""

    def __init__(self, status: int, message: str = "boom") -> None:
        super().__init__(message)
        self.status_code = status


class _ConnError(Exception):
    pass


_ConnError.__name__ = "APIConnectionError"


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "ai_api_key", "", raising=False)
    monkeypatch.setattr(settings, "ai_provider", "openai_compat", raising=False)
    return tmp_path


def _prof(pid: str, **kw) -> dict:
    base = {"id": pid, "label": pid, "provider": "openai_compat",
            "base_url": "https://x/v1", "api_key": f"k-{pid}", "model": f"m-{pid}",
            "reasoning_effort": "", "enabled": True}
    base.update(kw)
    return base


# ---------- 档位读取 ----------

def test_profiles_keep_the_order_they_were_saved_in(store):
    """列表顺序**就是**优先级 —— 不另存 priority 字段: 两处表达同一件事迟早打架。"""
    secrets_store.save_ai_profiles([_prof("a"), _prof("b"), _prof("c")])
    assert [p["id"] for p in secrets_store.list_ai_profiles()] == ["a", "b", "c"]


def test_a_profile_without_a_key_is_dropped(store):
    """openai 兼容那一路没 key 就是个摆设, 留着只会在兜底链上白占一次往返。"""
    secrets_store.save_ai_profiles([_prof("a", api_key=""), _prof("b")])
    assert [p["id"] for p in secrets_store.list_ai_profiles()] == ["b"]


def test_codex_profiles_do_not_need_a_key(store):
    """Codex CLI 走本地命令, 要求填 key 会把这一路整个挡在门外。"""
    secrets_store.save_ai_profiles([_prof("c", provider="codex_cli", api_key="")])
    assert [p["id"] for p in secrets_store.list_ai_profiles()] == ["c"]


def test_disabled_profiles_are_skipped_only_when_asked(store):
    """设置页要看得到停用的那几条, 调用时才跳过。"""
    secrets_store.save_ai_profiles([_prof("a", enabled=False), _prof("b")])
    assert [p["id"] for p in secrets_store.list_ai_profiles()] == ["a", "b"]
    assert [p["id"] for p in secrets_store.list_ai_profiles(enabled_only=True)] == ["b"]


def test_old_single_key_config_still_works_untouched(store, monkeypatch):
    """老配置一行不用改也照跑 —— 否则升级这一版等于把所有人的 AI 关掉。"""
    from app.config import settings
    monkeypatch.setattr(settings, "ai_model", "legacy-model", raising=False)
    secrets_store.save({"ai_api_key": "sk-old"})
    got = secrets_store.list_ai_profiles()
    assert len(got) == 1
    assert got[0]["api_key"] == "sk-old" and got[0]["model"] == "legacy-model"


def test_no_config_at_all_yields_no_profiles(store):
    assert secrets_store.list_ai_profiles() == []


# ---------- 什么样的失败该换档 ----------

@pytest.mark.parametrize("status", [401, 402, 403, 429, 500, 503, 404])
def test_provider_side_failures_advance_to_the_next_profile(status):
    """key 失效 / 余额不足 / 限流 / 对面挂了 / 这一档没这个模型 —— 换一档有戏。"""
    assert ap._should_try_next(_StatusError(status)) is True


def test_connection_failures_advance():
    assert ap._should_try_next(_ConnError("connect timeout")) is True


@pytest.mark.parametrize("status", [400, 422])
def test_request_side_failures_do_not_advance(status):
    """请求本身错了换谁都一样 —— 挨个试等于把每个 key 都白烧一次,
    还会把真正的错误埋进一句"都失败了"。"""
    assert ap._should_try_next(_StatusError(status)) is False


def test_a_missing_model_advances_even_without_a_status_code():
    """有些网关把"没这个模型"写在 400 的正文里而不是状态码上。"""
    assert ap._should_try_next(Exception("model not found: m-x")) is True


# ---------- 兜底链 ----------

@pytest.fixture
def calls(monkeypatch):
    """记下每次尝试用的是哪一档(靠 ContextVar 读当前档位)。"""
    seen: list[str] = []

    def _install(outcomes: list):
        async def _fake(messages, **kw):
            prof = ap.active_profile() or {}
            seen.append(str(prof.get("id")))
            out = outcomes[len(seen) - 1]
            if isinstance(out, Exception):
                raise out
            return out
        monkeypatch.setattr(ap, "_run_openai_once", _fake)
    return seen, _install


async def test_the_first_working_profile_wins(store, calls):
    seen, install = calls
    secrets_store.save_ai_profiles([_prof("a"), _prof("b")])
    install(["来自 a"])
    assert await ap.generate_ai_text([{"role": "user", "content": "hi"}]) == "来自 a"
    assert seen == ["a"], "第一档就成了就不该再碰别人的额度"


async def test_it_falls_through_to_the_next_profile_on_quota(store, calls):
    """用户实际撞上的那个场景: 第一档余额不足。"""
    seen, install = calls
    secrets_store.save_ai_profiles([_prof("a"), _prof("b"), _prof("c")])
    install([_StatusError(402), "来自 b"])
    assert await ap.generate_ai_text([{"role": "user", "content": "hi"}]) == "来自 b"
    assert seen == ["a", "b"], "b 成了就停, 不该继续往下试"


async def test_a_bad_request_stops_at_the_first_profile(store, calls):
    seen, install = calls
    secrets_store.save_ai_profiles([_prof("a"), _prof("b")])
    install([_StatusError(400, "messages 格式不对")])
    with pytest.raises(Exception, match="messages 格式不对"):
        await ap.generate_ai_text([{"role": "user", "content": "hi"}])
    assert seen == ["a"], "请求本身的错误不该把每个 key 都试一遍"


async def test_disabled_profiles_are_not_in_the_chain(store, calls):
    seen, install = calls
    secrets_store.save_ai_profiles([_prof("a", enabled=False), _prof("b")])
    install(["来自 b"])
    await ap.generate_ai_text([{"role": "user", "content": "hi"}])
    assert seen == ["b"]


async def test_when_every_profile_fails_the_error_names_each_one(store, calls):
    """一句"AI 调用失败"没法据以行动 —— 用户要知道是该充值、该换 key,
    还是对面在抽风。"""
    _seen, install = calls
    secrets_store.save_ai_profiles([_prof("a"), _prof("b")])
    install([_StatusError(402, "余额不足"), _StatusError(429, "限流")])
    with pytest.raises(RuntimeError) as e:
        await ap.generate_ai_text([{"role": "user", "content": "hi"}])
    msg = str(e.value)
    assert "a(m-a)" in msg and "b(m-b)" in msg
    assert "余额不足" in msg and "限流" in msg


async def test_a_single_profile_reports_its_own_error_unwrapped(store, calls):
    """只有一档时包一层"全都没能用上"只会让人看不到真正的报错。"""
    _seen, install = calls
    secrets_store.save_ai_profiles([_prof("a")])
    install([_StatusError(402, "余额不足, 请充值")])
    with pytest.raises(Exception, match="余额不足, 请充值"):
        await ap.generate_ai_text([{"role": "user", "content": "hi"}])


async def test_no_profiles_says_to_go_configure_one(store):
    with pytest.raises(RuntimeError, match="未配置"):
        await ap.generate_ai_text([{"role": "user", "content": "hi"}])


# ---------- 档位真的被用上了 ----------

async def test_the_active_profile_drives_model_and_key(store, monkeypatch):
    """换档不只是换个名字 —— model / key / base_url 都得跟着换,
    否则拿 a 的 key 去打 b 的地址, 每一档都会失败。"""
    got: list[tuple[str, str, str]] = []

    async def _fake(messages, **kw):
        got.append((ap.current_ai_model(), ap._active_ai_key(),
                    ap.secrets_store.get_ai_config("ai_base_url", "")))
        raise _StatusError(429)

    monkeypatch.setattr(ap, "_run_openai_once", _fake)
    secrets_store.save_ai_profiles([
        _prof("a", model="m-a", api_key="k-a", base_url="https://a/v1"),
        _prof("b", model="m-b", api_key="k-b", base_url="https://b/v1"),
    ])
    with pytest.raises(RuntimeError):
        await ap.generate_ai_text([{"role": "user", "content": "hi"}])
    assert [(m, k) for m, k, _ in got] == [("m-a", "k-a"), ("m-b", "k-b")]


async def test_the_active_profile_is_cleared_after_the_call(store, calls):
    """ContextVar 没复位的话, 下一次调用会莫名其妙沿用上一次最后试的那一档。"""
    _seen, install = calls
    secrets_store.save_ai_profiles([_prof("a")])
    install(["ok"])
    await ap.generate_ai_text([{"role": "user", "content": "hi"}])
    assert ap.active_profile() is None


# ---------- 流式 ----------

def _stream_of(*outcomes):
    """把一串"这一档吐什么/抛什么"做成 _stream_openai 的替身。"""
    state = {"i": -1}

    async def _fake(messages, **kw):
        state["i"] += 1
        out = outcomes[state["i"]]
        if isinstance(out, Exception):
            raise out
        for piece in out:
            yield piece
    return _fake


async def test_streaming_falls_over_before_the_first_chunk(store, monkeypatch):
    monkeypatch.setattr(ap, "_stream_openai", _stream_of(_StatusError(402), ["来自", " b"]))
    secrets_store.save_ai_profiles([_prof("a"), _prof("b")])
    out = [c async for c in ap.stream_ai_text([{"role": "user", "content": "hi"}])]
    assert "".join(out) == "来自 b"


async def test_streaming_never_switches_after_it_started_emitting(store, monkeypatch):
    """中途换档会把两家的输出接在一起 —— 读起来通顺, 但那是拼的。
    第一个字之后出错就是错, 照实抛。"""
    async def _fake(messages, **kw):
        prof = ap.active_profile() or {}
        if prof.get("id") == "a":
            yield "开头"
            raise _StatusError(429, "写到一半被限流")
        yield "不该跑到这里"

    monkeypatch.setattr(ap, "_stream_openai", _fake)
    secrets_store.save_ai_profiles([_prof("a"), _prof("b")])

    got: list[str] = []
    with pytest.raises(Exception, match="写到一半被限流"):
        async for c in ap.stream_ai_text([{"role": "user", "content": "hi"}]):
            got.append(c)
    assert got == ["开头"], "已经流出去的保留, 但不能再接上第二家的输出"
