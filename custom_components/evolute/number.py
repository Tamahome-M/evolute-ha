"""Number platform for Evolute — preparation (предпрогрев) parameters.

These are configuration helpers held in coordinator memory. They do not poll
the car; pressing the «Предпрогрев: вкл» button reads their current values and
sends a single PREPARE command with the chosen temperature, duration and
heating levels.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    PREPARE_TEMP_MIN,
    PREPARE_TEMP_MAX,
    PREPARE_DURATION_MIN,
    PREPARE_DURATION_MAX,
    PREPARE_SEAT_MIN,
    PREPARE_SEAT_MAX,
    PREPARE_WHEEL_MAX,
)
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity


@dataclass(frozen=True, kw_only=True)
class _Desc(NumberEntityDescription):
    param: str   # key inside coordinator.prepare_params


NUMBERS: tuple[_Desc, ...] = (
    _Desc(key="prepare_temp", param="temp", name="Предпрогрев: температура",
          native_min_value=PREPARE_TEMP_MIN, native_max_value=PREPARE_TEMP_MAX,
          native_step=1, native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          icon="mdi:thermometer", mode=NumberMode.SLIDER),
    _Desc(key="prepare_duration", param="time", name="Предпрогрев: длительность",
          native_min_value=PREPARE_DURATION_MIN, native_max_value=PREPARE_DURATION_MAX,
          native_step=1, native_unit_of_measurement=UnitOfTime.MINUTES,
          icon="mdi:timer-outline", mode=NumberMode.SLIDER),
    _Desc(key="prepare_seat_fl", param="fl", name="Предпрогрев: сиденье перед. лев.",
          native_min_value=PREPARE_SEAT_MIN, native_max_value=PREPARE_SEAT_MAX,
          native_step=1, icon="mdi:car-seat-heater", mode=NumberMode.SLIDER),
    _Desc(key="prepare_seat_fr", param="fr", name="Предпрогрев: сиденье перед. прав.",
          native_min_value=PREPARE_SEAT_MIN, native_max_value=PREPARE_SEAT_MAX,
          native_step=1, icon="mdi:car-seat-heater", mode=NumberMode.SLIDER),
    _Desc(key="prepare_seat_rl", param="rl", name="Предпрогрев: сиденье зад. лев.",
          native_min_value=PREPARE_SEAT_MIN, native_max_value=PREPARE_SEAT_MAX,
          native_step=1, icon="mdi:car-seat-heater", mode=NumberMode.SLIDER),
    _Desc(key="prepare_seat_rr", param="rr", name="Предпрогрев: сиденье зад. прав.",
          native_min_value=PREPARE_SEAT_MIN, native_max_value=PREPARE_SEAT_MAX,
          native_step=1, icon="mdi:car-seat-heater", mode=NumberMode.SLIDER),
    _Desc(key="prepare_wheel", param="wheel", name="Предпрогрев: подогрев руля",
          native_min_value=0, native_max_value=PREPARE_WHEEL_MAX,
          native_step=1, icon="mdi:steering", mode=NumberMode.BOX),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coord: EvolUteCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(EvolUtePrepareNumber(coord, d) for d in NUMBERS)


class EvolUtePrepareNumber(EvolUteEntity, NumberEntity):
    entity_description: _Desc
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EvolUteCoordinator, description: _Desc) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name

    @property
    def native_value(self) -> float | None:
        return self.coordinator.prepare_params.get(self.entity_description.param)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.prepare_params[self.entity_description.param] = int(value)
        self.async_write_ha_state()
