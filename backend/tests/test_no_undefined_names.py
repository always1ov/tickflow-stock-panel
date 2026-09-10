"""[R275] 全仓不许有「用了没定义的名字」—— 这类错跑到那一行就是 500。

## 为什么值得单独立一道闸

用户报「行业分析/概念分析这几个页面好像不正常了」「都在报错 500」。查下来是
`api/screener.py` 的 `market_snapshot` 里用了一个**从来没被赋值**的 `ext_value_maps`,
走到那一行必然 `NameError` → 整个接口 500 → 行业分析、概念分析、成分股弹窗三处的
行情数字全空。

**它是 R145 引进来的, 而 R145 的标题正是「修…500」** —— 从别处(那边有这个局部量)
复制一段过来, 变量没跟着来。这类错的特点是:

- **机器完全查得出来**(`ruff --select F821` 一秒钟出结果)
- **测试很难覆盖到**(要恰好调到那一个分支)
- **在仓库里躺了九天没人发现**

躺九天的原因不是没人跑 ruff, 而是**跑了也看不见**: 全仓默认规则下有两千多条中文
标点告警(`RUF001/002/003`), 真错埋在噪音里。所以这道闸**只选 F821 这一条**, 期望值
是**零** —— 一条都不许有, 出现即失败, 不给"基线"留口子。基线一旦允许非零, 下一个
真错又会混进去。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _ruff() -> str:
    exe = shutil.which("ruff")
    if not exe:
        pytest.skip("环境里没有 ruff")
    return exe


def test_R275_全仓没有未定义的名字():
    """`F821 Undefined name` 一条都不许有。

    **期望值是零, 不是"不比上次多"。** 这类错跑到那一行就是 500, 没有"可接受的量"。
    """
    proc = subprocess.run(
        [_ruff(), "check", "app", "--select", "F821", "--output-format", "concise",
         "--no-cache"],
        cwd=BACKEND, capture_output=True, text=True, timeout=180,
    )
    hits = [ln for ln in proc.stdout.splitlines() if ": F821" in ln]
    assert not hits, (
        "用了没定义的名字 —— 跑到那一行就是 500:\n  " + "\n  ".join(hits))


def test_R275_也扫测试自己():
    """测试里写错名字会让守卫本身失效(报错被当成"这条没跑")。"""
    proc = subprocess.run(
        [_ruff(), "check", "tests", "--select", "F821", "--output-format", "concise",
         "--no-cache"],
        cwd=BACKEND, capture_output=True, text=True, timeout=180,
    )
    hits = [ln for ln in proc.stdout.splitlines() if ": F821" in ln]
    assert not hits, "测试里也有未定义的名字:\n  " + "\n  ".join(hits)


def test_R275_那道闸真的能抓到东西(tmp_path):
    """**守卫自己也要validated**: 如果 ruff 参数写错(比如规则名打错), 上面两条会
    永远绿而什么都没查。这里塞一个已知的坏文件进去, 确认它真的会被报出来。
    """
    bad = tmp_path / "坏例子.py"
    bad.write_text("def f():\n    return 从来没定义过的名字\n", encoding="utf-8")
    proc = subprocess.run(
        [_ruff(), "check", str(bad), "--select", "F821", "--output-format", "concise",
         "--no-cache"],
        cwd=BACKEND, capture_output=True, text=True, timeout=60,
    )
    assert ": F821" in proc.stdout, (
        f"这道闸抓不到已知的坏例子 —— 参数可能写错了:\n{proc.stdout}\n{proc.stderr}")


def test_R275_那一行确实删掉了():
    """回归: `market_snapshot` 不该再引用 `ext_value_maps`。

    这个接口**压根没有"扩展列"这个概念**(不收 ext_columns 参数, 只出一份轻量行情
    快照), 所以正确的修法是整行删掉 —— 补个空 dict 进去只会把一段没人要的逻辑留着。
    """
    src = (BACKEND / "app" / "api" / "screener.py").read_text(encoding="utf-8")
    fn = src[src.index("def market_snapshot("):]
    fn = fn[:fn.index("\ndef ")]
    code = "\n".join(ln for ln in fn.splitlines() if not ln.strip().startswith("#"))
    assert "ext_value_maps" not in code
    assert "_rows_with_ext" not in code, "这个接口不需要扩展列"
