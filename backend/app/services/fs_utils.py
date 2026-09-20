"""文件系统小工具 — 原子写等。

历史遗留: json_report_store / strategy_cache / kline_sync 等模块里各有一份内联的
同款原子写。新代码统一用本模块的 atomic_write_text, 一处实现一处维护。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 只做类型标注; JSON 原子写的调用方 (preferences/secrets) 不必加载 polars
    import polars as pl

logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    """临时文件 + os.replace 原子替换, 避免读侧读到半截 JSON。

    传了 `mode` 时, 权限在**文件存在的那一刻**就位 —— 用 `os.open` 带着 mode
    以 `O_CREAT|O_EXCL` 创建临时文件, 而不是先写内容再 chmod。

    [安全审查 run-1] 这段的上一版注释写的是「`mode` 在替换之前打到临时文件上……
    先改临时文件就没有这个窗口」。**那句话不成立**: 临时文件是先 `write_text`
    写满内容、下一条语句才 chmod, 所以窗口并没有消失, 只是从正式路径**挪到了
    `.tmp` 路径** —— 而 `.tmp` 里躺的是同一份明文(`secrets.json` 是全部三方
    凭据, `auth.json` 是 PBKDF2 哈希**加上明文的活 session token**)。改成创建
    时带 mode 之后, 文件从不以比 `mode` 更宽的权限存在过。

    umask 只会把权限**削窄**不会放宽, 所以创建后再 chmod 一次只是把被 umask
    削掉的位补回来, 不构成新窗口。chmod 失败不再静默: Windows 上 chmod 只影响
    只读位, 失败不该让写入失败, 但一个**要求了 0600 却没拿到**的凭据文件必须
    在日志里留下痕迹, 否则就是悄悄降级。
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    if mode is not None:
        # 先以目标权限创建一个**空**文件, 再往里写内容 —— 这样内容出现时权限已经
        # 就位, 文件从不以比 mode 更宽的权限装着明文。O_EXCL 保证不复用残留的
        # .tmp (它会保留自己的旧权限)。
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode))
        try:
            # umask 只会削窄不会放宽, 这一步只是把被削掉的位补回来
            os.chmod(tmp, mode)
        except OSError as exc:
            logger.warning(
                "requested mode %o could not be applied to %s: %s", mode, path.name, exc
            )
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_parquet(df: pl.DataFrame, path: Path) -> None:
    """parquet 版原子写: 先写 `<name>.tmp` 再替换, 与 repository / kline_sync 的
    `_atomic_write_parquet` 同语义。

    直接 `df.write_parquet(path)` 在进程被 kill (dev.sh 清端口用 kill -9)、断电或
    磁盘写满时会留下半截文件, 之后读侧 `read_parquet` / `scan_parquet` 整条报错。
    `.tmp` 后缀不匹配 `*.parquet` glob, 不会被视图误读。Windows 下目标正被并发读取时
    由 `replace_with_retry` 短退避穿过。
    """
    from app.tickflow.repository import replace_with_retry  # 惰性导入, 避免模块级环

    tmp = path.with_name(path.name + ".tmp")
    df.write_parquet(tmp)
    replace_with_retry(tmp, path)
