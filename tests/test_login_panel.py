"""Verify registration of the embedded login screen."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components.evolute.login_panel import (
    HANDOFF_MODULE_URL,
    HANDOFF_SCRIPT_URL,
    PANEL_PATH,
    SCRIPT_URL,
    async_ensure_login_panel,
)


async def test_headless_installation(hass):
    """Token/API setup remains possible without loading the frontend."""
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel"
    ) as register:
        assert not await async_ensure_login_panel(hass)
    register.assert_not_called()


async def test_register_once_and_require_admin(hass, monkeypatch):
    """Concurrent flows share the panel, script routes and automatic handoff."""
    hass.config.components.add("frontend")
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel",
        new_callable=AsyncMock,
    ) as register, patch(
        "custom_components.evolute.login_panel.frontend.add_extra_js_url"
    ) as add_module:
        assert all(await asyncio.gather(*(async_ensure_login_panel(hass) for _ in range(3))))
        register.assert_awaited_once_with(
            hass,
            frontend_url_path=PANEL_PATH,
            webcomponent_name="evolute-login-panel-v5",
            module_url=f"{SCRIPT_URL}?v=5",
            require_admin=True,
        )
        add_module.assert_called_once_with(hass, HANDOFF_MODULE_URL)
    http.async_register_static_paths.assert_awaited_once()
    routes = http.async_register_static_paths.call_args.args[0]
    assert [route.url_path for route in routes] == [SCRIPT_URL, HANDOFF_SCRIPT_URL]
    assert all(Path(route.path).is_file() and not route.cache_headers for route in routes)


async def test_registration_can_retry_after_failure(hass, monkeypatch):
    """A failed panel registration does not duplicate the static path on retry."""
    hass.config.components.add("frontend")
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("Not ready"), None],
    ), patch(
        "custom_components.evolute.login_panel.frontend.add_extra_js_url"
    ) as add_module:
        assert not await async_ensure_login_panel(hass)
        assert await async_ensure_login_panel(hass)
        add_module.assert_called_once_with(hass, HANDOFF_MODULE_URL)
    http.async_register_static_paths.assert_awaited_once()


async def test_legacy_static_path_api(hass, monkeypatch):
    """Older supported HA versions use the original static registration API."""
    hass.config.components.add("frontend")
    http = SimpleNamespace(register_static_path=Mock())
    monkeypatch.setattr(hass, "http", http, raising=False)
    with patch(
        "custom_components.evolute.login_panel.panel_custom.async_register_panel",
        new_callable=AsyncMock,
    ), patch("custom_components.evolute.login_panel.frontend.add_extra_js_url"):
        assert await async_ensure_login_panel(hass)
    assert [call.args[0] for call in http.register_static_path.call_args_list] == [
        SCRIPT_URL,
        HANDOFF_SCRIPT_URL,
    ]

