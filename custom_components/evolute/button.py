"""Button platform for Evolute — remote commands."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity


@dataclass(frozen=True, kw_only=True)
class _Desc(ButtonEntityDescription):
    action: str


BUTTONS: tuple[_Desc, ...] = (
    _Desc(key="heating_on",  action="heating_on",  name="Включить обогрев",   icon="mdi:heat-wave"),
    _Desc(key="heating_off", action="heating_off", name="Выключить обогрев",  icon="mdi:heat-wave"),
    _Desc(key="cooling_on",  action="cooling_on",  name="Включить охлаждение",icon="mdi:snowflake"),
    _Desc(key="cooling_off", action="cooling_off", name="Выключить охлаждение",icon="mdi:snowflake-off"),
    _Desc(key="prepare_on",  action="prepare_on",  name="Предпрогрев: вкл",   icon="mdi:car-key"),
    _Desc(key="prepare_off", action="prepare_off", name="Предпрогрев: выкл",  icon="mdi:car-key"),
    _Desc(key="trunk_open",  action="trunk_open",  name="Открыть багажник",   icon="mdi:car-back"),
    _Desc(key="trunk_close", action="trunk_close", name="Закрыть багажник",   icon="mdi:car-back"),
    _Desc(key="blink",       action="blink",       name="Мигнуть фарами",     icon="mdi:car-light-high"),
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
        await self.coordinator.async_send_action(self.entity_description.action)
