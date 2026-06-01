"""Evolute integration — direct cloud polling, no proxy addon needed."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, EVENT_HOMEASSISTANT_STARTED, HomeAssistant

from .const import DOMAIN, DATA_COORDINATOR, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_SCAN_INTERVAL
from .coordinator import EvolUteCoordinator
from .frontend import async_register_frontend

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "lock", "button", "device_tracker"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Регистрируем JS-карточку при старте Home Assistant."""

    async def _register(_event=None) -> None:
        await async_register_frontend(hass)

    if hass.state == CoreState.running:
        await _register()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvolUteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Перезагрузка при изменении настроек."""
    new_data = dict(entry.data)
    for key in (CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_SCAN_INTERVAL):
        if key in entry.options:
            new_data[key] = entry.options[key]
    hass.config_entries.async_update_entry(entry, data=new_data, options={})
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
