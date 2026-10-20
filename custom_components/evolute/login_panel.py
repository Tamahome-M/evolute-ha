"""Serve the embedded login screen using Home Assistant's custom panel API."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PANEL_PATH = "evolute-login"
SCRIPT_URL = "/evolute_static/login-panel.js"
PANEL_ELEMENT = "evolute-login-panel-v3"
PANEL_MODULE_URL = f"{SCRIPT_URL}?v=3"
_SETUP_TASK = f"{DOMAIN}_login_panel_setup"
_STATIC_REGISTERED = f"{DOMAIN}_login_panel_static"
_LOGGER = logging.getLogger(__name__)


async def async_ensure_login_panel(hass: HomeAssistant) -> bool:
    """Register once, including when several setup flows are opened together."""
    if "frontend" not in hass.config.components:
        # Headless installations can still use the existing API/token flow.
        return False

    if (task := hass.data.get(_SETUP_TASK)) is None:
        task = hass.data[_SETUP_TASK] = hass.async_create_task(
            _async_register_panel(hass), "Register Evolute login panel"
        )
    try:
        await asyncio.shield(task)
    except Exception:
        if task.done():
            hass.data.pop(_SETUP_TASK, None)
        _LOGGER.exception("Unable to register the embedded Evolute login screen")
        return False
    return True


async def _async_register_panel(hass: HomeAssistant) -> None:
    script_path = str(Path(__file__).parent / "frontend" / "login-panel.js")
    if not hass.data.get(_STATIC_REGISTERED):
        if hasattr(hass.http, "async_register_static_paths"):
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig(SCRIPT_URL, script_path, False)]
            )
        else:
            # Compatibility with older supported Home Assistant versions.
            hass.http.register_static_path(SCRIPT_URL, script_path, False)
        hass.data[_STATIC_REGISTERED] = True

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        module_url=PANEL_MODULE_URL,
        require_admin=True,
    )
