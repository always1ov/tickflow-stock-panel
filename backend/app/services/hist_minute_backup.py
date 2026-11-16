"""分时备用接口: 全系统共用的分钟兜底 (独立配置, 不进自定义数据源列表)。

设计边界 (硬约束):
  - 只由个股弹窗的分时请求触发; 批量/定时同步路径永不引用;
  - 单只逐日拉取, 不做全市场扫描;
  - 落盘前先校验 (行数/时间窗/价格/去重), 坏数据一律不写主分钟存储;
  - 写入的 (symbol, datetime) 记入台账, 删除该接口时据此精确清除,
    不触碰主分钟源的历史数据;
  - 接口地址从设置页单独填写, 失效可随时删除。

支持的接口形态:
  1. 单只单日 ("data.points" 分钟点): 请求参数里替换代码与日期, 每点只有
     一个价格 p, 按 O=H=L=C=p 落成分钟 K (量/额取 vol/amt);
  2. 通用行列表: 用 response_path + field_map 取行, 自动识别常见列名。

配置文件: {data_dir}/hist_minute_source.yaml
台账文件: {data_dir}/data_source_writes/hist_minute.parquet
"""
from __future__ import annotations

import contextlib
import logging
import threading
import time
from datetime import date, datetime, time as dtime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import polars as pl
import yaml

from app.config import settings
from app.market_time import cn_today
from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "hist_minute_source.yaml"
LEDGER_NAME = "hist_minute"
DISPLAY_NAME = "分时备用接口"

DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 300.0

# 完整交易日约 241 点 (09:25 集合竞价 + 240 根连续竞价)。上游偶有只回半天
# (上午 120 根) 的情况, 半个交易日仍然可画图, 低于此值才视为源侧异常;
# 当日盘中按已出分钟递减, 只要求有足够样本能画图。
_MIN_BARS_HISTORY = 120
_MIN_BARS_TODAY = 5

_WINDOW_START = dtime(9, 15)
_WINDOW_END = dtime(15, 5)

_TODAY_TTL_S = 60.0
_HISTORY_TTL_S = 3600.0
_FAIL_TTL_S = 300.0

_FRAME_COLUMNS = ["symbol", "datetime", "open", "high", "low", "close", "volume", "amount"]

_cache_lock = threading.Lock()
_cache: dict[tuple, tuple[float, pl.DataFrame, str | None]] = {}
_ledger_cache: dict[tuple, tuple[float, str | None]] = {}
_config_lock = threading.Lock()
_config_state: tuple[tuple, dict | None] | None = None


def config_path() -> Path:
    return settings.data_dir / CONFIG_FILENAME


def _ledger_path() -> Path:
    return settings.data_dir / "data_source_writes" / f"{LEDGER_NAME}.parquet"


def _minute_dir(asset_type: str) -> Path:
    folder = "kline_etf_minute" if asset_type == "etf" else "kline_minute"
    return settings.data_dir / folder


def _empty() -> pl.DataFrame:
    return pl.DataFrame()


def _upstream_symbol(symbol: str) -> str:
    """内部代码 → 上游代码。

    该接口族: **指数**要交易所前缀 (000001.SH → SH000001, 399001.SZ →
    SZ399001), **个股**用裸代码 (600519.SH → 600519, 000001.SZ → 000001)。
    无后缀的裸代码原样透传。
    """
    text = (symbol or "").strip().upper()
    if "." not in text:
        return text
    code, _, exchange = text.partition(".")
    if exchange not in {"SH", "SZ", "BJ"} or not code:
        return text
    is_index = (
        exchange == "SH" and code.startswith(("000", "880", "930", "950"))
    ) or (exchange == "SZ" and code.startswith("399"))
    return f"{exchange}{code}" if is_index else code


# ---------------------------------------------------------------- 配置读写

def _normalize_config(raw: dict | None) -> dict:
    raw = raw or {}
    url = str(raw.get("url") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("接口地址必须以 http:// 或 https:// 开头")
    method = str(raw.get("method") or "GET").strip().upper()
    if method not in {"GET", "POST"}:
        raise ValueError("请求方法只支持 GET / POST")
    try:
        timeout = float(raw.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError) as e:
        raise ValueError(f"超时必须是 0~{MAX_TIMEOUT:g} 之间的数字") from e
    if not 0 < timeout <= MAX_TIMEOUT:
        raise ValueError(f"超时必须在 0~{MAX_TIMEOUT:g} 秒之间")

    field_map = raw.get("field_map") or {}
    if not isinstance(field_map, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in field_map.items()
    ):
        raise ValueError("字段映射必须是 {上游字段: 标准字段} 的对象")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("额外参数必须是对象")

    return {
        "url": url,
        "method": method,
        "symbol_param": str(raw.get("symbol_param") or "code").strip() or "code",
        "date_param": str(raw.get("date_param") or "date").strip() or "date",
        "response_path": str(raw.get("response_path") or "").strip(),
        "field_map": {str(k): str(v) for k, v in field_map.items()},
        "params": dict(params),
        "timeout": timeout,
    }


def load_source_config() -> dict | None:
    """读取独立配置; 未配置返回 None, 文件损坏抛 ValueError。"""
    path = config_path()
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"分时备用接口配置解析失败: {e}") from e
    return _normalize_config(raw)


def save_source_config(raw: dict) -> dict:
    cfg = _normalize_config(raw)
    if not cfg["url"]:
        raise ValueError("请填写接口地址")
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    clear_caches()
    _reset_config()
    return cfg


def delete_source_config() -> None:
    config_path().unlink(missing_ok=True)
    clear_caches()
    _reset_config()


def _reset_config() -> None:
    global _config_state
    with _config_lock:
        _config_state = None


def _config() -> dict | None:
    """配置未变时复用; 文件变化 (保存/删除) 自动重读。"""
    global _config_state
    path = config_path()
    try:
        stat = path.stat()
    except FileNotFoundError:
        _reset_config()
        return None
    signature = (str(path), stat.st_mtime_ns, stat.st_size)
    with _config_lock:
        if _config_state is not None and _config_state[0] == signature:
            return _config_state[1]
    try:
        cfg = load_source_config()
    except ValueError as e:
        logger.warning("分时备用接口配置不可用: %s", e)
        cfg = None
    with _config_lock:
        _config_state = (signature, cfg)
    return cfg


# ---------------------------------------------------------------- 请求

def _build_url(cfg: dict, symbol: str, trade_date: date) -> tuple[str, dict]:
    """把代码/日期写进 URL 查询串; 返回 (url, POST 用的请求体)。"""
    code = _upstream_symbol(symbol)
    day = trade_date.strftime("%Y%m%d")
    url = cfg["url"].replace("{symbol}", code).replace("{date}", day)
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[cfg["symbol_param"]] = code
    query[cfg["date_param"]] = day
    for key, value in cfg["params"].items():
        query.setdefault(str(key), str(value))
    query.setdefault("format", "json")
    body = {cfg["symbol_param"]: code, cfg["date_param"]: day}
    body.update({str(k): v for k, v in cfg["params"].items()})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)), body


def _parse_clock(value) -> dtime | None:
    text = str(value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _points_frame(payload, symbol: str, trade_date: date) -> pl.DataFrame | None:
    """解析单只单日分钟点 ({'data': {'points': [{'t','p','vol','amt'}]}})。

    返回 None 表示不是这种形态, 交由通用行列表处理。
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("points"), list):
        return None
    rows: list[dict] = []
    for item in data["points"]:
        if not isinstance(item, dict):
            continue
        clock = _parse_clock(item.get("t"))
        price = _num(item.get("p"))
        if clock is None or price is None or price <= 0:
            continue
        rows.append({
            "symbol": symbol,
            "datetime": datetime.combine(trade_date, clock),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": _num(item.get("vol")) or 0.0,
            "amount": _num(item.get("amt")),
        })
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _rows_frame(payload, cfg: dict, trade_date: date) -> pl.DataFrame:
    """通用行列表: response_path 取行 + field_map (留空自动识别常见列名)。"""
    from app.data_providers.custom.mapper import extract_rows, map_rows

    rows = extract_rows(payload, cfg["response_path"])
    df = map_rows(rows, cfg["field_map"], infer=not cfg["field_map"])
    if df.is_empty() or "datetime" not in df.columns:
        return df
    dtype = df.schema["datetime"]
    if dtype == pl.Utf8:
        # 只有 HH:MM 的接口: 与请求日期拼成完整时间
        parsed = df["datetime"].str.strptime(pl.Datetime("us"), "%Y-%m-%d %H:%M:%S", strict=False)
        if parsed.null_count() == df.height:
            clocks = [_parse_clock(v) for v in df["datetime"].to_list()]
            if all(c is not None for c in clocks):
                df = df.with_columns(
                    pl.Series("datetime", [datetime.combine(trade_date, c) for c in clocks])
                )
        else:
            df = df.with_columns(parsed.alias("datetime"))
    return df


def request_frame(cfg: dict, symbol: str, trade_date: date) -> pl.DataFrame:
    """按配置请求单只单日分钟数据 (不落盘)。"""
    url, body = _build_url(cfg, symbol, trade_date)
    with httpx.Client(timeout=cfg["timeout"], follow_redirects=True) as client:
        if cfg["method"] == "POST":
            resp = client.post(url, json=body)
        else:
            resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    df = _points_frame(payload, symbol, trade_date)
    if df is None:
        df = _rows_frame(payload, cfg, trade_date)
    return df


# ---------------------------------------------------------------- 校验与落盘

def _normalize_frame(
    df: pl.DataFrame, symbol: str, trade_date: date,
) -> pl.DataFrame | None:
    """校验并收敛为可落盘的标准分钟帧; 不合格返回 None (不写盘)。"""
    if df is None or df.is_empty():
        return None
    required = {"datetime", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        logger.warning("分时备用接口缺少必要字段 %s, 丢弃", missing)
        return None

    dtype = df.schema.get("datetime")
    if isinstance(dtype, pl.Datetime) and dtype.time_zone:
        df = df.with_columns(
            pl.col("datetime").dt.convert_time_zone("Asia/Shanghai").dt.replace_time_zone(None)
        )
    df = df.with_columns(
        pl.col("datetime").cast(pl.Datetime("us"), strict=False),
        pl.lit(symbol).alias("symbol"),
    )
    if df["datetime"].null_count() == df.height:
        logger.warning("分时备用接口时间列解析失败, 丢弃")
        return None

    start = datetime.combine(trade_date, _WINDOW_START)
    end = datetime.combine(trade_date, _WINDOW_END)
    df = df.filter(
        pl.col("datetime").is_not_null()
        & (pl.col("datetime") >= start)
        & (pl.col("datetime") <= end)
    )

    for col in ("open", "high", "low", "close"):
        df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    df = df.filter(
        pl.col("open").is_not_null() & (pl.col("open") > 0)
        & pl.col("high").is_not_null() & (pl.col("high") > 0)
        & pl.col("low").is_not_null() & (pl.col("low") > 0)
        & pl.col("close").is_not_null() & (pl.col("close") > 0)
    )
    if "volume" in df.columns:
        df = df.with_columns(pl.col("volume").cast(pl.Float64, strict=False))
        df = df.filter(pl.col("volume").is_null() | (pl.col("volume") >= 0))
    else:
        df = df.with_columns(pl.lit(0.0).alias("volume"))
    if "amount" in df.columns:
        df = df.with_columns(pl.col("amount").cast(pl.Float64, strict=False))
        df = df.filter(pl.col("amount").is_null() | (pl.col("amount") >= 0))

    keep = [c for c in _FRAME_COLUMNS if c in df.columns]
    df = df.select(keep)
    df = df.unique(subset=["symbol", "datetime"], keep="last").sort("datetime")

    min_bars = _MIN_BARS_TODAY if trade_date >= cn_today() else _MIN_BARS_HISTORY
    if df.height < min_bars:
        logger.warning(
            "分时备用接口有效行数不足 (%d < %d, %s %s), 丢弃不落盘",
            df.height, min_bars, symbol, trade_date,
        )
        return None
    return df


def _record_ledger(df: pl.DataFrame, asset_type: str) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = df.select("symbol", "datetime").with_columns(
        pl.col("datetime").cast(pl.Datetime("us")),
        pl.lit(asset_type).alias("asset_type"),
        pl.lit(DISPLAY_NAME).alias("display"),
    )
    if path.exists():
        try:
            existing = pl.read_parquet(path)
            incoming = pl.concat([existing, incoming], how="diagonal_relaxed")
        except Exception as e:  # noqa: BLE001 — 台账损坏不阻塞主流程
            logger.warning("分时备用接口台账读取失败, 重建: %s", e)
    merged = incoming.unique(subset=["symbol", "datetime", "asset_type"], keep="last")
    from app.services.kline_sync import _atomic_write_parquet

    _atomic_write_parquet(merged.sort(["symbol", "datetime"]), path)


def _persist(df: pl.DataFrame, asset_type: str, write_lock=None) -> None:
    from app.services.kline_sync import _write_minute_partition

    lock = write_lock if write_lock is not None else contextlib.nullcontext()
    with lock:
        _write_minute_partition(df, _minute_dir(asset_type), missing_only=True)


def fetch(
    symbol: str,
    trade_date: date,
    asset_type: str = "stock",
    *,
    write_lock=None,
) -> tuple[pl.DataFrame, str | None]:
    """按需拉取单只单日分时。返回 (标准分钟帧, 生效的备用接口名)。

    未配置 / 请求失败 / 数据校验不通过 → 返回 (空帧, None)。
    成功结果落盘到主分钟存储, 并记台账供删除时精确清除。
    """
    cfg = _config()
    if cfg is None or not cfg["url"]:
        return _empty(), None

    key = (symbol, trade_date, asset_type)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1], hit[2]

    try:
        raw = request_frame(cfg, symbol, trade_date)
    except Exception as e:  # noqa: BLE001 — 备用源失败不阻塞主流程
        logger.warning("分时备用接口拉取失败 (%s %s): %s", symbol, trade_date, e)
        _cache[key] = (now + _FAIL_TTL_S, _empty(), None)
        return _empty(), None

    df = _normalize_frame(raw, symbol, trade_date)
    if df is None:
        _cache[key] = (now + _FAIL_TTL_S, _empty(), None)
        return _empty(), None

    try:
        _persist(df, asset_type, write_lock=write_lock)
        _record_ledger(df, asset_type)
    except Exception as e:  # noqa: BLE001 — 落盘失败不影响本次展示
        logger.warning("分时备用接口落盘失败 (不影响本次展示): %s", e)
    _cache[key] = (now + _ttl(trade_date), df, DISPLAY_NAME)
    return df, DISPLAY_NAME


def _ttl(trade_date: date) -> float:
    return _TODAY_TTL_S if trade_date >= cn_today() else _HISTORY_TTL_S


def written_by(symbol: str, trade_date: date, asset_type: str = "stock") -> str | None:
    """该 (symbol, 日期) 是否由备用接口写入; 是则返回名称, 供前端角标。"""
    key = (symbol, trade_date, asset_type)
    now = time.monotonic()
    with _cache_lock:
        hit = _ledger_cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]

    found: str | None = None
    path = _ledger_path()
    if path.exists():
        start = datetime.combine(trade_date, dtime(0, 0))
        end = datetime.combine(trade_date, dtime(23, 59, 59))
        try:
            rows = pl.read_parquet(path).filter(
                (pl.col("symbol") == symbol)
                & (pl.col("asset_type") == asset_type)
                & (pl.col("datetime") >= start)
                & (pl.col("datetime") <= end)
            )
            if not rows.is_empty():
                found = DISPLAY_NAME
        except Exception:  # noqa: BLE001 — 台账损坏按无记录处理
            pass

    with _cache_lock:
        _ledger_cache[key] = (now + _TODAY_TTL_S, found)
    return found


def purge(*, write_lock=None) -> int:
    """清除备用接口写入的分钟行, 返回删除行数; 主分钟源历史不受影响。"""
    path = _ledger_path()
    if not path.exists():
        return 0
    try:
        ledger = pl.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        logger.warning("分时备用接口台账读取失败, 跳过清除: %s", e)
        return 0
    if ledger.is_empty():
        path.unlink(missing_ok=True)
        return 0

    from app.services.kline_sync import _atomic_write_parquet

    removed = 0
    lock = write_lock if write_lock is not None else contextlib.nullcontext()
    with lock:
        for asset_type in ledger["asset_type"].unique().to_list():
            group = ledger.filter(pl.col("asset_type") == asset_type)
            minute_dir = _minute_dir(str(asset_type))
            grouped = group.with_columns(
                pl.col("datetime").dt.date().alias("_day")
            ).partition_by("_day", maintain_order=True)
            for day_df in grouped:
                day = day_df["_day"][0]
                out = minute_dir / f"date={day}" / "part.parquet"
                if not out.exists():
                    continue
                try:
                    existing = pl.read_parquet(out).with_columns(
                        pl.col("datetime").cast(pl.Datetime("us"))
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("分时备用接口清除时分区读取失败 %s: %s", out, e)
                    continue
                drop_keys = day_df.select("symbol", "datetime").unique()
                kept = existing.join(drop_keys, on=["symbol", "datetime"], how="anti")
                removed += existing.height - kept.height
                if kept.is_empty():
                    out.unlink(missing_ok=True)
                else:
                    _atomic_write_parquet(kept.sort(["symbol", "datetime"]), out)

    path.unlink(missing_ok=True)
    clear_caches()
    return removed


def clear_caches() -> None:
    with _cache_lock:
        _cache.clear()
        _ledger_cache.clear()
