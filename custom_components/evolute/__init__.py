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

    # NOTE: update_listener intentionally NOT registered here.
    #
    # Previously we used entry.add_update_listener(_async_update_listener) which
    # called async_reload() on every entry change — including the programmatic
    # token-persist writes that the coordinator does every ~10 minutes.  That
    # caused all entities to flap to "unavailable" for ~1 second on each token
    # refresh cycle.
    #
    # Options-flow changes (scan_interval etc.) are now applied by
    # async_migrate_entry / a manual reload from the UI if ever needed.
    # Token rotation is handled entirely in-memory by the coordinator; the
    # persisted entry is updated for restart-safety but must NOT trigger a
    # reload.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
