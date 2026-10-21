"""DataUpdateCoordinator for Evolute."""
from __future__ import annotations

import asyncio
import functools
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
    CANCEL_COMMAND,
    COMMAND_CONFIRM_TIMEOUT,
    COMMAND_POLL_INTERVAL,
    COMMAND_TIMEOUT,
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
    INTELLIGENT_ACTIONS,
    PREPARE_COMMAND,
    PREPARE_DEFAULTS,
    PREPARE_TIMEOUT,
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
        # In-memory parameters for the PREPARE (предпрогрев) command. Edited via
        # the number entities, consumed when the prepare button is pressed.
        self.prepare_params: dict[str, int] = dict(PREPARE_DEFAULTS)
        # Tbox device id (IMEI) — key of the new client-bff telemetry API.
        # Auto-discovered from API responses and persisted to the entry.
        self.device_id: str | None = entry.data.get(CONF_DEVICE_ID)
        self.api_source: str = "tbox"
        self._raw_car: dict | None = None
        self._device_id_warned = False
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

        # ----------------------------------------------------------------
        # New API (client-bff-service/telemetry) — primary source when the
        # tbox device id (IMEI) is known. Any failure or unexpected payload
        # falls back to the old tbox API below.
        # ----------------------------------------------------------------
        used_telemetry = False
        sensors: dict = {}
        position: dict = {}
        tbox_raw: dict | None = None

        if self.device_id:
            telemetry_raw: Any = None
            try:
                telemetry_raw = await self.hass.async_add_executor_job(
                    self.client.fetch_telemetry, self.device_id
                )
            except EvolUteAuthError:
                _LOGGER.info("Access token expired — refreshing")
                try:
                    await self._async_refresh_and_persist()
                    telemetry_raw = await self.hass.async_add_executor_job(
                        self.client.fetch_telemetry, self.device_id
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.debug("Telemetry retry after refresh failed: %s", exc)
            except EvolUteAPIError as exc:
                _LOGGER.debug("Telemetry API request failed: %s", exc)

            parsed = parse_telemetry(telemetry_raw)
            if parsed is not None:
                sensors, position = parsed
                used_telemetry = True
            elif telemetry_raw is not None:
                _LOGGER.debug(
                    "Telemetry API returned an unexpected payload — falling back"
                )

        # ----------------------------------------------------------------
        # Old API (tbox) — fallback, and the source for device id discovery
        # ----------------------------------------------------------------
        if not used_telemetry:
            # Fetch tbox data — retry once with fresh tokens on 401
            try:
                tbox_raw = await self.hass.async_add_executor_job(
                    self.client.fetch_tbox_info
                )
            except EvolUteAuthError:
                _LOGGER.info("Access token expired — refreshing")
                try:
                    await self._async_refresh_and_persist()
                    tbox_raw = await self.hass.async_add_executor_job(
                        self.client.fetch_tbox_info
                    )
                except EvolUteAuthError as exc:
                    raise ConfigEntryAuthFailed(
                        "Evolute session expired. Sign in again in the integration settings."
                    ) from exc
                except EvolUteAPIError as exc:
                    raise UpdateFailed(f"Evolute API error: {exc}") from exc
            except EvolUteAPIError as exc:
                raise UpdateFailed(f"Evolute API error: {exc}") from exc

            # Parse tbox payload
            sensors_root: dict = (
                tbox_raw.get("sensors", {}) if isinstance(tbox_raw, dict) else {}
            )

            if isinstance(sensors_root.get("sensorsData"), dict):
                sensors = dict(sensors_root["sensorsData"])
            elif isinstance(sensors_root, dict):
                sensors = dict(sensors_root)

            # Merge scalar meta fields from top-level and sensors root
            for root in (tbox_raw, sensors_root):
                if not isinstance(root, dict):
                    continue
                for key, value in root.items():
                    if key in ("sensorsData", "positionData") or isinstance(
                        value, (dict, list)
                    ):
                        continue
                    sensors.setdefault(key, value)

            # Flatten preparation_script sub-object
            for root in (tbox_raw, sensors_root):
                ps = root.get("preparation_script") if isinstance(root, dict) else None
                if isinstance(ps, dict):
                    for ps_key, ps_val in ps.items():
                        sensors[f"preparation_script{ps_key[0].upper()}{ps_key[1:]}"] = (
                            ps_val
                        )

            # Alias sensorDataTime
            sensor_time = sensors.get("time")
            if sensor_time and "sensorDataTime" not in sensors:
                sensors["sensorDataTime"] = sensor_time

            # Position
            pos_raw = (
                sensors_root.get("positionData")
                if isinstance(sensors_root, dict)
                else None
            )
            if isinstance(pos_raw, dict):
                position = pos_raw

        # Log transitions between the two APIs (once per switch, not per poll)
        source = "telemetry" if used_telemetry else "tbox"
        if source != self.api_source:
            if used_telemetry:
                _LOGGER.info(
                    "Данные получаются через новый API (client-bff-service/telemetry)"
                )
            else:
                _LOGGER.warning(
                    "Новый telemetry API недоступен — использую старый tbox API"
                )
            self.api_source = source

        # ----------------------------------------------------------------
        # Car info — fetched once on first run, cached afterwards.
        # Preserve previously cached car_info on every subsequent poll so
        # we never wipe VIN/model from the sensors dict.
        # ----------------------------------------------------------------
        car_info = (self.data or {}).get("car_info", {})
        if not car_info:
            try:
                raw_car = await self.hass.async_add_executor_job(
                    self.client.fetch_car_info
                )
                self._raw_car = raw_car if isinstance(raw_car, dict) else None
                cm = raw_car.get("carModel") if isinstance(raw_car, dict) else {}
                car_info = {
                    "vin": raw_car.get("vin"),
                    "carModelName": cm.get("name") if isinstance(cm, dict) else None,
                    "carModelModname": (
                        cm.get("modname") if isinstance(cm, dict) else None
                    ),
                    "carModelYear": (
                        cm.get("modelYear") if isinstance(cm, dict) else None
                    ),
                    "carModelColor": (
                        cm.get("color") if isinstance(cm, dict) else None
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Could not fetch car info: %s", exc)

        sensors.update({k: v for k, v in car_info.items() if v is not None})

        # ----------------------------------------------------------------
        # Device id (IMEI) discovery for the new telemetry API. Runs while
        # unknown; once found it is persisted and the next poll switches to
        # the new endpoint automatically.
        # ----------------------------------------------------------------
        if not self.device_id:
            found = find_device_id(tbox_raw, self._raw_car)
            if found:
                self.device_id = found
                _LOGGER.info(
                    "Найден device id тбокса (%s) — со следующего обновления "
                    "использую новый telemetry API",
                    found,
                )
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, CONF_DEVICE_ID: found},
                )
            elif tbox_raw is not None and not self._device_id_warned:
                self._device_id_warned = True
                _LOGGER.warning(
                    "Device id (IMEI) не найден в ответах API — новый telemetry "
                    "API использоваться не будет, работаю через старый tbox API"
                )

        # ----------------------------------------------------------------
        # Stale-data guard: if the API returned identical sensor timestamp
        # as the last successful poll, reuse previous sensors dict wholesale
        # to avoid spurious state changes caused by partial/empty payloads.
        # ----------------------------------------------------------------
        prev_sensors: dict = (self.data or {}).get("sensors", {})
        new_time = sensors.get("sensorDataTime")
        prev_time = prev_sensors.get("sensorDataTime")

        if new_time and prev_time and new_time == prev_time:
            _LOGGER.debug(
                "sensorDataTime unchanged (%s) — reusing previous sensor values", new_time
            )
            # Connection and profile checks may change independently of the
            # vehicle's sensor timestamp. Keep those current even when parked.
            sensors = {
                **prev_sensors,
                **{
                    key: value for key, value in sensors.items()
                    if used_telemetry and key in {
                        "isOnline", "onlineState", "isCarStateReady",
                        "firmwareActual", "firmwareExpected", "firmwareMismatch",
                        "firmwareVersionText", "settingsActual", "settingsExpected",
                        "settingsMismatch",
                    }
                },
            }

        buttons = telemetry_raw.get("buttons") if used_telemetry else None
        return {
            "sensors": sensors, "position": position, "car_info": car_info,
            "buttons": buttons if isinstance(buttons, list) else None,
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
        return action in INTELLIGENT_ACTIONS

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

    async def _send_command(
        self, endpoint: str, value: Any = None, timeout: int = COMMAND_TIMEOUT
    ) -> None:
        """POST a command, refreshing tokens once on a 401."""
        call = functools.partial(
            self.client.tbox_command, endpoint, value=value, timeout=timeout
        )
        try:
            await self.hass.async_add_executor_job(call)
        except EvolUteAuthError:
            await self._async_refresh_and_persist()
            await self.hass.async_add_executor_job(call)

    async def async_send_action(self, action: str) -> None:
        """Prefer explicit commands and correlate their execution receipts."""
        if action not in TELEMETRY_ACTIONS:
            raise ValueError(f"Unknown action: {action}")
        if self._command_lock.locked():
            raise HomeAssistantError("Уже выполняется команда автомобиля")
        async with self._command_lock:
            if self.device_id:
                await self._telemetry_action(action)
                return
            if action not in INTELLIGENT_ACTIONS:
                raise HomeAssistantError("Эта команда требует нового API автомобиля")
            await self._legacy_action(action)

    async def _legacy_action(self, action: str) -> None:
        endpoint, status_key, skip_if_value = INTELLIGENT_ACTIONS[action]

        # Toggle commands flip the state server-side, so don't re-send when we
        # are already in the desired state. Push commands (status_key is None)
        # always fire.
        if status_key is not None:
            current = self.sensors.get(status_key)
            if current == skip_if_value:
                _LOGGER.debug("Action '%s' skipped: already in desired state", action)
                return

        await self._legacy_send(endpoint, timeout=COMMAND_TIMEOUT)

    async def _legacy_send(self, endpoint: str, **kwargs: Any) -> None:
        self.last_command = {"command": endpoint, "source": "tbox"}
        self._command_state("sending")
        try:
            await self._send_command(endpoint, **kwargs)
        except (EvolUteAPIError, EvolUteAuthError) as exc:
            self._command_state("unconfirmed")
            raise HomeAssistantError(
                "Не удалось подтвердить отправку команды. Проверьте состояние автомобиля."
            ) from exc
        self._command_state("legacy_sent")
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Preparation (предпрогрев)
    # ------------------------------------------------------------------

    def _prepare_value(self) -> dict[str, int]:
        """Build the PREPARE value object from the stored parameters."""
        p = self.prepare_params
        return {
            "flSeatHeating": p["fl"],
            "frSeatHeating": p["fr"],
            "rlSeatHeating": p["rl"],
            "rrSeatHeating": p["rr"],
            "wheelHeating": p["wheel"],
            "time": p["time"],
            "temp": p["temp"],
        }

    async def async_prepare(self) -> None:
        """Start preparation with the currently configured temp/time/heating."""
        await self._legacy_prepare(
            PREPARE_COMMAND, value=self._prepare_value(), timeout=PREPARE_TIMEOUT
        )

    async def async_cancel_prepare(self) -> None:
        """Cancel a running preparation."""
        await self._legacy_prepare(CANCEL_COMMAND, timeout=PREPARE_TIMEOUT)

    async def _legacy_prepare(self, endpoint: str, **kwargs: Any) -> None:
        # Custom seat/temperature parameters belong to PREPARE. The new
        # tripPreparationOn command uses the vehicle profile, not these values.
        if self._command_lock.locked():
            raise HomeAssistantError("Уже выполняется команда автомобиля")
        async with self._command_lock:
            await self._legacy_send(endpoint, **kwargs)
