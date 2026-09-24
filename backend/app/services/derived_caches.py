"""[R496 · fork 增强] 日K衍生缓存登记表 —— 谁从日K算出来、放在哪、什么时候作废, 写在一处。

用户: 「做第2条」(把散在各处的衍生缓存登记到一处, 改写日K之后统一通知一次)。

## 为什么要有它

从带指标日K(`kline_daily_enriched` 等)算出来、存下来的东西有四份, 各有各的作废规则。
R493 复查就查出过一处「除权重算后副本没跟着作废」—— 新加一份缓存时, 没人记得要在
改写日K的那几处补一句作废。这里把四份都登记下来, 改写日K的地方只调一个
`enriched_rewritten`, 由登记表挨个通知。以后再加缓存, 加一行登记即可。

## 什么算「改写日K」

**历史行在原地被改了值**(分区集合不变)。目前有四处, 由 `tests/test_derived_caches.py`
按调用点钉住(调了 `run_pipeline` 的文件必须也调 `enriched_rewritten`):

  · 盘后管道: 除权因子变了的那几只重算全部日期(股票), 首次/往前扩展时全量重建;
  · 盘后管道: ETF 除权因子变了的那几只;
  · 往前扩展历史(`extend_history`): 全量重建;
  · 手动「全量重算 enriched」(`/api/kline/rebuild_enriched`): 全量重建。

不算的: 每天新增一个交易日(旧行没变); 盘中实时覆写「今天」(副本不含最近 10 天,
两张副图的实时蜡烛每次请求现叠); 完整性修复先删分区再补(分区集合变了, 副本自己看得出)。

## 登记表

见 `REGISTRY`。作者的两份自带判据(按发布代次 generation 校验), 登记在此只为「一处看全」,
不接通知 —— 作者怎么管它们, 这里不插手。
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# (data_dir, 资产类型, 点名的代码; None = 这一类整个作废)
Handler = Callable[[Path, str, "tuple[str, ...] | None"], None]


@dataclass(frozen=True)
class DerivedCache:
    name: str
    lives: str          # 放在哪
    stale_when: str     # 什么时候作废
    on_rewrite: Handler | None   # 改写日K后要做的事; None = 自带判据, 不接通知


def _symbol_copies(data_dir: Path, asset_type: str, symbols: tuple[str, ...] | None) -> None:
    from app.services import symbol_daily_store
    symbol_daily_store.invalidate(data_dir, asset_type, None if symbols is None else list(symbols))


def _ohlcv_memory(_data_dir: Path, asset_type: str, symbols: tuple[str, ...] | None) -> None:
    from app.services import ohlcv_history
    ohlcv_history.invalidate(asset_type, symbols)


REGISTRY: tuple[DerivedCache, ...] = (
    DerivedCache(
        name="带指标日K内存缓存(作者)",
        lives="进程内存: KlineRepository 的 _enriched_cache / _enriched_history_cache 等",
        stale_when="盘后管道收尾 finally 里 repo.refresh_cache(); 历史缓存每次读按发布代次校验",
        on_rewrite=None,
    ),
    DerivedCache(
        name="回测矩阵缓存(作者)",
        lives="data_dir/.backtest_matrix_cache",
        stale_when="缓存键带发布代次(无代次时带分区指纹), 任何一次落盘都换代次, 旧矩阵不再命中",
        on_rewrite=None,
    ),
    DerivedCache(
        name="个股日K副本",
        lives="data_dir/.symbol_daily_cache/<stock|index|etf>/",
        stale_when="改写日K时点名作废(这里); 兜底: 分区数变了、首尾与两头外侧抽查、7 天到期",
        on_rewrite=_symbol_copies,
    ),
    DerivedCache(
        name="两张副图的单票历史内存缓存",
        lives="进程内存: services/ohlcv_history",
        stale_when="改写日K时点名作废(这里); 兜底: 库里最新交易日变了、10 分钟到期",
        on_rewrite=_ohlcv_memory,
    ),
)


def enriched_rewritten(data_dir: Path, asset_type: str, symbols: Iterable[str] | None = None) -> None:
    """日K历史被原地改写之后调一次。symbols=None → 这一类整个作废; 空列表 → 什么都不做。

    一份缓存作废失败只记日志, 不影响其他几份, 更不影响调用方(管道不能因为缓存判失败) ——
    每份缓存都还有自己的兜底判据。
    """
    syms = None if symbols is None else tuple(s for s in symbols if isinstance(s, str))
    for cache in REGISTRY:
        if cache.on_rewrite is None:
            continue
        try:
            cache.on_rewrite(Path(data_dir), asset_type, syms)
        except Exception:  # noqa: BLE001
            logger.exception("衍生缓存作废失败: %s (%s)", cache.name, asset_type)
