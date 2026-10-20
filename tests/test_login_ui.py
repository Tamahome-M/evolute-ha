"""Verify the native login field is available without a custom HA panel."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components import frontend

from custom_components.evolute.login_ui import (
    MODULE_URL,
    SCRIPT_URL,
    async_ensure_login_ui,
)


async def test_headless_installation(hass):
    assert not await async_ensure_login_ui(hass)


async def test_register_once_before_frontend_finishes(hass, monkeypatch):
    """Register as soon as HA's module manager exists, even during startup."""
    on_change = Mock()
    manager = frontend.UrlManager(on_change, [])
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = manager
    assert "frontend" not in hass.config.components
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    assert all(await asyncio.gather(*(async_ensure_login_ui(hass) for _ in range(3))))
    assert manager.urls == {MODULE_URL}
    on_change.assert_called_once_with("added", MODULE_URL)
    http.async_register_static_paths.assert_awaited_once()
    routes = http.async_register_static_paths.call_args.args[0]
    assert len(routes) == 1 and routes[0].url_path == SCRIPT_URL
    assert Path(routes[0].path).is_file() and not routes[0].cache_headers


async def test_registration_can_retry_after_failure(hass, monkeypatch):
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = object()
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_ui.frontend.add_extra_js_url",
        side_effect=[RuntimeError("Not ready"), None],
    ) as add:
        assert not await async_ensure_login_ui(hass)
        assert await async_ensure_login_ui(hass)
        assert add.call_count == 2
    http.async_register_static_paths.assert_awaited_once()


async def test_legacy_static_path_api(hass, monkeypatch):
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = object()
    http = SimpleNamespace(register_static_path=Mock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch("custom_components.evolute.login_ui.frontend.add_extra_js_url"):
        assert await async_ensure_login_ui(hass)
    http.register_static_path.assert_called_once()
    assert http.register_static_path.call_args.args[0] == SCRIPT_URL
