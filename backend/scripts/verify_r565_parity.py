"""R565 升级前 vs 现在: 副图指标逐点对拍。

用法(在 backend 目录下):
    .venv/bin/python scripts/verify_r565_parity.py            # 默认对 R565 时点
    .venv/bin/python scripts/verify_r565_parity.py --rev 0b174ac9 --symbols 50

做什么: 从 git 里取出指定时点的 `quant_macd.py` / `trend_quant.py`, 与当前实现喂同一批
K 线(真实库 + 合成序列), 逐字段逐点比较。退出码 0 = 完全一致, 1 = 有差异。

为什么要有它: R566 把图表从 ECharts 换成 lightweight 之后, 「数值是不是还是原来那份」
只能靠对拍回答; 一次性脚本跑完就没了, 这里固化成可复跑的一条命令。
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent

TOL = 1e-12
# 与 AnalysisKChart 的调用一致: 指标吃纯 Python 序列, 不依赖框架
SYNTH_LEN = 1500


def load_from_rev(rev: str, module_file: str, alias: str):
    """把 git 里某个时点的模块写到临时目录再导入(dataclass 需要模块已注册)。"""
    src = subprocess.check_output(
        ['git', 'show', f'{rev}:backend/app/indicators/{module_file}'], cwd=REPO).decode()
    tmp = Path(tempfile.mkdtemp(prefix='r565parity-')) / module_file
    tmp.write_text(src, encoding='utf-8')
    spec = importlib.util.spec_from_file_location(alias, tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def as_dict(obj) -> dict:
    return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}


def compare(a, b, path: str, bad: list[str], stats: dict) -> None:
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)):
            bad.append(f'{path}: 类型 {type(a).__name__} vs {type(b).__name__}')
            return
        if len(a) != len(b):
            bad.append(f'{path}: 长度 {len(a)} vs {len(b)}')
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            compare(x, y, f'{path}[{i}]', bad, stats)
        return
    stats['n'] += 1
    if a is None or b is None:
        if a is not b:
            bad.append(f'{path}: {a} vs {b}')
        return
    try:
        delta = abs(float(a) - float(b))
    except (TypeError, ValueError):
        if a != b:
            bad.append(f'{path}: {a!r} vs {b!r}')
        return
    stats['max'] = max(stats['max'], delta)
    if delta > TOL:
        bad.append(f'{path}: {a} vs {b} (Δ={delta:.3e})')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rev', default='0b174ac9', help='对照时点(R565 台账提交), 默认 0b174ac9')
    parser.add_argument('--symbols', type=int, default=25, help='取多少个交易日样本(按成交额), 默认 25')
    parser.add_argument('--skip-synthetic', action='store_true', help='只跑真实库')
    args = parser.parse_args()

    import polars as pl

    sys.path.insert(0, str(BACKEND))
    from app.config import settings
    from app.indicators import quant_macd as new_qm
    from app.indicators import trend_quant as new_tq

    old_qm = load_from_rev(args.rev, 'quant_macd.py', 'old_quant_macd')
    old_tq = load_from_rev(args.rev, 'trend_quant.py', 'old_trend_quant')

    total = {'n': 0, 'max': 0.0}
    problems: list[str] = []

    def check(tag: str, old_mod, new_mod, argv: tuple, label: str) -> None:
        old, new = as_dict(old_mod.compute(*argv)), as_dict(new_mod.compute(*argv))
        only_old, only_new = set(old) - set(new), set(new) - set(old)
        if only_old or only_new:
            problems.append(f'{label} {tag}: 字段差异 旧独有={sorted(only_old)} 新独有={sorted(only_new)}')
        bad, stats = [], {'n': 0, 'max': 0.0}
        for key in sorted(set(old) & set(new)):
            compare(new[key], old[key], f'{tag}.{key}', bad, stats)
        total['n'] += stats['n']
        total['max'] = max(total['max'], stats['max'])
        if bad:
            problems.append(f'{label} {tag}: {len(bad)} 处不一致, 例 {bad[:2]}')

    # ---- 真实库 ----
    kline = Path(settings.data_dir) / 'kline_daily'
    files = sorted(kline.glob('*/*.parquet'))
    if not files:
        print(f'[skip] 没有真实库数据: {kline}')
        return 1
    top = (pl.read_parquet(files[-1]).sort('amount', descending=True)
           .head(args.symbols)['symbol'].to_list())
    frame = (pl.scan_parquet(str(kline / '*/*.parquet'))
             .filter(pl.col('symbol').is_in(top))
             .select(['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'])
             .collect().sort(['symbol', 'date']))

    bars = 0
    for symbol, group in frame.group_by('symbol', maintain_order=True):
        opens, highs, lows, closes, volumes = (
            group[k].to_list() for k in ('open', 'high', 'low', 'close', 'volume'))
        bars += len(closes)
        check('quant_macd', old_qm, new_qm, (closes, volumes), f'{symbol} ({len(closes)}根)')
        check('trend_quant', old_tq, new_tq,
              (opens, highs, lows, closes, volumes), f'{symbol} ({len(closes)}根)')
    print(f'真实库: {len(top)} 只 / {bars} 根')

    # ---- 合成序列 ----
    if not args.skip_synthetic:
        random.seed(20261114)
        shapes = {
            '单边涨': lambda i: 10 + i * 0.05,
            '单边跌': lambda i: 60 - i * 0.03,
            '正弦': lambda i: 30 + 8 * math.sin(i / 17),
            '横盘': lambda i: 20 + random.uniform(-0.2, 0.2),
            '中途反转': lambda i: 15 + 6 * math.sin(i / 40) + (i - 750) * 0.02,
        }
        for name, fn in shapes.items():
            close = [fn(i) for i in range(SYNTH_LEN)]
            volumes = [1000.0 + (i * 7) % 5000 for i in range(SYNTH_LEN)]
            check('quant_macd', old_qm, new_qm, (close, volumes), f'合成-{name}')
            check('trend_quant', old_tq, new_tq,
                  ([x * 0.999 for x in close], [x * 1.01 for x in close],
                   [x * 0.99 for x in close], close, volumes), f'合成-{name}')
        print(f'合成序列: {len(shapes)} 组 / {SYNTH_LEN * len(shapes)} 根')

    print(f'比较的数值点: {total["n"]:,}')
    print(f'最大绝对差: {total["max"]:.3e}')
    print(f'不一致项: {len(problems)}')
    for item in problems[:20]:
        print('  -', item)
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
