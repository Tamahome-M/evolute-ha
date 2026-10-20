"""Evolute integration — direct cloud polling, no proxy addon needed.

The dashboard card is distributed separately via HACS
(https://github.com/Tamahome-M/evolute-card) and is intentionally NOT bundled or
auto-registered here, to avoid a custom-element name clash with the HACS card.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .login_ui import async_ensure_login_ui

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "lock", "button", "number", "device_tracker"]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Load the embedded field for Home Assistant's native setup dialog."""
    await async_ensure_login_ui(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvolUteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Only options changes need a reload. Saving rotated tokens must not
    # interrupt polling or briefly make all entities unavailable.
    options = dict(entry.options)

    async def _async_options_updated(hass: HomeAssistant, updated_entry: ConfigEntry):
        if dict(updated_entry.options) != options:
            await hass.config_entries.async_reload(updated_entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data[DATA_COORDINATOR].client.close)
    return unload_ok
