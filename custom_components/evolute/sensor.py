"""Sensor platform for Evolute."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity


@dataclass(frozen=True, kw_only=True)
class _Desc(SensorEntityDescription):
    data_key: str
    source: str = "sensors"   # "sensors" | "position"


SENSORS: tuple[_Desc, ...] = (
    _Desc(key="battery_pct", data_key="batteryPercentage", name="Заряд батареи",
          native_unit_of_measurement="%", device_class=SensorDeviceClass.BATTERY,
          state_class=SensorStateClass.MEASUREMENT, icon="mdi:battery-high"),
    _Desc(key="remains_mileage", data_key="remainsMileage", name="Запас хода (батарея)",
          native_unit_of_measurement=UnitOfLength.KILOMETERS,
          device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:map-marker-distance"),
    _Desc(key="remains_mileage_fuel", data_key="remainsMileageFuel", name="Запас хода (топливо)",
          native_unit_of_measurement=UnitOfLength.KILOMETERS,
          device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:gas-station"),
    _Desc(key="fuel_pct", data_key="fuelPercentage", name="Уровень топлива",
          native_unit_of_measurement="%", state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:fuel"),
    _Desc(key="odometer", data_key="odometer", name="Одометр",
          native_unit_of_measurement=UnitOfLength.KILOMETERS,
          device_class=SensorDeviceClass.DISTANCE,
          state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:counter"),
    _Desc(key="outside_temp", data_key="outsideTemp", name="Температура снаружи",
          native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    _Desc(key="inboard_temp", data_key="inBoardTemp", name="Температура в салоне",
          native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    _Desc(key="battery_temp", data_key="batteryTemp", name="Температура батареи",
          native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:thermometer"),
    _Desc(key="coolant_temp", data_key="coolantTemp", name="Температура ОЖ",
          native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:coolant-temperature"),
    _Desc(key="voltage_12v", data_key="12VBatteryVoltage", name="Напряжение 12В АКБ",
          native_unit_of_measurement=UnitOfElectricPotential.VOLT,
          device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:battery"),
    _Desc(key="tachometer", data_key="tachometer", name="Обороты двигателя",
          native_unit_of_measurement="RPM", state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:rotate-right"),
    _Desc(key="climate_fan", data_key="climateFanSpeed", name="Скорость вентилятора",
          native_unit_of_measurement="уровень", state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:fan"),
    _Desc(key="climate_target_temp", data_key="climateTargetTemp", name="Целевая т° климата",
          native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    _Desc(key="climate_current_temp", data_key="climateCurentTemp", name="Текущая т° климата",
          native_unit_of_measurement=UnitOfTemperature.CELSIUS,
          device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    _Desc(key="diagnostics", data_key="diagnostics", name="Диагностический код",
          icon="mdi:alert-circle-outline"),
    _Desc(key="last_online", data_key="lastOnlineTime", name="Последний онлайн",
          device_class=SensorDeviceClass.TIMESTAMP, icon="mdi:clock-outline"),
    _Desc(key="sensor_time", data_key="sensorDataTime", name="Время данных",
          device_class=SensorDeviceClass.TIMESTAMP, icon="mdi:timeline-clock"),
    _Desc(key="vin", data_key="vin", name="VIN", icon="mdi:card-account-details",
          entity_registry_enabled_default=False),
    _Desc(key="car_model", data_key="carModelName", name="Модель", icon="mdi:car-info",
          entity_registry_enabled_default=False),
    _Desc(key="car_year", data_key="carModelYear", name="Год выпуска", icon="mdi:calendar",
          entity_registry_enabled_default=False),
    _Desc(key="car_color", data_key="carModelColor", name="Цвет", icon="mdi:palette",
          entity_registry_enabled_default=False),
    _Desc(key="prepare_end", data_key="preparation_scriptEndTime",
          name="Предпрогрев: окончание", native_unit_of_measurement="мин",
          icon="mdi:timer-outline"),
    # Position
    _Desc(key="speed", data_key="speed", name="Скорость", source="position",
          native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
          device_class=SensorDeviceClass.SPEED, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:speedometer"),
    _Desc(key="altitude", data_key="height", name="Высота", source="position",
          native_unit_of_measurement=UnitOfLength.METERS,
          state_class=SensorStateClass.MEASUREMENT, icon="mdi:image-filter-hdr"),
    _Desc(key="course", data_key="course", name="Курс GPS", source="position",
          native_unit_of_measurement=DEGREE, state_class=SensorStateClass.MEASUREMENT,
          icon="mdi:compass"),
    _Desc(key="gps_sats", data_key="sats", name="Спутники GPS", source="position",
          state_class=SensorStateClass.MEASUREMENT, icon="mdi:satellite-variant"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coord: EvolUteCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        EvolUteTimestampSensor(coord, d) if d.key in _TIMESTAMP_KEYS else EvolUteSensor(coord, d)
        for d in SENSORS
    )


class EvolUteSensor(EvolUteEntity, SensorEntity):
    entity_description: _Desc

    def __init__(self, coordinator: EvolUteCoordinator, description: _Desc) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        src = self.coordinator.sensors if self.entity_description.source == "sensors" \
            else self.coordinator.position
        return src.get(self.entity_description.data_key)


_TIMESTAMP_KEYS = {"last_online", "sensor_time"}


class EvolUteTimestampSensor(EvolUteSensor):
    """Sensor that converts a unix timestamp (int/float) to aware datetime."""

    @property
    def native_value(self) -> datetime | None:
        raw = self.coordinator.sensors.get(self.entity_description.data_key)
        if raw is None:
            return None
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
