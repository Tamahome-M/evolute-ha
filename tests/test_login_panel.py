"""Verify registration of the embedded login screen."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from yarl import URL

from custom_components.evolute.login_panel import (
    PANEL_PATH,
    SCRIPT_URL,
    async_ensure_login_panel,
    login_panel_url,
)


async def test_panel_url_keeps_browser_origin(hass):
    """The native external step requires an absolute URL that works remotely."""
    request = SimpleNamespace(
        url=URL("https://ha.example.net:8443/api/config/config_entries/flow/id")
    )
    hass.config.internal_url = "http://homeassistant.local:8123"
    with patch("custom_components.evolute.login_panel.http.current_request") as current:
        current.get.return_value = request
        assert (
            login_panel_url(hass, "flow-1")
            == "https://ha.example.net:8443/evolute-login?flow_id=flow-1"
        )


async def test_headless_installation(hass):
    """Token/API setup remains possible without loading the frontend."""
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel"
    ) as register:
        assert not await async_ensure_login_panel(hass)
    register.assert_not_called()


async def test_register_once_and_require_admin(hass, monkeypatch):
    """Concurrent flows share one admin-only panel and one static route."""
    hass.config.components.add("frontend")
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel",
        new_callable=AsyncMock,
    ) as register:
        assert all(
            await asyncio.gather(*(async_ensure_login_panel(hass) for _ in range(3)))
        )
        register.assert_awaited_once_with(
            hass,
            frontend_url_path=PANEL_PATH,
            webcomponent_name="evolute-login-panel-v6",
            module_url=f"{SCRIPT_URL}?v=6",
            require_admin=True,
        )
    http.async_register_static_paths.assert_awaited_once()
    route = http.async_register_static_paths.call_args.args[0][0]
    assert route.url_path == SCRIPT_URL
    assert Path(route.path).is_file()
    assert not route.cache_headers


async def test_registration_can_retry_after_failure(hass, monkeypatch):
    """A failed panel registration does not duplicate the static path on retry."""
    hass.config.components.add("frontend")
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("Not ready"), None],
    ):
        assert not await async_ensure_login_panel(hass)
        assert await async_ensure_login_panel(hass)
    http.async_register_static_paths.assert_awaited_once()


async def test_legacy_static_path_api(hass, monkeypatch):
    """Older supported HA versions use the original static registration API."""
    hass.config.components.add("frontend")
    http = SimpleNamespace(register_static_path=Mock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel",
        new_callable=AsyncMock,
    ):
        assert await async_ensure_login_panel(hass)
    assert http.register_static_path.call_args.args[0] == SCRIPT_URL
