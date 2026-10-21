"""DataUpdateCoordinator for Evolute."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    EvolUteAPIError,
    EvolUteAuthError,
    EvolUteClient,
    find_device_id,
    parse_telemetry,
)
from .const import (
    COMMAND_CONFIRM_TIMEOUT,
    COMMAND_POLL_INTERVAL,
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_TOKEN_REFRESH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_TOKEN_REFRESH_INTERVAL,
    DOMAIN,
    TELEMETRY_ACTIONS,
)

_LOGGER = logging.getLogger(__name__)


class EvolUteCoordinator(DataUpdateCoordinator):
    """Manages polling evassist.ru and issuing commands."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._token_refresh_interval: int = entry.options.get(
            CONF_TOKEN_REFRESH_INTERVAL,
            entry.data.get(CONF_TOKEN_REFRESH_INTERVAL, DEFAULT_TOKEN_REFRESH_INTERVAL),
        )
        self._last_token_refresh: float = 0.0
        self._token_refresh_in_progress: bool = False
        # Tbox device id (IMEI) — key of the new client-bff telemetry API.
        # Auto-discovered from API responses and persisted to the entry.
        self.device_id: str | None = entry.data.get(CONF_DEVICE_ID)
        self._command_lock = asyncio.Lock()
        self.last_command: dict[str, Any] = {"status": "idle"}
        self.client = EvolUteClient(
            car_id=entry.data[CONF_CAR_ID],
            access_token=entry.data[CONF_ACCESS_TOKEN],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
            timeout=entry.options.get(
                CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _async_refresh_and_persist(self) -> None:
        """Refresh tokens and save new values into config entry data."""
        access, refresh = await self.hass.async_add_executor_job(
            self.client.refresh_tokens
        )
        self._last_token_refresh = time.monotonic()
        self.hass.config_entries.async_update_entry(
            self._entry,
            data={
                **self._entry.data,
                CONF_ACCESS_TOKEN: access,
                CONF_REFRESH_TOKEN: refresh,
            },
        )
        _LOGGER.debug("New tokens persisted to config entry")

    # ------------------------------------------------------------------
    # DataUpdateCoordinator
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        # ----------------------------------------------------------------
        # Proactive token refresh — runs BEFORE fetching data, but ONLY if
        # another refresh is not already in progress.  Any failure here is
        # logged and silently skipped so it never makes sensors unavailable.
        # ----------------------------------------------------------------
        if (
            not self._token_refresh_in_progress
            and time.monotonic() - self._last_token_refresh >= self._token_refresh_interval
        ):
            self._token_refresh_in_progress = True
            _LOGGER.debug(
                "Proactive token refresh (interval=%ds)", self._token_refresh_interval
            )
            try:
                await self._async_refresh_and_persist()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Proactive token refresh failed: %s", exc)
            finally:
                self._token_refresh_in_progress = False

        # Car metadata is cached. It also supplies the IMEI for older config
        # entries, before the very first telemetry request; no tbox fallback.
        car_info = (self.data or {}).get("car_info", {})
        try:
            if not car_info or not self.device_id:
                raw_car = await self._call_with_auth(self.client.fetch_car_info)
                if not isinstance(raw_car, dict):
                    raise EvolUteAPIError("Evolute API returned invalid car information")
                model = raw_car.get("carModel")
                model = model if isinstance(model, dict) else {}
                car_info = {
                    "vin": raw_car.get("vin"),
                    "carModelName": model.get("name"),
                    "carModelModname": model.get("modname"),
                    "carModelYear": model.get("modelYear"),
                    "carModelColor": model.get("color"),
                }
                if not self.device_id:
                    found = find_device_id(raw_car)
                    if not found:
                        raise UpdateFailed(
                            "Evolute API did not return the vehicle device IMEI"
                        )
                    self.device_id = found
                    self.hass.config_entries.async_update_entry(
                        self._entry,
                        data={**self._entry.data, CONF_DEVICE_ID: found},
                    )

            telemetry = await self._call_with_auth(
                self.client.fetch_telemetry, self.device_id
            )
        except EvolUteAuthError as exc:
            raise ConfigEntryAuthFailed(
                "Evolute session expired. Sign in again in the integration settings."
            ) from exc
        except EvolUteAPIError as exc:
            raise UpdateFailed(f"Evolute API error: {exc}") from exc

        parsed = parse_telemetry(telemetry)
        if parsed is None:
            raise UpdateFailed("Evolute API returned invalid telemetry")
        sensors, position = parsed
        sensors.update({key: value for key, value in car_info.items() if value is not None})
        # Button states and connection metadata can change independently of
        # carStateUpdatedAt. Use every fresh response, including mode changes.
        buttons = telemetry.get("buttons")
        return {
            "sensors": sensors, "position": position, "car_info": car_info,
            "buttons": buttons if isinstance(buttons, list) else [],
        }

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def sensors(self) -> dict:
        return (self.data or {}).get("sensors", {})

    @property
    def position(self) -> dict:
        return (self.data or {}).get("position", {})

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def action_available(self, action: str) -> bool:
        """Respect the command capabilities advertised for this car."""
        command = TELEMETRY_ACTIONS[action]
        buttons = (self.data or {}).get("buttons")
        if self.device_id and isinstance(buttons, list):
            return any(
                isinstance(button, dict) and button.get("enabled") is True
                and command in (button.get("activateCommand"), button.get("deactivateCommand"))
                for button in buttons
            )
        return False

    def _command_state(self, status: str, **attributes: Any) -> None:
        self.last_command = {
            **self.last_command, **attributes, "status": status,
            "updated_at": dt_util.utcnow().isoformat(),
        }
        self.async_update_listeners()

    async def _call_with_auth(self, method: Any, *args: Any) -> Any:
        """Retry only a rejected session; never retry an ambiguous command POST."""
        try:
            return await self.hass.async_add_executor_job(method, *args)
        except EvolUteAuthError:
            await self._async_refresh_and_persist()
            return await self.hass.async_add_executor_job(method, *args)

    def _check_command(self, action: str) -> None:
        if not self.action_available(action):
            raise HomeAssistantError("Эта команда недоступна для автомобиля")
        if self.sensors.get("isOnline") is False:
            raise HomeAssistantError("Автомобиль не в сети")
        if self.sensors.get("isParkedOn") is False:
            raise HomeAssistantError("Автомобиль должен быть в режиме паркинга")
        if self.sensors.get("isTrunkOpen") is True and not action.startswith("trunk_"):
            raise HomeAssistantError("Сначала закройте багажник")
        if (
            self.sensors.get("isCentralLockingOn") is False
            and action not in {"lock_close", "lock_open", "blink"}
        ):
            raise HomeAssistantError("Сначала закройте центральный замок")

    async def _wait_command(self, command_id: str) -> None:
        async with asyncio.timeout(COMMAND_CONFIRM_TIMEOUT):
            while True:
                result = await self._call_with_auth(
                    self.client.fetch_command_status, self.device_id
                )
                # Another browser or integration may have issued a command.
                # Its success must never be attributed to our own command.
                if result and result["commandId"] == command_id:
                    status = result["status"]
                    if status != "pending" or self.last_command["status"] != "delivered":
                        self._command_state(status)
                    if status == "success":
                        return
                    if status == "error":
                        raise HomeAssistantError("Автомобиль не подтвердил выполнение команды")
                await asyncio.sleep(COMMAND_POLL_INTERVAL)

    async def _telemetry_action(self, action: str) -> None:
        await self.async_refresh()
        if not self.last_update_success:
            raise HomeAssistantError("Не удалось обновить состояние автомобиля")
        self._check_command(action)
        command = TELEMETRY_ACTIONS[action]
        self.last_command = {"command": command, "source": "telemetry"}
        self._command_state("sending")
        try:
            command_id = await self._call_with_auth(
                self.client.send_telemetry_command, self.device_id, command
            )
        except (EvolUteAPIError, EvolUteAuthError) as exc:
            self._command_state("unconfirmed")
            await self.async_request_refresh()
            raise HomeAssistantError(
                "Не удалось подтвердить отправку команды. Проверьте состояние автомобиля."
            ) from exc
        self._command_state("pending", command_id=command_id)
        try:
            await self._wait_command(command_id)
        except TimeoutError as exc:
            self._command_state("timeout")
            raise HomeAssistantError("Истекло время ожидания подтверждения команды") from exc
        except (EvolUteAPIError, EvolUteAuthError) as exc:
            self._command_state("unconfirmed")
            raise HomeAssistantError(
                "Не удалось получить статус команды. Проверьте состояние автомобиля."
            ) from exc
        finally:
            await self.async_request_refresh()

    async def async_send_action(self, action: str) -> None:
        """Send explicit commands and correlate their execution receipts."""
        if action not in TELEMETRY_ACTIONS:
            raise ValueError(f"Unknown action: {action}")
        if self._command_lock.locked():
            raise HomeAssistantError("Уже выполняется команда автомобиля")
        async with self._command_lock:
            await self._telemetry_action(action)
