"""Button platform for Evolute — remote commands."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity


@dataclass(frozen=True, kw_only=True)
class _Desc(ButtonEntityDescription):
    # Coroutine factory to run when the button is pressed.
    press_fn: Callable[[EvolUteCoordinator], Coroutine[Any, Any, None]]


def _action(name: str) -> Callable[[EvolUteCoordinator], Coroutine[Any, Any, None]]:
    async def _run(coord: EvolUteCoordinator) -> None:
        await coord.async_send_action(name)

    return _run


BUTTONS: tuple[_Desc, ...] = (
    _Desc(key="heating_on",  name="Включить обогрев",     icon="mdi:heat-wave",
          press_fn=_action("heating_on")),
    _Desc(key="heating_off", name="Выключить обогрев",    icon="mdi:heat-wave",
          press_fn=_action("heating_off")),
    _Desc(key="cooling_on",  name="Включить охлаждение",  icon="mdi:snowflake",
          press_fn=_action("cooling_on")),
    _Desc(key="cooling_off", name="Выключить охлаждение", icon="mdi:snowflake-off",
          press_fn=_action("cooling_off")),
    _Desc(key="trunk_open",  name="Открыть багажник",     icon="mdi:car-back",
          press_fn=_action("trunk_open")),
    _Desc(key="trunk_close", name="Закрыть багажник",     icon="mdi:car-back",
          press_fn=_action("trunk_close")),
    _Desc(key="blink",       name="Сигнал и фары",       icon="mdi:car-light-high",
          press_fn=_action("blink")),
    # Preparation (предпрогрев) — uses temp/time/heating from the number entities.
    _Desc(key="prepare_on",  name="Предпрогрев: вкл",     icon="mdi:car-key",
          press_fn=lambda c: c.async_prepare()),
    _Desc(key="prepare_off", name="Предпрогрев: выкл",    icon="mdi:car-key",
          press_fn=lambda c: c.async_cancel_prepare()),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coord: EvolUteCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(EvolUteButton(coord, d) for d in BUTTONS)


class EvolUteButton(EvolUteEntity, ButtonEntity):
    entity_description: _Desc

    def __init__(self, coordinator: EvolUteCoordinator, description: _Desc) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
