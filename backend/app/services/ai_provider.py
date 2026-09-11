"""AI provider adapter for OpenAI-compatible APIs and local Codex CLI."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import AsyncIterator, Callable, Sequence
from contextvars import ContextVar
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app import secrets_store
from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_COMPAT_PROVIDER = "openai_compat"
OPENAI_PROVIDER = "openai"
CODEX_CLI_PROVIDER = "codex_cli"
CODEX_DEFAULT_COMMAND = "codex"
CODEX_SUPPORTED_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
OPENAI_DEFAULT_REASONING_EFFORT = "high"

_CODEX_ENV_ALLOWLIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "TEMP",
    "TMP",
    "TMPDIR",
    "SHELL",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)

# [R180] content 放宽成 str | list —— 多模态(图文混排)时 OpenAI 兼容协议要求
# content 是一个 part 数组: [{"type":"text",...}, {"type":"image_url",...}]。
# 既有调用方全部传字符串, 不受影响。
Message = dict[str, Any]

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


# ----------------------------------------------------------------
# 用户 focus 输入规范化。交易建议类表达不会被静默丢弃,而是由统一提示词
# 转换成客观价位、风险和情景分析,避免历史报告显示了 focus、模型却没有收到。
# ----------------------------------------------------------------
_FOCUS_BLOCKLIST = re.compile(
    r"买入|卖出|加仓|减仓|轻仓|重仓|半仓|全仓|仓位|止损|止盈|"
    r"操作建议|买卖点|买卖区间|建仓|平仓|清仓|调仓|"
    r"追高|低吸|反包|抄底|逃顶|进攻|防守|"
    r"激进|稳健|保守|目标价|能涨|会跌|预测涨|预测跌|"
    r"荐股|推荐买|推荐卖|值得投资|现在买|可以买|能买|要不要买|买吗|卖吗|"
    r"明日基调|交易计划|下单",
    re.IGNORECASE,
)


def sanitize_focus(focus: str) -> str:
    """规范化 focus 中的首尾空白与连续换行。"""
    if not focus:
        return ""
    text = re.sub(r"\s+", " ", focus).strip()
    return text


def build_focus_instruction(focus: str, *, report_name: str = "分析报告") -> str:
    """构建所有报告共用的关注重点指令。

    有关注点时要求模型在固定报告结构之前先直接回应。若原问题涉及交易
    建议,保留问题语义但要求转换成中立的数据分析,不再无提示地整段丢弃。
    """
    text = sanitize_focus(focus)
    if not text:
        return ""

    lines = [
        "## 用户关注重点(必须优先回应)",
        f"用户关注: {text}",
        f"请在完整{report_name}最前面先输出 `### 0. 🔎 关注重点回应`,"
        "用 2-4 条带具体数据的结论直接回应;随后继续完成既定报告结构,"
        "并在相关章节加深分析。不要只复述问题。",
    ]
    if _FOCUS_BLOCKLIST.search(text):
        lines.append(
            "该关注点含有买卖、仓位、目标价或预测类表达。不得给出相应操作结论;"
            "请将其转换为客观的技术/财务状态、关键价位、风险因素和条件情景后回应。"
        )
    return "\n".join(lines)


# ===== [R56] 多档兜底 =====
#
# 一次调用会按优先级把配置好的档位逐个试过去。为了不去改 _run_openai_once /
# _stream_openai / _openai_client 里那一堆读配置的地方, 这里用一个 ContextVar
# 记住"当前正在试的是哪一档", 下面几个 current_* 读它优先。
#
# 用 ContextVar 而不是全局变量: 并发的两个请求可能各自在试不同的档, 用全局
# 会互相串档 —— 那种 bug 只在有并发时才现, 排查起来最费劲。
_ACTIVE_PROFILE: ContextVar[dict | None] = ContextVar("ai_active_profile", default=None)


def _profile_value(field: str) -> str | None:
    """当前档位的某个字段; 不在兜底链里(或该字段为空)时返回 None, 由调用方回落。"""
    prof = _ACTIVE_PROFILE.get()
    if not prof:
        return None
    val = prof.get(field)
    return str(val) if val else None


def active_profile() -> dict | None:
    """当前正在试的档位。给日志与错误消息用。"""
    return _ACTIVE_PROFILE.get()


def _active_ai_key() -> str:
    return _profile_value("api_key") or secrets_store.get_ai_key()


def current_ai_provider() -> str:
    return (_profile_value("provider")
            or secrets_store.get_ai_config("ai_provider", settings.ai_provider)
            or OPENAI_COMPAT_PROVIDER)


def current_openai_model() -> str:
    return _profile_value("model") or secrets_store.get_ai_config("ai_model", settings.ai_model)


def current_codex_model() -> str:
    from_profile = _profile_value("model")
    if from_profile:
        return normalize_codex_model(from_profile)
    stored = secrets_store.load()
    model = stored.get("ai_codex_model")
    # 旧版本的两种 provider 共用 ai_model。仅在旧配置仍启用 Codex 时回退读取,
    # 避免把正常的 OpenAI-compatible 模型误当作 Codex 模型。
    if model is None and current_ai_provider() == CODEX_CLI_PROVIDER:
        model = stored.get("ai_model")
    return normalize_codex_model(str(model or ""))


def current_ai_model() -> str:
    if current_ai_provider() == CODEX_CLI_PROVIDER:
        return current_codex_model()
    return current_openai_model()


def current_openai_reasoning_effort() -> str:
    prof = _ACTIVE_PROFILE.get()
    if prof is not None:
        # 档位里显式留空 = 这一档不传 reasoning_effort, 不该回落到全局默认
        return str(prof.get("reasoning_effort") or "").strip()
    stored = secrets_store.load()
    if "ai_reasoning_effort" not in stored:
        return OPENAI_DEFAULT_REASONING_EFFORT
    return str(stored.get("ai_reasoning_effort") or "").strip()


def current_ai_max_output_tokens() -> int:
    """当前 AI 输出上限 (max_tokens): secrets.json 优先, 否则 config 默认。"""
    return secrets_store.get_ai_config_int("ai_max_output_tokens", settings.ai_max_output_tokens)


def current_ai_context_window() -> int:
    """当前 AI 输入上下文窗口上限 (约 token): secrets.json 优先, 否则 config 默认。"""
    return secrets_store.get_ai_config_int("ai_context_window", settings.ai_context_window)


def _resolve_max_tokens(max_tokens: int | None) -> int | None:
    """显式传入的 max_tokens 钳制到配置输出上限; None 保持 None。

    None = 不传该参数(推理型模型的思考 token 计入 max_tokens 预算,
    显式限制会挤占正文, 语义见 generate_ai_text), 不能映射成配置上限。
    """
    if max_tokens is None:
        return None
    cap = current_ai_max_output_tokens()
    return max(1, min(int(max_tokens), cap))


# 一张图按多少 token 估。各家实测在几百到一两千之间(与分辨率有关), 取 1500
# 是**故意偏高**的: 这个估算只用来挡"明显超窗", 宁可早一点拒绝, 也不要让一张
# 大图把请求撑到上游 400。
_IMAGE_TOKEN_ESTIMATE = 1500


def _content_text(content: Any) -> tuple[str, int]:
    """(可计字数的文本, 图片张数)。

    [R180] 多模态的 content 是 part 数组, 里面 image_url 往往是一个几十万字符的
    base64 data URI。直接 str() 会把它当文本算 —— 一张图就能顶出十几万"token",
    上下文保护会立刻拒掉一个其实完全正常的请求。所以这里只取文本 part。
    """
    if isinstance(content, str):
        return content, 0
    if not isinstance(content, list):
        return str(content or ""), 0
    texts, images = [], 0
    for part in content:
        if not isinstance(part, dict):
            texts.append(str(part))
            continue
        if part.get("type") == "text":
            texts.append(str(part.get("text") or ""))
        elif part.get("type") == "image_url":
            images += 1
    return "".join(texts), images


def _estimate_input_tokens(messages: Sequence[Message]) -> int:
    """粗略估算输入 token 数: 中文按 1 字 1 token, 其余按 4 字符 1 token。"""
    total = 0
    for m in messages:
        text, images = _content_text(m.get("content"))
        cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        total += cjk + (len(text) - cjk) // 4 + 1
        total += images * _IMAGE_TOKEN_ESTIMATE
    return max(1, total)


def _check_input_budget(messages: Sequence[Message], *, max_tokens: int | None) -> None:
    """输入估算超出上下文窗口时给出明确报错, 避免上游 400 或静默截断。

    token 计数不精确, 仅作安全网: 用中/英文混合估算, 只有明显超窗才拒绝;
    用户可在 AI 设置里调大『上下文窗口』。max_tokens=None(输出放开)时用
    配置上限作输出预留估计。
    """
    context_window = current_ai_context_window()
    if context_window <= 0:
        return
    output_reserve = max_tokens if max_tokens is not None else current_ai_max_output_tokens()
    est = _estimate_input_tokens(messages)
    if est + output_reserve > context_window:
        raise ValueError(
            f"输入过长: 估算输入约 {est} tokens, 加上输出预算 {max_tokens} tokens, "
            f"超过上下文窗口 {context_window}。请缩短输入, 或在 AI 设置中调大『上下文窗口』。"
        )


def current_codex_command() -> str:
    return normalize_codex_command(
        secrets_store.get_ai_config("ai_codex_command", settings.ai_codex_command),
        strict=False,
    )


def current_codex_reasoning_effort() -> str:
    return normalize_codex_reasoning_effort(
        secrets_store.get_ai_config(
            "ai_codex_reasoning_effort",
            settings.ai_codex_reasoning_effort,
        )
    )


def is_codex_cli_provider(provider: str | None = None) -> bool:
    return (provider or current_ai_provider()) == CODEX_CLI_PROVIDER


def normalize_codex_model(model: str) -> str:
    value = model.strip()
    aliases = {
        "gpt5.5": "gpt-5.5",
        "gpt5.6": "gpt-5.6-sol",
        "gpt5.6-sol": "gpt-5.6-sol",
        "gpt5.6-terra": "gpt-5.6-terra",
        "gpt5.6-luna": "gpt-5.6-luna",
    }
    return aliases.get(value.lower(), value)


def normalize_codex_reasoning_effort(effort: str | None) -> str:
    value = (effort or "").strip().lower()
    return value if value in CODEX_SUPPORTED_REASONING_EFFORTS else ""


def normalize_codex_command(command: str | None, *, strict: bool = True) -> str:
    value = (command or "").strip()
    if not value or value.lower() == CODEX_DEFAULT_COMMAND:
        return CODEX_DEFAULT_COMMAND
    if strict:
        raise ValueError("Codex CLI 仅支持使用默认 codex 命令自动解析, 不支持自定义可执行路径")
    return CODEX_DEFAULT_COMMAND


_VERSION_SEGMENT_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)


def normalize_openai_base_url(url: str) -> str:
    """Return the OpenAI-compatible base URL expected by the OpenAI SDK.

    识别 URL 中已有的版本段 (/v1、/v2、/v4 等) 时保持原样 —— 部分 OpenAI 兼容
    服务用非 v1 的版本号 (如智谱 GLM 用 /api/paas/v4), 旧实现无条件补 /v1 会拼成
    不存在的 /api/paas/v4/v1/chat/completions 导致 404。仅在无版本段时才补 /v1。
    """
    base = (url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")].rstrip("/")
    if _VERSION_SEGMENT_RE.search(base):
        return base
    return f"{base}/v1"


def codex_cli_available() -> bool:
    """Codex CLI 是否真正可用: 解析命令后实跑一次 --version。

    仅 which 到二进制不够 — npm 壳缺平台原生二进制时同样存在于 PATH,
    但一运行就报错(如 "Codex CLI not available"), 状态页会误报已连接。
    """
    try:
        base = _codex_base_command()
    except RuntimeError:
        return False
    try:
        proc = subprocess.run(
            [*base, "--version"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def ai_configured(provider: str | None = None) -> bool:
    provider = provider or current_ai_provider()
    if is_codex_cli_provider(provider):
        return codex_cli_available()
    return bool(secrets_store.get_ai_key())


# 什么样的失败该顺位往下试。
#
# 分寸在这里: **只有"这一档现在服务不了"才换下一档**。请求本身有问题(比如
# 消息构造错了)换谁都一样失败, 挨个试一遍等于把每个 key 都白烧一次往返,
# 还会把真正的错误埋在一串"都失败了"里面。
#
#   401/403  key 无效或过期
#   402      余额不足 —— 用户最常撞上的那个
#   429      限流 / 额度用尽
#   5xx      对面挂了
#   连接类   连不上、超时
#   模型不存在  这一档没有这个模型(换一档可能就有)
_FAILOVER_STATUSES = frozenset({401, 402, 403, 429})
_MODEL_MISSING_HINTS = ("model not found", "model_not_found", "does not exist",
                        "unknown model", "无可用模型", "模型不存在")


def _should_try_next(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in _FAILOVER_STATUSES or 500 <= status <= 599:
            return True
        if status == 404:
            return True
    if type(exc).__name__ in ("APIConnectionError", "APITimeoutError"):
        return True
    text = (_openai_error_detail(exc) or str(exc)).lower()
    return any(h in text for h in _MODEL_MISSING_HINTS)


def _profile_name(prof: dict) -> str:
    label = str(prof.get("label") or "").strip()
    model = str(prof.get("model") or "").strip()
    if label and model:
        return f"{label}({model})"
    return label or model or str(prof.get("id") or "?")


def _all_failed(errors: list[tuple[dict, Exception]]) -> RuntimeError:
    """每一档各自为什么失败都要写出来 —— 一句"AI 调用失败"没法据以行动:
    用户需要知道是该充值、该换 key, 还是对面在抽风。"""
    lines = [f"· {_profile_name(p)}: {_format_openai_error(e) if _is_openai_transport_error(e) else e}"
             for p, e in errors]
    return RuntimeError("配置的 AI 档位全都没能用上:\n" + "\n".join(lines))


def _profiles_for_call() -> list[dict]:
    return secrets_store.list_ai_profiles(enabled_only=True)


# [fork R94] 最近一次真正服务成功的档位(诊断用: 测试按钮/日志据此报"是谁在答")。
# 只是标签, 不参与任何路由决策; 简单全局够用 —— 并发下最多显示成"最近一个成功的"。
_LAST_SERVED: dict | None = None


def last_served_profile_name() -> str | None:
    return _profile_name(_LAST_SERVED) if _LAST_SERVED else None


def _mark_served(prof: dict) -> None:
    global _LAST_SERVED
    _LAST_SERVED = prof


async def generate_ai_text(
    messages: Sequence[Message],
    *,
    temperature: float | None = 0.3,
    max_tokens: int | None = 3000,
    timeout: float = 180.0,
) -> str:
    """Return a complete AI response, trying each configured profile in priority order.

    [R56] 按优先级逐档兜底: 排在前面的先用, 那一档因为额度/限流/鉴权/宕机
    用不了就顺位往下。只在"这一档服务不了"时换档 —— 请求本身的错误不换,
    见 _should_try_next。

    max_tokens=None 表示不传该参数(输出上限交给服务端默认) — 推理型模型
    (如 deepseek reasoner 系)的思考 token 计入 max_tokens 预算, 显式限制
    会挤占正文甚至全部吃光(正文 0 字 + finish=length), 长分析类调用应放开。
    显式传入的数值会被钳制到配置的输出上限 (AI 设置可调)。
    """
    # [同步上游] 输出上限归一 + 输入预算检查在进档位循环前做一次 —— 预算超了
    # 换哪一档都超, 不该把它算成"这一档用不了"去触发兜底
    max_tokens = _resolve_max_tokens(max_tokens)
    _check_input_budget(messages, max_tokens=max_tokens)

    profiles = _profiles_for_call()
    if not profiles:
        raise RuntimeError("AI API Key 未配置, 请在设置页配置")

    errors: list[tuple[dict, Exception]] = []
    for i, prof in enumerate(profiles):
        token = _ACTIVE_PROFILE.set(prof)
        try:
            if is_codex_cli_provider():
                text = await _run_codex_cli(
                    messages, max_tokens=max_tokens, timeout=max(timeout, 600.0))
            else:
                text = await _run_openai_once(
                    messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
            _mark_served(prof)
            # [R232] 剥掉内联的思考段(MiniMax 一类把 <think>…</think> 写在
            # content 里)。做在这个唯一出口上 —— 每个调用方各剥一遍必然漏。
            # 剥完为空会退回原文, 见 ai_reasoning 的说明。
            from app.services.ai_reasoning import strip_reasoning
            return strip_reasoning(text)
        except Exception as exc:
            errors.append((prof, exc))
            last = i == len(profiles) - 1
            if last or not _should_try_next(exc):
                # 只有一档时原样抛原错 —— 包一层只会让人看不到真正的报错
                if len(errors) == 1:
                    raise
                raise _all_failed(errors) from exc
            logger.warning("AI 档位 %s 用不了(%s), 顺位试下一档", _profile_name(prof), exc)
        finally:
            _ACTIVE_PROFILE.reset(token)
    raise _all_failed(errors)


async def stream_ai_text(
    messages: Sequence[Message],
    *,
    temperature: float | None = 0.5,
    max_tokens: int | None = 4000,
    timeout: float = 180.0,
    prefer_final_answer: bool = False,
) -> AsyncIterator[str]:
    """Yield text deltas from the configured provider.

    Codex CLI only exposes the final assistant message for this use case, so it
    yields one complete chunk after the command exits. ``prefer_final_answer``
    lets compatible providers prioritize visible content over hidden reasoning.

    [R56] 同样按优先级逐档兜底, 但**只在还没吐出第一个字之前**能换档 ——
    已经流给用户的内容收不回来, 中途换档会把两家的输出接在一起, 那比直接
    报错更糟(用户看到的是一段读得通但其实是拼接的文字)。第一个字之后出错
    就是错, 照实抛。

    max_tokens=None 表示不限制输出(同 generate_ai_text 的说明)。
    """
    # [同步上游] 预算检查同样在进档位循环前做(理由见 generate_ai_text)
    max_tokens = _resolve_max_tokens(max_tokens)
    _check_input_budget(messages, max_tokens=max_tokens)

    # [R56 + 上游] fork 的多档兜底循环保留; 上游新加的 prefer_final_answer
    # 穿进下面那次 _stream_openai 调用 —— 只取上游那版的话, 多档兜底就没了;
    # 只取 fork 那版的话, 新参数在流式这条路上等于没接。
    profiles = _profiles_for_call()
    if not profiles:
        raise RuntimeError("AI API Key 未配置, 请在设置页配置")

    errors: list[tuple[dict, Exception]] = []
    for i, prof in enumerate(profiles):
        token = _ACTIVE_PROFILE.set(prof)
        started = False
        try:
            # [R232] 流式也要剥思考段, 而且**必须有状态** —— <think> 六个字符
            # 可以正好跨在两个 chunk 之间, 逐块 replace 抓不住。见 ai_reasoning。
            from app.services.ai_reasoning import StreamStripper
            stripper = StreamStripper()
            if is_codex_cli_provider():
                text = await _run_codex_cli(
                    messages, max_tokens=max_tokens, timeout=max(timeout, 600.0))
                started = True
                _mark_served(prof)
                yield stripper.feed(text) + stripper.flush()
                return
            async for chunk in _stream_openai(
                messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                prefer_final_answer=prefer_final_answer,
            ):
                if not started:
                    _mark_served(prof)
                started = True
                out = stripper.feed(chunk)
                if out:
                    yield out
            tail = stripper.flush()
            if tail:
                yield tail
            return
        except Exception as exc:
            errors.append((prof, exc))
            last = i == len(profiles) - 1
            if started or last or not _should_try_next(exc):
                if len(errors) == 1:
                    raise
                raise _all_failed(errors) from exc
            logger.warning("AI 档位 %s 用不了(%s), 顺位试下一档", _profile_name(prof), exc)
        finally:
            _ACTIVE_PROFILE.reset(token)
    raise _all_failed(errors)


async def _run_openai_once(
    messages: Sequence[Message],
    *,
    temperature: float | None,
    max_tokens: int | None,
    timeout: float,
) -> str:
    ai_key = _active_ai_key()
    if not ai_key:
        raise RuntimeError("AI API Key 未配置, 请在设置页配置")

    client = _openai_client(ai_key, timeout)
    model = current_ai_model()
    req_messages = list(messages)
    kwargs = _openai_kwargs(temperature=temperature, max_tokens=max_tokens)
    transient_left = 2  # 瞬时错误(429/5xx/连接超时)自动重试: 2s → 5s 退避
    while True:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=req_messages,
                **kwargs,
            )
            break
        except Exception as exc:
            retry_kwargs = _openai_retry_kwargs(exc, kwargs)
            if retry_kwargs is not None:
                kwargs = retry_kwargs
                continue
            if transient_left > 0 and _is_transient_ai_error(exc):
                await asyncio.sleep(2.0 if transient_left == 2 else 5.0)
                transient_left -= 1
                continue
            if _is_openai_transport_error(exc):
                raise RuntimeError(_format_openai_error(exc)) from exc
            raise
    if not resp.choices:
        return ""
    msg = resp.choices[0].message
    text = (msg.content or "").strip()
    if not text:
        # [R22] 部分思考型模型把推理放 reasoning_content 而 content 为空(答案没
        # 输出完就被掐断时尤甚)—— 取推理段返回, 让上层报错能带上原文摘录,
        # 用户可判断是 token 不够还是模型没回, 而不是一句"空内容"
        text = (getattr(msg, "reasoning_content", None) or "").strip()
    return text


async def _stream_openai(
    messages: Sequence[Message],
    *,
    temperature: float | None,
    max_tokens: int | None,
    timeout: float,
    prefer_final_answer: bool,
) -> AsyncIterator[str]:
    ai_key = _active_ai_key()
    if not ai_key:
        raise RuntimeError("AI API Key 未配置, 请在设置页配置")

    client = _openai_client(ai_key, timeout)
    model = current_ai_model()
    base_url = secrets_store.get_ai_config("ai_base_url", settings.ai_base_url)
    req_messages = list(messages)

    kwargs = _openai_kwargs(
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        base_url=base_url,
        prefer_final_answer=prefer_final_answer,
    )
    transient_left = 2  # [fork] 瞬时错误(429/5xx/连接超时)自动重试: 2s → 5s 退避
    while True:
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=req_messages,
                **kwargs,
                stream=True,
            )
            break
        except Exception as exc:
            # 流尚未开始 yield, 可安全移除被拒绝的可选参数后重建。
            retry_kwargs = _openai_retry_kwargs(exc, kwargs)
            if retry_kwargs is not None:
                kwargs = retry_kwargs
                continue
            if transient_left > 0 and _is_transient_ai_error(exc):
                await asyncio.sleep(2.0 if transient_left == 2 else 5.0)
                transient_left -= 1
                continue
            if _is_openai_transport_error(exc):
                raise RuntimeError(_format_openai_error(exc)) from exc
            raise

    try:
        async for piece in _iter_openai_text(stream):
            yield piece
    except Exception as exc:
        if _is_openai_transport_error(exc):
            raise RuntimeError(_format_openai_error(exc)) from exc
        raise


_LENGTH_FINISH_REASONS = {"length", "max_tokens", "max_output_tokens"}


async def _iter_openai_text(stream) -> AsyncIterator[str]:
    """Normalize an OpenAI-compatible stream into complete text deltas.

    Reasoning models may spend the entire completion budget on
    ``reasoning_content`` and finish with HTTP 200 but no user-visible text.
    Treat that response, and any length-truncated partial response, as a
    terminal generation error instead of silently reporting success.
    """
    content_seen = False
    reasoning_seen = False
    finish_reason = ""

    async for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        choice = choices[0]
        reason = getattr(choice, "finish_reason", None)
        if reason:
            finish_reason = str(reason)

        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        if getattr(delta, "reasoning_content", None):
            reasoning_seen = True
        content = getattr(delta, "content", None)
        if content:
            content_seen = True
            yield content

    if finish_reason in _LENGTH_FINISH_REASONS:
        if reasoning_seen and not content_seen:
            raise RuntimeError(
                "AI 推理达到输出长度上限, 未生成正文; 请提高输出 Token 上限或改用非推理模型"
            )
        raise RuntimeError("AI 输出达到长度上限, 内容不完整; 请提高输出 Token 上限后重试")

    if not content_seen:
        if reasoning_seen:
            raise RuntimeError("AI 仅返回推理内容, 未生成正文; 请检查模型配置或改用非推理模型")
        raise RuntimeError("AI 服务未返回正文内容; 请检查模型配置或稍后重试")


def _openai_client(api_key: str, timeout: float):
    from openai import AsyncOpenAI

    user_agent = secrets_store.get_ai_config("ai_user_agent", "") or settings.ai_user_agent
    return AsyncOpenAI(
        api_key=api_key,
        base_url=normalize_openai_base_url(
            _profile_value("base_url") or secrets_store.get_ai_config("ai_base_url", settings.ai_base_url)),
        timeout=timeout,
        max_retries=0,
        default_headers={"User-Agent": user_agent},
    )


# 不同模型可能拒绝 temperature 或 reasoning_effort。这里不靠模型名猜测,
# 只在 400 明确指出对应参数时移除该参数并重试; 每个参数最多移除一次。
_TEMP_REJECT_HINTS = ("temperature", "only 1 is allowed")
_REASONING_EFFORT_REJECT_HINTS = ("reasoning_effort", "reasoning effort")
_THINKING_BODY_REJECT_HINTS = ("thinking",)


def _is_temperature_rejected(exc: Exception) -> bool:
    """True if the upstream 400 is specifically about the temperature param."""
    if getattr(exc, "status_code", None) != 400:
        return False
    text = _openai_error_detail(exc) or str(exc)
    return _openai_error_param(exc) == "temperature" or any(
        h in text.lower() for h in _TEMP_REJECT_HINTS
    )


def _is_reasoning_effort_rejected(exc: Exception) -> bool:
    """True if the upstream 400 specifically rejects reasoning_effort."""
    if getattr(exc, "status_code", None) != 400:
        return False
    text = _openai_error_detail(exc) or str(exc)
    return _openai_error_param(exc) == "reasoning_effort" or any(
        h in text.lower() for h in _REASONING_EFFORT_REJECT_HINTS
    )


def _is_thinking_body_rejected(exc: Exception) -> bool:
    """True if the upstream 400 specifically rejects the thinking extra_body."""
    if getattr(exc, "status_code", None) != 400:
        return False
    text = _openai_error_detail(exc) or str(exc)
    return _openai_error_param(exc) == "thinking" or any(
        h in text.lower() for h in _THINKING_BODY_REJECT_HINTS
    )


def _openai_error_param(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        body = error
    return str(body.get("param") or "").strip().lower()


def _openai_retry_kwargs(exc: Exception, kwargs: dict) -> dict | None:
    """Remove one explicitly rejected optional argument for a bounded retry."""
    retry_kwargs = dict(kwargs)
    if "temperature" in retry_kwargs and _is_temperature_rejected(exc):
        retry_kwargs.pop("temperature")
        return retry_kwargs
    if "reasoning_effort" in retry_kwargs and _is_reasoning_effort_rejected(exc):
        retry_kwargs.pop("reasoning_effort")
        return retry_kwargs
    if "extra_body" in retry_kwargs and _is_thinking_body_rejected(exc):
        # DeepSeek thinking 禁用参数被拒 (模型/API 版本差异): 回退默认思考模式
        # 重试; 报告若因此被推理挤占正文, 由 _iter_openai_text 显式报错。
        retry_kwargs.pop("extra_body")
        return retry_kwargs
    return None


_DEEPSEEK_V4_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}


def _openai_kwargs(
    *,
    temperature: float | None,
    max_tokens: int | None,
    model: str = "",
    base_url: str = "",
    prefer_final_answer: bool = False,
) -> dict:
    """Build OpenAI create() kwargs and map supported provider capabilities.

    max_tokens=None 时不传 — 由服务端默认上限管理(推理模型的思考 token 也
    计入该参数预算, 限制会挤占正文, 见 stream_ai_text 文档)。
    """
    kwargs: dict = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    if current_ai_provider() == OPENAI_PROVIDER:
        reasoning_effort = current_openai_reasoning_effort()
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
    if (
        prefer_final_answer
        and model.strip().lower() in _DEEPSEEK_V4_MODELS
        and urlsplit(base_url.strip()).hostname == "api.deepseek.com"
    ):
        # DeepSeek V4 defaults to thinking mode. For report-style tasks the
        # hidden reasoning shares max_tokens with the final answer and can
        # exhaust the budget before any visible content is emitted.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return kwargs


def _is_transient_ai_error(exc: Exception) -> bool:
    """瞬时可重试错误: 提供商过载/限流/网关抖动。

    429(限流) 与 5xx(如 MiniMax 偶发 503 Service temporarily unavailable)
    以及连接建立/超时类错误 —— 这类错误换个时间点重试大概率成功,
    不该直接把失败甩给用户。
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or 500 <= status <= 504):
        return True
    return type(exc).__name__ in ("APIConnectionError", "APITimeoutError")


def _is_openai_transport_error(exc: Exception) -> bool:
    try:
        import openai
    except ImportError:
        openai = None

    if openai is not None and isinstance(exc, openai.APIError):
        return True

    try:
        import httpx
    except ImportError:
        return False

    return isinstance(exc, httpx.HTTPError)


def _format_openai_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)

    class_name = exc.__class__.__name__
    if "Timeout" in class_name:
        return "AI 服务请求超时, 请稍后重试或检查 AI Base URL / 网络"
    if "Connection" in class_name:
        return "AI 服务连接失败, 请检查 AI Base URL / 网络"

    detail = _openai_error_detail(exc)
    status_messages = {
        400: "请求参数无效, 请检查模型名称和上下文长度",
        401: "API Key 无效或无权限, 请检查设置页配置",
        403: "AI 服务拒绝访问, 请检查账号权限或网关配置",
        404: "模型或接口地址不存在, 请检查 AI Base URL 和模型名称",
        408: "AI 服务请求超时, 请稍后重试",
        429: "AI 服务限流或额度不足, 请稍后重试或检查额度",
        500: "AI 服务内部错误, 请稍后重试",
        502: "AI 网关返回错误, 请稍后重试或检查 AI Base URL",
        503: "AI 服务暂时不可用, 请稍后重试",
        504: "AI 上游服务超时, 请稍后重试或检查 AI Base URL / 网络",
    }
    # 优先透出上游真实错误 (如 Moonshot 的 "model not found"), 仅在没有
    # 可读 detail 时才回落到按状态码的通用文案, 避免吞掉排障关键信息。
    message = detail or status_messages.get(status) or "请稍后重试或检查 AI 服务配置"
    if status:
        return f"AI 服务请求失败({status}): {message}"
    return f"AI 服务请求失败: {message}"


def _openai_error_detail(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            text = error.get("message") or error.get("code") or error.get("type")
            return _compact_error_text(str(text or ""))
        if isinstance(error, str):
            return _compact_error_text(error)

    response = getattr(exc, "response", None)
    content_type = ""
    text = ""
    if response is not None:
        content_type = response.headers.get("content-type", "").lower()
        try:
            text = response.text
        except Exception:
            text = ""
    if not text and isinstance(body, str):
        text = body
    if not text:
        text = str(exc)
    if _looks_like_html(text, content_type):
        return ""
    return _compact_error_text(text)


def _looks_like_html(text: str, content_type: str) -> bool:
    sample = text.lstrip()[:200].lower()
    return "html" in content_type or sample.startswith("<!doctype html") or sample.startswith("<html")


def _compact_error_text(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


async def _run_codex_cli(
    messages: Sequence[Message],
    *,
    max_tokens: int | None,
    timeout: float,
) -> str:
    prompt = _codex_prompt(messages, max_tokens=max_tokens)
    run_path = Path(tempfile.mkdtemp(prefix="tickflow-codex-run-"))
    try:
        codex_home_path = run_path / "codex-home"
        workspace_path = run_path / "workspace"
        codex_home_path.mkdir()
        workspace_path.mkdir()
        output_path = codex_home_path / "last-message.txt"
        _prepare_codex_home(codex_home_path)

        # 不传 --ephemeral: 老版本 codex(如 0.58)无此参数, 传了直接报
        # unexpected argument; 会话隔离已由一次性临时 CODEX_HOME 保证(跑完即删)。
        args = [
            *_codex_base_command(),
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
        ]
        model = current_ai_model().strip()
        if model:
            args.extend(["--model", model])
        args.extend(["--cd", str(workspace_path), "-"])

        env = _codex_process_env(codex_home_path)

        returncode, stdout, stderr = await asyncio.to_thread(
            _run_codex_process,
            args,
            prompt,
            env,
            timeout,
        )

        out = _clean_process_text(stdout)
        err = _clean_process_text(stderr)
        final_message = _read_output_file(output_path)
        if returncode != 0:
            detail = err or out or f"exit code {returncode}"
            raise RuntimeError(f"Codex CLI 调用失败: {detail[-1200:]}")
        result = final_message or out
        if not result:
            raise RuntimeError("Codex CLI 未返回内容")
        return result
    finally:
        await asyncio.to_thread(_remove_tree_best_effort, run_path)


def _run_codex_process(
    args: Sequence[str],
    prompt: str,
    env: dict[str, str],
    timeout: float,
) -> tuple[int, bytes, bytes]:
    try:
        proc = subprocess.run(
            list(args),
            input=prompt.encode("utf-8"),
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Codex CLI 调用超时, 请稍后重试或检查本机 Codex 登录状态") from exc
    return proc.returncode, proc.stdout, proc.stderr


def _codex_process_env(codex_home_path: Path) -> dict[str, str]:
    """Pass only OS, locale, certificate, and proxy settings to Codex."""
    env: dict[str, str] = {}
    seen: set[str] = set()
    for name in _CODEX_ENV_ALLOWLIST:
        normalized = name.casefold() if os.name == "nt" else name
        if normalized in seen:
            continue
        value = os.environ.get(name)
        if value:
            env[name] = value
            seen.add(normalized)
    env["NO_COLOR"] = "1"
    env["CODEX_HOME"] = str(codex_home_path)
    return env


def _remove_tree_best_effort(path: Path) -> None:
    _remove_auth_files(path)
    for attempt in range(4):
        try:
            shutil.rmtree(path, onerror=_make_writable_and_retry)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 3:
                break
            time.sleep(0.2 * (attempt + 1))
    _remove_auth_files(path)
    shutil.rmtree(path, ignore_errors=True)
    _remove_auth_files(path)


def _remove_auth_files(path: Path) -> None:
    try:
        auth_files = list(path.rglob("auth.json"))
    except OSError:
        return
    for auth_file in auth_files:
        try:
            os.chmod(auth_file, stat.S_IWRITE)
            auth_file.unlink(missing_ok=True)
        except OSError:
            pass


def _make_writable_and_retry(
    func: Callable[[str], object],
    path: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType],
) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise exc_info[1] from None


def _codex_prompt(messages: Sequence[Message], *, max_tokens: int | None) -> str:
    parts = [
        "You are 牛来's local AI provider.",
        "This is a text-generation task. The working directory is intentionally empty.",
        "Use only the user-provided prompt content below; do not inspect or modify local files.",
        "Return only the final requested content; do not include execution logs.",
    ]
    if max_tokens:
        parts.append(f"Keep the final answer within about {max_tokens} output tokens.")
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        parts.append(f"\n<{role}>\n{content}\n</{role}>")
    return "\n".join(parts)


def _codex_base_command() -> list[str]:
    command = current_codex_command()
    resolved = _resolve_command(command)
    if not resolved:
        raise RuntimeError(f"未找到 Codex CLI 命令: {command}")

    if sys.platform == "win32" and resolved.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved]
    return [resolved]


def _resolve_command(command: str) -> str | None:
    if command.lower() != CODEX_DEFAULT_COMMAND:
        return None

    if sys.platform == "win32":
        desktop_codex = _resolve_windows_desktop_codex()
        if desktop_codex:
            return desktop_codex

    resolved = shutil.which(command)
    if sys.platform == "win32" and resolved:
        resolved_path = Path(resolved)
        if not resolved_path.suffix:
            cmd_path = resolved_path.with_suffix(".cmd")
            if cmd_path.exists():
                return str(cmd_path)
    if not resolved and sys.platform == "win32" and not command.lower().endswith(".cmd"):
        resolved = shutil.which(f"{command}.cmd")
    if not resolved and sys.platform == "win32":
        resolved = _resolve_windows_codex_command(command)
    return resolved


def _resolve_windows_codex_command(command: str) -> str | None:
    """Find npm-installed Codex when the backend process has a minimal PATH."""
    raw = Path(command)
    if raw.parent != Path("."):
        return None

    names = [command]
    if not raw.suffix:
        names = [f"{command}.cmd", f"{command}.exe", f"{command}.bat", f"{command}.ps1", command]

    dirs: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "npm")
    dirs.append(Path.home() / "AppData" / "Roaming" / "npm")

    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        value = os.environ.get(env_name)
        if value:
            dirs.append(Path(value) / "nodejs")

    for directory in dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)
    return None


def _resolve_windows_desktop_codex() -> str | None:
    """Prefer the Codex Desktop bundled CLI over an older npm shim."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None

    root = Path(local_appdata) / "OpenAI" / "Codex" / "bin"
    if not root.exists():
        return None

    candidates = list(root.glob("*/codex.exe"))
    direct = root / "codex.exe"
    if direct.exists():
        candidates.append(direct)
    if not candidates:
        return None

    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return str(newest)


def _prepare_codex_home(target: Path) -> None:
    """Create an isolated CODEX_HOME that reuses auth but not fragile config."""
    source = _codex_home()
    auth_file = source / "auth.json"
    if auth_file.exists():
        shutil.copy2(auth_file, target / "auth.json")
    _write_compatible_codex_config(target / "config.toml")


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _write_compatible_codex_config(path: Path) -> None:
    config = _read_codex_config()
    lines: list[str] = []
    active_provider = _active_codex_provider(config)

    if active_provider:
        lines.append(_toml_string("model_provider", active_provider[0]))

    openai_base_url = config.get("openai_base_url")
    if isinstance(openai_base_url, str) and openai_base_url:
        lines.append(_toml_string("openai_base_url", openai_base_url))

    model = current_ai_model() or normalize_codex_model(str(config.get("model") or ""))
    if model:
        lines.append(_toml_string("model", model))

    effort = current_codex_reasoning_effort() or normalize_codex_reasoning_effort(
        str(config.get("model_reasoning_effort") or "")
    )
    if effort:
        lines.append(_toml_string("model_reasoning_effort", effort))

    lines.append(_toml_string("approval_policy", "never"))
    lines.append(_toml_string("sandbox_mode", "read-only"))

    if active_provider:
        provider_name, provider = active_provider
        lines.append("")
        lines.append(f"[model_providers.{_toml_key(provider_name)}]")
        for key in ("name", "base_url", "wire_api", "experimental_bearer_token"):
            value = provider.get(key)
            if isinstance(value, str) and value:
                lines.append(_toml_string(key, value))
        for key in ("requires_openai_auth", "supports_websockets"):
            value = provider.get(key)
            if isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _active_codex_provider(config: dict) -> tuple[str, dict] | None:
    """Return the active custom provider, adapting loopback URLs for Docker."""
    provider_name = config.get("model_provider")
    if not isinstance(provider_name, str) or not provider_name:
        return None

    providers = config.get("model_providers")
    if not isinstance(providers, dict):
        return None
    source = providers.get(provider_name)
    if not isinstance(source, dict):
        return None

    provider = dict(source)
    base_url = str(provider.get("base_url") or "").strip()
    parsed = urlsplit(base_url)
    docker_host = os.environ.get("CODEX_DOCKER_HOST", "").strip()
    if docker_host and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        port = f":{parsed.port}" if parsed.port else ""
        provider["base_url"] = urlunsplit(parsed._replace(netloc=f"{docker_host}{port}"))
    return provider_name, provider


def _read_codex_config() -> dict:
    path = _codex_home() / "config.toml"
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return _read_codex_config_lenient(path)
    except OSError:
        return {}


def _read_codex_config_lenient(path: Path) -> dict:
    config: dict[str, str] = {}
    pattern = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"\s*$')
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line)
            if match:
                config[match.group(1)] = match.group(2)
    except OSError:
        pass
    return config


def _toml_string(key: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key} = "{escaped}"'


def _toml_key(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _clean_process_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    return _ANSI_RE.sub("", text).strip()


def _read_output_file(path: Path) -> str:
    if path.exists():
        return _ANSI_RE.sub("", path.read_text(encoding="utf-8", errors="replace")).strip()
    return ""
