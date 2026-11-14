import pytest
from fastapi import HTTPException

from app.api import settings as settings_api
from app.config import settings
from app.services import preferences


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    preferences._invalidate_cache()
    yield
    preferences._invalidate_cache()


def test_external_page_defaults_to_empty_link_directory():
    assert preferences.get_external_page_config() == {
        "external_page_enabled": True,
        "external_page_name": "外链导航",
        # [R611] 外部网页改成外链导航: 没有预置链接, 页面引导去设置里添加
        "external_links": [],
    }


def test_update_external_page_persists_links():
    result = settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
        enabled=False,
        name="  我的导航  ",
        links=[
            {"name": " 利弗莫尔趋势 ", "url": " https://example.com/trend "},
            {"name": "", "url": "https://example.com/tools"},
        ],
    ))

    assert result == {
        "external_page_enabled": False,
        "external_page_name": "我的导航",
        "external_links": [
            {"name": "利弗莫尔趋势", "url": "https://example.com/trend"},
            # 没填名字时用地址兜底
            {"name": "https://example.com/tools", "url": "https://example.com/tools"},
        ],
    }
    assert preferences.get_external_page_config() == result


def test_links_are_deduped_and_unsafe_schemes_dropped():
    preferences.save({"external_links": [
        {"name": "A", "url": "https://example.com/"},
        {"name": "重复", "url": "https://example.com/"},
        {"name": "脚本", "url": "javascript:alert(1)"},
        {"name": "不是对象"},
    ]})
    assert preferences.get_external_page_config()["external_links"] == [
        {"name": "A", "url": "https://example.com/"},
    ]


def test_r611_legacy_single_url_is_migrated_once():
    """老 preferences 里的 external_page_url 迁成第一条外链; 保存过一次后不再回读。"""
    preferences.save({
        "external_page_name": "利弗莫尔趋势",
        "external_page_url": "https://old.example.com/",
        "external_page_mode": "fetch",
        "external_page_ai_hint": "只要涨幅榜",
    })
    got = preferences.get_external_page_config()
    assert "external_page_url" not in got
    # 站名迁进链接名, 页面本身叫「外链导航」
    assert got["external_page_name"] == "外链导航"
    assert got["external_links"] == [
        {"name": "利弗莫尔趋势", "url": "https://old.example.com/"},
    ]

    # 用户把这条删掉并保存 —— 老字段还在文件里, 也不许复活
    settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
        enabled=True, name="外链导航", links=[],
    ))
    assert preferences.get_external_page_config()["external_links"] == []


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "data:text/html,hello",
    "//example.com/path",
    "https://user:secret@example.com/",
])
def test_update_external_page_rejects_unsafe_url(url):
    with pytest.raises(HTTPException) as exc:
        settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
            enabled=True,
            name="外链导航",
            links=[{"name": "站点", "url": url}],
        ))
    assert exc.value.status_code == 400


def test_update_external_page_rejects_blank_name():
    with pytest.raises(HTTPException) as exc:
        settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
            enabled=True,
            name="   ",
            links=[],
        ))
    assert exc.value.status_code == 400
