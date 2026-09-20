"""标识符 → 文件路径的白名单守卫 (安全审查 run-1)。

这批守卫补的是同一个缺口: 几个 store 把请求里的标识符直接拼成文件名, 把
「挡住穿越」隐式外包给了路由正则。而 Starlette 的默认段正则是 `[^/]+`,
uvicorn 又在匹配之前 percent-decode —— 于是 `%2F` 变成真斜杠后单段路由不匹配
(POSIX 安全), 但 **`%5C` 解码出的反斜杠 `[^/]+` 照收**。反斜杠在 POSIX 上只是
普通文件名字符, 在 Windows 上是路径分隔符; 而冻结的桌面版里 `data_dir` 就是
exe 同级的 `data/`, `job_store/`、`custom_factors/` 与 `user_data/` 彼此平级。

所以下面每个用例都**同时**跑 POSIX 与 Windows 两种 join 语义 —— 只断言
「POSIX 上没越界」是不够的, 那恰恰是这批 bug 能活下来的原因。
"""
from __future__ import annotations

import pathlib

import pytest

from app.api.analysis import _validate_menu_id
from app.data_providers.custom import loader
from app.factors import store as factor_store
from app.services import pipeline_jobs

# 反斜杠、正斜杠、`..`、空、点、绝对路径 —— 逐个都必须被拒
TRAVERSAL_IDS = [
    "..\\..\\user_data\\secrets",
    "..\\evil",
    "../../user_data/secrets",
    "..",
    ".",
    "",
    "/etc/passwd",
    "C:\\Windows\\system32\\x",
    "a/b",
    "a\\b",
    "uf_ok\x00",
]


def test_factor_path_rejects_every_traversal_shape(tmp_path):
    for bad in TRAVERSAL_IDS:
        with pytest.raises(ValueError):
            factor_store._path(tmp_path, bad)


def test_factor_path_accepts_only_the_declared_patterns(tmp_path):
    # 模块顶部就声明了这两条 pattern, 之前只接在 to_spec 上
    assert factor_store._path(tmp_path, "uf_mom").name == "uf_mom.json"
    assert factor_store._path(tmp_path, "cf_combo").name == "cf_combo.json"
    for bad in ["mom", "UF_MOM", "uf_" + "x" * 41]:
        with pytest.raises(ValueError):
            factor_store._path(tmp_path, bad)


def test_factor_exists_probe_does_not_delete(tmp_path):
    """存在性探测不许有副作用 —— 删除路由原本拿 delete_one 当探测用。"""
    factor_store.save_one(tmp_path, {"id": "uf_mom", "label": "动量"})
    assert factor_store.exists_one(tmp_path, "uf_mom") is True
    assert factor_store.exists_one(tmp_path, "uf_mom") is True  # 第二次仍在
    assert factor_store._path(tmp_path, "uf_mom").exists()
    assert factor_store.delete_one(tmp_path, "uf_mom") is True
    assert factor_store.exists_one(tmp_path, "uf_mom") is False


def test_job_store_rejects_traversal_and_keeps_valid(tmp_path):
    store = pipeline_jobs.JobStore(store_dir=tmp_path)
    for bad in TRAVERSAL_IDS:
        assert store._job_path(bad) is None, bad
        assert store._read_file(bad) is None, bad
    good = store._job_path("job_20260920_abc")
    assert good is not None and good.parent == tmp_path.resolve()


def test_job_store_read_cannot_escape_to_a_sibling_directory(tmp_path):
    """把 job_store/ 与 user_data/ 摆成真实的平级布局, 断言读不出去。"""
    data_dir = tmp_path / "data"
    (data_dir / "user_data").mkdir(parents=True)
    (data_dir / "job_store").mkdir()
    marker = data_dir / "user_data" / "probe.json"
    marker.write_text('{"marker": "must-not-be-read"}', encoding="utf-8")

    store = pipeline_jobs.JobStore(store_dir=data_dir / "job_store")
    for bad in ["..\\user_data\\probe", "../user_data/probe"]:
        assert store._read_file(bad) is None
    assert marker.exists()


def test_job_store_write_drops_an_invalid_id_instead_of_writing(tmp_path):
    store = pipeline_jobs.JobStore(store_dir=tmp_path)
    store._write_file({"id": "..\\escape", "status": "done"})
    assert list(tmp_path.parent.glob("escape.json")) == []
    assert list(tmp_path.glob("*.json")) == []


def test_menu_id_validator_is_ascii_only(tmp_path):
    """写入侧原本用 isalnum(), 它是 Unicode 感知的 —— 全角数字/CJK 都能过,
    然后被更严的 AnalysisMenu.id ASCII pattern 在函数体里抛成 500。"""
    from fastapi import HTTPException

    assert _validate_menu_id("my_menu_1") == "my_menu_1"
    for bad in ["１２３", "菜单", "a-b", "a.b", *TRAVERSAL_IDS]:
        with pytest.raises(HTTPException) as exc:
            _validate_menu_id(bad)
        assert exc.value.status_code == 400


def test_plugin_manifest_rejects_traversal_and_absolute(tmp_path, monkeypatch):
    """plugin_manifest 下游是 yaml.safe_load + importlib.import_module。"""
    base = tmp_path / "plugins"
    (base / "fuyao").mkdir(parents=True)
    (base / "fuyao" / "plugin.yaml").write_text("name: fuyao\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plugin.yaml").write_text("name: evil\nentry: os:getcwd\n", encoding="utf-8")
    monkeypatch.setattr(loader, "plugins_dir", lambda: base)

    assert loader.plugin_manifest("fuyao") == {"name": "fuyao"}
    assert loader.plugin_manifest("FUYAO") == {"name": "fuyao"}  # 大小写归一
    for bad in ["../outside", "..\\outside", str(outside), "/tmp", "", ".."]:
        assert loader.plugin_manifest(bad) is None, bad
    # plugin_dir_of 同样 fail-closed, 不许把 `..` 当路径段带出去
    assert loader.plugin_dir_of("../outside").resolve() != outside.resolve()


def test_windows_join_semantics_are_what_make_this_matter():
    """把这批守卫存在的理由钉住: 同一个字符串在两种 join 语义下结果不同。

    这条不测目标代码, 只用标准库固定那个平台事实 —— 免得将来有人看着
    POSIX 上的行为得出「反斜杠无害」的结论, 再把上面的白名单拆掉。
    """
    posix = pathlib.PurePosixPath("/app/data/job_store") / "..\\user_data\\secrets.json"
    win = pathlib.PureWindowsPath("C:/app/data/job_store") / "..\\user_data\\secrets.json"
    # POSIX: 整串只是一个文件名, 仍在 job_store 里
    assert posix.parent == pathlib.PurePosixPath("/app/data/job_store")
    # Windows: 反斜杠是分隔符, `..` 生效 —— 走出了 job_store
    assert "user_data" in win.parts
    assert win.parts[-1] == "secrets.json"
