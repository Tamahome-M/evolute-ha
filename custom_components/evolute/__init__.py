"""Evolute integration — direct cloud polling, no proxy addon needed."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DATA_COORDINATOR, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_SCAN_INTERVAL
from .coordinator import EvolUteCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "lock", "button", "device_tracker"]

CARD_URL = f"/{DOMAIN}/evolute-card.js"
CARD_FILE = Path(__file__).parent / "www" / "evolute-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Регистрируем статический путь для JS-карточки."""
    from homeassistant.components.http import StaticPathConfig
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)
    ])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvolUteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_COORDINATOR: coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await _async_register_lovelace_resource(hass)
    return True


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Добавляет JS карточку в Lovelace ресурсы, если ещё не добавлена."""
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
        resources = hass.data.get("lovelace", {}).get("resources")
        if not isinstance(resources, ResourceStorageCollection):
            return
        await resources.async_load()
        if any(r.get("url") == CARD_URL for r in resources.async_items()):
            return
        await resources.async_create_item({"res_type": "module", "url": CARD_URL})
        _LOGGER.info("Evolute card зарегистрирован как Lovelace-ресурс: %s", CARD_URL)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Не удалось авторегистрировать Lovelace-ресурс: %s", exc)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change (new tokens or scan interval)."""
    new_data = dict(entry.data)
    opts = entry.options
    for key in (CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_SCAN_INTERVAL):
        if key in opts:
            new_data[key] = opts[key]
    hass.config_entries.async_update_entry(entry, data=new_data, options={})
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
