"""Evolute integration — direct cloud polling, no proxy addon needed.

The dashboard card is distributed separately via HACS
(https://github.com/Tamahome-M/evolute-card) and is intentionally NOT bundled or
auto-registered here, to avoid a custom-element name clash with the HACS card.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DATA_COORDINATOR
from .coordinator import EvolUteCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "lock", "button", "number", "device_tracker"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvolUteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # NOTE: update_listener intentionally NOT registered here.
    #
    # Previously we used entry.add_update_listener(...) which called
    # async_reload() on every entry change — including the programmatic
    # token-persist writes the coordinator does every ~10 minutes. That caused
    # all entities to flap to "unavailable" for ~1 second on each token refresh.
    # Token rotation is handled in-memory; the persisted entry is updated for
    # restart-safety but must NOT trigger a reload.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
