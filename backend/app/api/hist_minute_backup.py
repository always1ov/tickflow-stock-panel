"""分时备用接口设置 (独立于自定义数据源, 全系统共用)。"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import hist_minute_backup
from app.services.trading_day import expected_latest_bar_date

router = APIRouter(prefix="/api/settings/hist-minute-backup", tags=["settings"])


class BackupConfigIn(BaseModel):
    url: str = ""
    method: str = "GET"
    symbol_param: str = "code"
    date_param: str = "date"
    response_path: str = ""
    field_map: dict[str, str] = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)
    timeout: float = 30.0


def _status() -> dict:
    try:
        cfg = hist_minute_backup.load_source_config()
    except ValueError as e:
        return {"configured": True, "config": None, "error": str(e)}
    return {
        "configured": bool(cfg and cfg.get("url")),
        "config": cfg,
        "display_name": hist_minute_backup.DISPLAY_NAME,
    }


@router.get("")
def get_hist_minute_backup():
    return _status()


@router.put("")
def save_hist_minute_backup(body: BackupConfigIn):
    try:
        hist_minute_backup.save_source_config(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _status()


@router.delete("")
def delete_hist_minute_backup(request: Request):
    purged = 0
    try:
        purged = hist_minute_backup.purge(
            write_lock=getattr(request.app.state.repo, "_write_lock", None),
        )
    except Exception as e:  # noqa: BLE001 — 清除失败不阻塞删除配置
        import logging
        logging.getLogger(__name__).warning("清除分时备用接口写入的分钟数据失败: %s", e)
    hist_minute_backup.delete_source_config()
    return {"configured": False, "purged_minute_rows": purged}


@router.post("/test")
def test_hist_minute_backup(symbol: str = "000001.SH"):
    """单只试拉最近一个有数据的交易日 (最多回溯 3 个工作日, 不落盘)。"""
    cfg = hist_minute_backup._config()
    if cfg is None or not cfg["url"]:
        raise HTTPException(status_code=400, detail="尚未配置分时备用接口")

    target: date = expected_latest_bar_date()
    last: tuple[str, int] | None = None
    for _ in range(3):
        try:
            df = hist_minute_backup.request_frame(cfg, symbol, target)
        except Exception as e:  # noqa: BLE001 — 上游异常回传可读原因
            raise HTTPException(status_code=400, detail=f"请求失败: {e}") from e
        if not df.is_empty():
            return {
                "ok": True,
                "trade_date": target.isoformat(),
                "rows": df.height,
                "columns": df.columns,
                "preview": df.head(5).to_dicts(),
            }
        last = ("空结果", df.height)
        target -= timedelta(days=1)
        while target.weekday() >= 5:
            target -= timedelta(days=1)
    return {
        "ok": False,
        "trade_date": target.isoformat(),
        "rows": last[1] if last else 0,
        "columns": [],
        "preview": [],
    }
