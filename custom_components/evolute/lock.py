"""Lock platform for Evolute."""
from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EvolUteCoordinator
from .entity_base import EvolUteEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coord: EvolUteCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([EvolUteLock(coord)])


class EvolUteLock(EvolUteEntity, LockEntity):
    _attr_name = "Центральный замок"
    _attr_icon = "mdi:car-door-lock"

    def __init__(self, coordinator: EvolUteCoordinator) -> None:
        super().__init__(coordinator, "central_lock")

    @property
    def is_locked(self) -> bool | None:
        val = self.coordinator.sensors.get("centralLockingStatus")
        if val is None:
            return None
        try:
            return int(val) == 1   # 1 = закрыт в API Evolute
        except (TypeError, ValueError):
            return None

    async def async_lock(self, **kwargs) -> None:
        await self.coordinator.async_send_action("lock_close")

    async def async_unlock(self, **kwargs) -> None:
        await self.coordinator.async_send_action("lock_open")

    @property
    def is_locking(self) -> bool:
        return self._command_in_progress("centralLockingOn")

    @property
    def is_unlocking(self) -> bool:
        return self._command_in_progress("centralLockingOff")

    def _command_in_progress(self, command: str) -> bool:
        result = self.coordinator.last_command
        return result.get("command") == command and result["status"] in {
            "sending", "pending", "delivered",
        }

    @property
    def available(self) -> bool:
        return super().available and all(
            self.coordinator.action_available(action)
            for action in ("lock_close", "lock_open")
        )
