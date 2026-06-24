"""Serve and register the bundled Lovelace card.

The card ships inside the integration (lovelace/evolute-card.js) and is
registered as a Lovelace resource automatically, so installing the integration
is enough to use `type: custom:evolute-card`. The resource URL carries the
integration version (?v=...) so browsers reload it after an upgrade, and it is
removed again when the last config entry is deleted.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_WWW_DIR = Path(__file__).parent / "lovelace"
_URL_PATH = "/evolute_card"                      # static mount point
_CARD_PATH = f"{_URL_PATH}/evolute-card.js"      # resource URL (without ?v=)
_LEGACY_PATHS = ("/evolute/evolute-card.js",)    # cleaned up on upgrade

_STATIC_REGISTERED = False


def _base(url: str) -> str:
    return (url or "").split("?")[0]


async def _resources(hass: HomeAssistant):
    """Return the Lovelace resource collection, or None if not editable."""
    lovelace = hass.data.get("lovelace")
    if not lovelace or getattr(lovelace, "mode", None) != "storage":
        return None
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        return None
    await resources.async_load()
    return resources


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Mount the static path and register the Lovelace resource."""
    global _STATIC_REGISTERED

    if not _STATIC_REGISTERED:
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(_URL_PATH, str(_WWW_DIR), True)]
            )
            _STATIC_REGISTERED = True
        except RuntimeError:
            _STATIC_REGISTERED = True  # already registered

    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version or "0"
    desired = f"{_CARD_PATH}?v={version}"

    resources = await _resources(hass)
    if resources is None:
        _LOGGER.info(
            "Evolute: dashboards are not in storage mode — add the resource "
            "manually as a JavaScript module: %s", desired,
        )
        return

    items = list(resources.async_items())

    # Drop any legacy resources from older versions.
    for item in items:
        if _base(item.get("url")) in _LEGACY_PATHS:
            await resources.async_delete_item(item["id"])

    mine = [i for i in items if _base(i.get("url")) == _CARD_PATH]
    if mine:
        first = mine[0]
        if first.get("url") != desired:
            await resources.async_update_item(first["id"], {"url": desired})
            _LOGGER.info("Evolute: card resource updated to %s", desired)
        for dup in mine[1:]:               # remove accidental duplicates
            await resources.async_delete_item(dup["id"])
    else:
        await resources.async_create_item({"res_type": "module", "url": desired})
        _LOGGER.info("Evolute: card resource registered: %s", desired)


async def async_unregister_frontend(hass: HomeAssistant) -> None:
    """Remove the Lovelace resource (called when the last entry is deleted)."""
    resources = await _resources(hass)
    if resources is None:
        return
    for item in list(resources.async_items()):
        if _base(item.get("url")) in (_CARD_PATH, *_LEGACY_PATHS):
            await resources.async_delete_item(item["id"])
            _LOGGER.info("Evolute: card resource removed: %s", item.get("url"))
