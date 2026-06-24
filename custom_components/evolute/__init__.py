"""Evolute integration — direct cloud polling, no proxy addon needed.

The dashboard card ships with the integration: it is served from lovelace/ and
registered as a Lovelace resource on setup, then removed when the last config
entry is deleted. Use it on a dashboard as `type: custom:evolute-card`.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, EVENT_HOMEASSISTANT_STARTED, HomeAssistant

from .const import DOMAIN, DATA_COORDINATOR
from .coordinator import EvolUteCoordinator
from .frontend import async_register_frontend, async_unregister_frontend

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "lock", "button", "number", "device_tracker"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the bundled Lovelace card once HA is running."""

    async def _register(_event=None) -> None:
        try:
            await async_register_frontend(hass)
        except Exception:  # noqa: BLE001 — never block setup on a card issue
            _LOGGER.exception("Evolute: failed to register dashboard card")

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

    # Make sure the card is registered even if the entry is added after startup.
    try:
        await async_register_frontend(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Evolute: failed to register dashboard card")

    # NOTE: update_listener intentionally NOT registered here — see history:
    # reloading on every programmatic token-persist write made all entities flap
    # to "unavailable" for ~1s each refresh cycle. Token rotation is in-memory.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """When the last Evolute entry is removed, remove the card resource too."""
    if hass.config_entries.async_entries(DOMAIN):
        return  # other Evolute cars still configured
    try:
        await async_unregister_frontend(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Evolute: failed to remove dashboard card resource")
