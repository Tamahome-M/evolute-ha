"""Register the EVAssist field used by the native Home Assistant setup form."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import Selector

from .const import DOMAIN

SCRIPT_URL = "/evolute_static/login-form.js"
MODULE_URL = f"{SCRIPT_URL}?v=1"
_SETUP_TASK = f"{DOMAIN}_login_ui_setup"
_STATIC_REGISTERED = f"{DOMAIN}_login_ui_static"
_LOGGER = logging.getLogger(__name__)


class EvoluteLoginSelector(Selector):
    """Render our web component using HA's normal selector serialization."""

    selector_type = "evolute_login"
    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Required("flow_id"): str,
            vol.Required("mode"): vol.In(("request", "actions", "status")),
        }
    )

    def __call__(self, value: Any) -> str:
        """Only the recovery action submits a value; credentials use HA fields."""
        if value != "request_again":
            raise vol.Invalid("Unknown login action")
        return value


async def async_ensure_login_ui(hass: HomeAssistant) -> bool:
    """Register once, including during concurrent setup flows."""
    if frontend.DATA_EXTRA_MODULE_URL not in hass.data:
        # The module manager is created before frontend setup finishes. Checking
        # it also permits early registration while startup is still in progress.
        return False
    if (task := hass.data.get(_SETUP_TASK)) is None:
        task = hass.data[_SETUP_TASK] = hass.async_create_task(
            _async_register_ui(hass), "Register Evolute login form"
        )
    try:
        await asyncio.shield(task)
    except Exception:
        if task.done():
            hass.data.pop(_SETUP_TASK, None)
        _LOGGER.exception("Unable to register the embedded Evolute login form")
        return False
    return True


async def _async_register_ui(hass: HomeAssistant) -> None:
    path = str(Path(__file__).parent / "frontend" / "login-form.js")
    if not hass.data.get(_STATIC_REGISTERED):
        if hasattr(hass.http, "async_register_static_paths"):
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig(SCRIPT_URL, path, False)]
            )
        else:
            hass.http.register_static_path(SCRIPT_URL, path, False)
        hass.data[_STATIC_REGISTERED] = True
    frontend.add_extra_js_url(hass, MODULE_URL)
