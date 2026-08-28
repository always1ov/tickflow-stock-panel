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
    }
    assert preferences.get_external_page_config() == result


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
