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
        # Stable English key, stored in the entity registry and exposed to the
        # frontend via hass.entities[...].translation_key. The Evolute dashboard
        # card uses it to locate entities regardless of the (localized) name or
        # the auto-generated entity_id. Does not affect the displayed name,
        # which subclasses set via _attr_name.
        self._attr_translation_key = unique_suffix

        s = coordinator.sensors
        vin = s.get("vin") or coordinator._entry.data.get("car_id", "unknown")
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
