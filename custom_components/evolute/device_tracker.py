"""Device tracker platform for Evolute (GPS location)."""
from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coord: EvolUteCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([EvolUteTracker(coord)])


class EvolUteTracker(EvolUteEntity, TrackerEntity):
    _attr_name = "Местоположение"
    _attr_icon = "mdi:car-connected"

    def __init__(self, coordinator: EvolUteCoordinator) -> None:
        super().__init__(coordinator, "tracker")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        val = self.coordinator.position.get("lat")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def longitude(self) -> float | None:
        val = self.coordinator.position.get("lon")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def location_accuracy(self) -> int:
        hdop = self.coordinator.position.get("hdop")
        try:
            return max(1, int(float(hdop) * 5))
        except (TypeError, ValueError):
            return 0

    @property
    def battery_level(self) -> int | None:
        val = self.coordinator.sensors.get("batteryPercentage")
        try:
            return int(float(val)) if val is not None else None
        except (TypeError, ValueError):
            return None
