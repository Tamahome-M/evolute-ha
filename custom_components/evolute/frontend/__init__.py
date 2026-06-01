"""JavaScript frontend card registration for Evolute."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# JS-файл находится в frontend/www/evolute-card.js
# Сервируем папку frontend/www/ по URL /evolute/
# → браузер получает карточку по /evolute/evolute-card.js
_WWW_DIR = Path(__file__).parent / "www"
CARD_URL = "/evolute/evolute-card.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Зарегистрировать статический путь и Lovelace-ресурс."""

    # 1. Статический HTTP-путь
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig("/evolute", str(_WWW_DIR), False)
        ])
        _LOGGER.debug("Evolute: static path /evolute → %s", _WWW_DIR)
    except RuntimeError:
        _LOGGER.debug("Evolute: static path already registered")

    # 2. Lovelace-ресурс (только в storage mode — дефолт для большинства установок)
    lovelace = hass.data.get("lovelace")
    if not lovelace or getattr(lovelace, "mode", None) != "storage":
        _LOGGER.debug(
            "Evolute: Lovelace не в storage mode — добавьте ресурс вручную: %s", CARD_URL
        )
        return

    resources = lovelace.resources
    await resources.async_load()  # идемпотентно: повторный вызов — no-op

    for item in resources.async_items():
        if item.get("url") == CARD_URL:
            _LOGGER.debug("Evolute: Lovelace-ресурс уже зарегистрирован")
            return

    await resources.async_create_item({"res_type": "module", "url": CARD_URL})
    _LOGGER.info("Evolute: Lovelace-ресурс зарегистрирован: %s", CARD_URL)
