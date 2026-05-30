"""Base entity for Evolute."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EvolUteCoordinator


class EvolUteEntity(CoordinatorEntity[EvolUteCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EvolUteCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        s = coordinator.sensors
        vin = s.get("vin") or coordinator.config_entry.data.get("car_id", "unknown")
        model = s.get("carModelName") or "Evolute"
        year = s.get("carModelYear") or ""
        modname = s.get("carModelModname") or ""
        color = s.get("carModelColor") or ""

        self._attr_unique_id = f"evolute_{vin}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            name=f"{model} {year}".strip(),
            manufacturer="Evolute",
            model=" ".join(filter(None, [modname, color])) or model,
            serial_number=vin,
        )
