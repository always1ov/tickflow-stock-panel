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


def test_external_page_defaults_are_backward_compatible():
    assert preferences.get_external_page_config() == {
        "external_page_enabled": True,
        "external_page_name": "利弗莫尔趋势",
        "external_page_url": "https://livermore-trend-dashboard-tigergu.netlify.app/",
        # [R117] 新增两字段, 默认值即上游原行为(内嵌整站, 无 AI 提示)
        "external_page_mode": "iframe",
        "external_page_ai_hint": "",
    }


def test_update_external_page_persists_configuration():
    result = settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
        enabled=False,
        name="  我的盘面  ",
        url=" https://example.com/dashboard?view=trend ",
    ))

    assert result == {
        "external_page_enabled": False,
        "external_page_name": "我的盘面",
        "external_page_url": "https://example.com/dashboard?view=trend",
        "external_page_mode": "iframe",
        "external_page_ai_hint": "",
    }
    assert preferences.get_external_page_config() == result


def test_r117_mode_and_hint_round_trip():
    settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
        enabled=True, name="盘面", url="https://example.com/",
        mode="fetch", ai_hint="  只要涨幅榜前 20  ",
    ))
    got = preferences.get_external_page_config()
    assert got["external_page_mode"] == "fetch"
    assert got["external_page_ai_hint"] == "只要涨幅榜前 20"


def test_r117_omitted_fields_keep_previous_values():
    """老客户端(只发 enabled/name/url)不该把已存的模式和提示抹掉。"""
    settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
        enabled=True, name="盘面", url="https://example.com/",
        mode="fetch", ai_hint="只要涨幅榜",
    ))
    settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
        enabled=True, name="改名了", url="https://example.com/",
    ))
    got = preferences.get_external_page_config()
    assert got["external_page_name"] == "改名了"
    assert got["external_page_mode"] == "fetch"
    assert got["external_page_ai_hint"] == "只要涨幅榜"


def test_r117_unknown_mode_falls_back_to_iframe():
    preferences.save({"external_page_mode": "上一版写坏的值"})
    assert preferences.get_external_page_config()["external_page_mode"] == "iframe"


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
            name="外部网页",
            url=url,
        ))
    assert exc.value.status_code == 400


def test_update_external_page_rejects_blank_name():
    with pytest.raises(HTTPException) as exc:
        settings_api.update_external_page(settings_api.ExternalPagePrefsIn(
            enabled=True,
            name="   ",
            url="https://example.com/",
        ))
    assert exc.value.status_code == 400
