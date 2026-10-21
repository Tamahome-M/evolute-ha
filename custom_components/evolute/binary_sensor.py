"""Binary sensor platform for Evolute."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity

_TRUTHY = {True, "true", "True", "1"}


def _truthy(v: Any) -> bool: return v in _TRUTHY
def _eq1(v: Any) -> bool:
    try: return int(v) == 1
    except (TypeError, ValueError): return False
def _ne1(v: Any) -> bool:
    try: return int(v) != 1
    except (TypeError, ValueError): return False


@dataclass(frozen=True, kw_only=True)
class _Desc(BinarySensorEntityDescription):
    data_key: str
    is_on_fn: Callable[[Any], bool] = field(default=_eq1)


BINARY_SENSORS: tuple[_Desc, ...] = (
    _Desc(key="ignition", data_key="ignitionStatus", name="Зажигание",
          device_class=BinarySensorDeviceClass.POWER, icon="mdi:engine"),
    _Desc(key="locked", data_key="centralLockingStatus", name="Замок (закрыт)",
          device_class=BinarySensorDeviceClass.LOCK, icon="mdi:lock", is_on_fn=_ne1),
    _Desc(key="door_fl", data_key="doorFLStatus", name="Дверь перед. лев.",
          device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"),
    _Desc(key="door_fr", data_key="doorFRStatus", name="Дверь перед. прав.",
          device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"),
    _Desc(key="door_rl", data_key="doorRLStatus", name="Дверь зад. лев.",
          device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"),
    _Desc(key="door_rr", data_key="doorRRStatus", name="Дверь зад. прав.",
          device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"),
    _Desc(key="trunk", data_key="trunkStatus", name="Багажник",
          device_class=BinarySensorDeviceClass.GARAGE_DOOR, icon="mdi:car-back"),
    _Desc(key="headlights", data_key="headLightsStatus", name="Фары",
          device_class=BinarySensorDeviceClass.LIGHT, icon="mdi:car-light-high"),
    _Desc(key="parked", data_key="isParked", name="Припаркован",
          device_class=BinarySensorDeviceClass.OCCUPANCY,
          icon="mdi:car-brake-parking", is_on_fn=_truthy),
    _Desc(key="climate", data_key="climateStatus", name="Климат включён",
          device_class=BinarySensorDeviceClass.HEAT, icon="mdi:air-conditioner"),
    _Desc(key="heating", data_key="heatingRunning", name="Обогрев включён",
          icon="mdi:heat-wave", is_on_fn=_truthy),
    _Desc(key="cooling", data_key="coolingRunning", name="Охлаждение включено",
          icon="mdi:snowflake", is_on_fn=_truthy),
    _Desc(key="climate_defrost", data_key="climateFWindowStatus",
          name="Обогрев лобового стекла", icon="mdi:car-windshield"),
    _Desc(key="charging_gun", data_key="isChargingGunInserted",
          name="Зарядный пистолет вставлен",
          device_class=BinarySensorDeviceClass.PLUG,
          icon="mdi:ev-plug-type2", is_on_fn=_truthy),
    _Desc(key="online", data_key="isOnline", name="Онлайн",
          device_class=BinarySensorDeviceClass.CONNECTIVITY,
          icon="mdi:car-connected", is_on_fn=_truthy),
    _Desc(key="firmware_mismatch", data_key="firmwareMismatch",
          name="Несоответствие прошивки", device_class=BinarySensorDeviceClass.PROBLEM,
          entity_category=EntityCategory.DIAGNOSTIC, is_on_fn=_truthy),
    _Desc(key="settings_mismatch", data_key="settingsMismatch",
          name="Несоответствие настроек", device_class=BinarySensorDeviceClass.PROBLEM,
          entity_category=EntityCategory.DIAGNOSTIC, is_on_fn=_truthy),
    _Desc(key="trip_preparation", data_key="tripPreparationRunning",
          name="Подготовка к поездке", icon="mdi:car-clock", is_on_fn=_truthy),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coord: EvolUteCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(EvolUteBinarySensor(coord, d) for d in BINARY_SENSORS)


class EvolUteBinarySensor(EvolUteEntity, BinarySensorEntity):
    entity_description: _Desc

    def __init__(self, coordinator: EvolUteCoordinator, description: _Desc) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name
        # Cache the last known good value to suppress single-poll glitches
        self._last_known_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        val = self.coordinator.sensors.get(self.entity_description.data_key)
        if val is None:
            # Key absent in current payload — return last known value instead
            # of flipping to None (unavailable).  HA will still mark the
            # entity unavailable if the coordinator itself fails.
            return self._last_known_on
        result = self.entity_description.is_on_fn(val)
        self._last_known_on = result
        return result

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        prefix = {"firmware_mismatch": "firmware", "settings_mismatch": "settings"}.get(
            self.entity_description.key
        )
        if prefix:
            return {
                "actual": self.coordinator.sensors.get(f"{prefix}Actual"),
                "expected": self.coordinator.sensors.get(f"{prefix}Expected"),
            }
        return None
