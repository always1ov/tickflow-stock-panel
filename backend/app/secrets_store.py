"""Key / 凭据本地存储(§14)。

存储位置:`data/user_data/secrets.json`,权限 0600。
优先级:secrets.json > .env > 空(Free 模式)。

UI 改 Key 时只动这个文件,不动 .env。
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)


def _path() -> Path:
    from app.config import settings
    p = settings.data_dir / "user_data" / "secrets.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load() -> dict:
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning("secrets.json malformed: %s", e)
    return {}


def save(updates: dict) -> dict:
    """合并写入(不会清掉未提及的字段)。返回新内容。"""
    current = load()
    current.update({k: v for k, v in updates.items() if v is not None})
    p = _path()
    atomic_write_text(
        p, json.dumps(current, indent=2, ensure_ascii=False), mode=0o600,
    )
    return current


def clear(*keys: str) -> dict:
    """清掉指定字段(留空清全部)。"""
    p = _path()
    if not p.exists():
        return {}
    if not keys:
        p.unlink()
        return {}
    current = load()
    for k in keys:
        current.pop(k, None)
    atomic_write_text(
        p, json.dumps(current, indent=2, ensure_ascii=False), mode=0o600,
    )
    return current


def _raw_tickflow_key_str() -> str:
    """原始 key 串:secrets.json 优先,否则 .env。可能含多 key(逗号/换行/空格分隔)。"""
    val = load().get("tickflow_api_key")
    if val:
        return str(val)
    from app.config import settings
    return settings.tickflow_api_key or ""


def get_tickflow_keys() -> list[str]:
    """所有配置的 TickFlow key。

    支持在同一字段里填多个 key(逗号 / 换行 / 空格分隔),用于「免费多 key 池化」——
    每个免费 key 各给 5 只自选实时额度,凑成 5×N 只。去重保序。
    """
    import re
    out: list[str] = []
    for k in re.split(r"[,\s]+", _raw_tickflow_key_str()):
        k = k.strip()
        if k and k not in out:
            out.append(k)
    return out


def get_tickflow_key() -> str:
    """取主 key(多 key 时取第一个);单 key 时行为不变。

    档位探测、付费端点、历史日K 等单 key 逻辑一律用主 key。
    """
    keys = get_tickflow_keys()
    return keys[0] if keys else ""


def get_ai_key() -> str:
    """取当前 AI Key:secrets.json 优先,否则 .env。"""
    val = load().get("ai_api_key")
    if val:
        return val
    from app.config import settings
    return settings.ai_api_key or ""


# ===== [R56] 多 AI 档位(按优先级排序, 逐个兜底) =====
#
# 原来只有单个 provider / 单个 key / 单个模型 —— 一家用完额度就整个 AI 功能停摆,
# 没有任何自动切换(用户以为有, 其实没有)。这里把它改成一个**有序列表**:
# 排在前面的先用, 那一档因为额度/限流/鉴权/宕机用不了就顺位往下试。
#
# 列表顺序就是优先级 —— 不另存一个 priority 字段: 两处表达同一件事迟早会打架,
# 而"拖一下换顺序"本来就是列表的语义。

AI_PROFILE_FIELDS = ("id", "label", "provider", "base_url", "api_key",
                     "model", "reasoning_effort", "enabled")


def _clean_profile(raw: dict, index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    model = str(raw.get("model") or "").strip()
    provider = str(raw.get("provider") or "openai_compat").strip() or "openai_compat"
    api_key = str(raw.get("api_key") or "").strip()
    # openai 兼容的那一路没 key 就是个摆设, 留着只会在兜底链上白占一次往返。
    # Codex CLI 那一路不需要 key(走本地命令), 所以只对前者要求。
    if provider != "codex_cli" and not api_key:
        return None
    return {
        "id": str(raw.get("id") or "").strip() or f"ai{index}",
        "label": str(raw.get("label") or "").strip(),
        "provider": provider,
        "base_url": str(raw.get("base_url") or "").strip(),
        "api_key": api_key,
        "model": model,
        "reasoning_effort": str(raw.get("reasoning_effort") or "").strip(),
        "enabled": bool(raw.get("enabled", True)),
        # [R111] 来自存储 = 用户真实档位。**不能靠 id=="legacy" 判断是不是合成档**:
        # 早期合成的那条一旦被用户保存进表, id 就原样留在存储里, 它已是真实档位
        # (调用链也确实在用它)。靠 id 猜会把用户排第一的档位误当兼容占位过滤掉。
        "synthesized": False,
    }


def list_ai_profiles(*, enabled_only: bool = False) -> list[dict]:
    """按优先级返回 AI 档位。

    没配过多档时**合成一条**来自旧字段(ai_provider/ai_api_key/ai_model/...)——
    这样老配置一行不用改也照跑, 设置页也不会突然空一片。
    """
    rows = load().get("ai_profiles")
    out: list[dict] = []
    if isinstance(rows, list):
        for i, raw in enumerate(rows):
            got = _clean_profile(raw, i)
            if got:
                out.append(got)
    if not out:
        legacy = _legacy_profile()
        if legacy:
            out.append(legacy)
    return [p for p in out if p["enabled"]] if enabled_only else out


def _legacy_profile() -> dict | None:
    """把旧的单档配置读成一条档位。没配过 AI 时返回 None。"""
    from app.config import settings
    provider = str(load().get("ai_provider") or settings.ai_provider or "openai_compat")
    key = get_ai_key()
    if provider != "codex_cli" and not key:
        return None
    return {
        "id": "legacy",
        "synthesized": True,   # [R111] 后端现合成的兼容档(存储里没有档位表时才出现)
        "label": "",
        "provider": provider,
        "base_url": get_ai_config("ai_base_url", settings.ai_base_url),
        "api_key": key,
        "model": get_ai_config("ai_model", settings.ai_model),
        "reasoning_effort": str(load().get("ai_reasoning_effort") or ""),
        "enabled": True,
    }


def save_ai_profiles(rows: list[dict]) -> list[dict]:
    """整表覆写(顺序即优先级)。返回清洗后的结果。"""
    cleaned = [p for p in (_clean_profile(r, i) for i, r in enumerate(rows or [])) if p]
    current = load()
    current["ai_profiles"] = cleaned
    path = _path()
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return cleaned


def get_ai_config(key: str, default: str = "") -> str:
    """取 AI 配置项:secrets.json 优先,否则 config。"""
    val = load().get(key)
    if val:
        return val
    from app.config import settings
    return getattr(settings, key, default) or default


def get_ai_config_int(key: str, default: int) -> int:
    """取 AI 数值配置项 (如 ai_max_output_tokens): secrets.json 优先,否则 config。"""
    val = load().get(key)
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            logger.warning("ai config %s is not an int: %r", key, val)
    from app.config import settings
    return int(getattr(settings, key, default) or default)


def get_custom_webhook_secret() -> str:
    """Return the optional HMAC secret for the generic outbound webhook."""
    return str(load().get("custom_webhook_secret") or "")


def set_custom_webhook_secret(secret: str) -> str:
    """Persist or clear the generic outbound webhook HMAC secret."""
    value = (secret or "").strip()
    if value:
        save({"custom_webhook_secret": value})
    else:
        clear("custom_webhook_secret")
    return value


def get_email_smtp_password() -> str:
    """Return the SMTP password used by the email notification channel."""
    return str(load().get("email_smtp_password") or "")


def set_email_smtp_password(password: str) -> str:
    """Persist or clear the SMTP password used by email notifications."""
    value = password or ""
    if value:
        save({"email_smtp_password": value})
    else:
        clear("email_smtp_password")
    return value


def get_env_backed_secret(field: str, env_name: str) -> str:
    """取环境变量后备的密钥(插件 API Key 等):secrets.json 优先,否则环境变量。

    与 get_tickflow_key 同优先级语义:UI 写入 secrets.json 后即覆盖 .env。
    """
    val = load().get(field)
    if val:
        return str(val).strip()
    return os.environ.get(env_name, "").strip()


def mask(key: str, prefix: int = 4, suffix: int = 4) -> str:
    """脱敏显示。"""
    if not key:
        return ""
    if len(key) <= prefix + suffix:
        return "•" * len(key)
    return f"{key[:prefix]}{'•' * 6}{key[-suffix:]}"
