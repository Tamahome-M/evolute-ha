"""DataUpdateCoordinator for Evolute."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EvolUteClient, EvolUteAuthError, EvolUteAPIError
from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    CONF_CAR_ID,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_TOKEN_REFRESH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_TOKEN_REFRESH_INTERVAL,
    INTELLIGENT_ACTIONS,
)

_LOGGER = logging.getLogger(__name__)


class EvolUteCoordinator(DataUpdateCoordinator):
    """Manages polling evassist.ru and issuing commands."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self._token_refresh_interval: int = entry.data.get(
            CONF_TOKEN_REFRESH_INTERVAL, DEFAULT_TOKEN_REFRESH_INTERVAL
        )
        self._last_token_refresh: float = 0.0
        self.client = EvolUteClient(
            car_id=entry.data[CONF_CAR_ID],
            access_token=entry.data[CONF_ACCESS_TOKEN],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
            timeout=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
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
        import time
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
        import time
        # Proactive token refresh by configured interval
        if time.monotonic() - self._last_token_refresh >= self._token_refresh_interval:
            _LOGGER.debug("Proactive token refresh (interval=%ds)", self._token_refresh_interval)
            try:
                await self._async_refresh_and_persist()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Proactive token refresh failed: %s", exc)

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
                raise UpdateFailed(
                    "Tokens are invalid. Open integration settings and enter new tokens."
                ) from exc
        except EvolUteAPIError as exc:
            raise UpdateFailed(f"Evolute API error: {exc}") from exc

        # Parse tbox payload ― same logic as evolute_api.py
        sensors: dict = {}
        position: dict = {}
        sensors_root: dict = tbox_raw.get("sensors", {}) if isinstance(tbox_raw, dict) else {}

        if isinstance(sensors_root.get("sensorsData"), dict):
            sensors = dict(sensors_root["sensorsData"])
        elif isinstance(sensors_root, dict):
            sensors = dict(sensors_root)

        # Merge scalar meta fields from top-level and sensors root
        for root in (tbox_raw, sensors_root):
            if not isinstance(root, dict):
                continue
            for key, value in root.items():
                if key in ("sensorsData", "positionData") or isinstance(value, (dict, list)):
                    continue
                sensors.setdefault(key, value)

        # Flatten preparation_script sub-object
        for root in (tbox_raw, sensors_root):
            ps = root.get("preparation_script") if isinstance(root, dict) else None
            if isinstance(ps, dict):
                for ps_key, ps_val in ps.items():
                    sensors[f"preparation_script_{ps_key[0].upper()}{ps_key[1:]}"] = ps_val

        # Alias sensorDataTime
        sensor_time = sensors.get("time")
        if sensor_time and "sensorDataTime" not in sensors:
            sensors["sensorDataTime"] = sensor_time

        # Position
        pos_raw = sensors_root.get("positionData") if isinstance(sensors_root, dict) else None
        if isinstance(pos_raw, dict):
            position = pos_raw

        # Car info (fetched once on first run, cached afterwards)
        car_info = (self.data or {}).get("car_info", {})
        if not car_info:
            try:
                raw_car = await self.hass.async_add_executor_job(
                    self.client.fetch_car_info
                )
                cm = raw_car.get("carModel") if isinstance(raw_car, dict) else {}
                car_info = {
                    "vin": raw_car.get("vin"),
                    "carModelName": cm.get("name") if isinstance(cm, dict) else None,
                    "carModelModname": cm.get("modname") if isinstance(cm, dict) else None,
                    "carModelYear": cm.get("modelYear") if isinstance(cm, dict) else None,
                    "carModelColor": cm.get("color") if isinstance(cm, dict) else None,
                }
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Could not fetch car info: %s", exc)

        sensors.update({k: v for k, v in car_info.items() if v is not None})

        return {"sensors": sensors, "position": position, "car_info": car_info}

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

    async def async_send_action(self, action: str) -> None:
        """Send an intelligent tbox action with skip-if-already logic."""
        if action not in INTELLIGENT_ACTIONS:
            raise ValueError(f"Unknown action: {action}")

        endpoint, status_key, skip_if_value = INTELLIGENT_ACTIONS[action]

        current = self.sensors.get(status_key)
        if current == skip_if_value:
            _LOGGER.debug("Action '%s' skipped: already in desired state", action)
            return

        try:
            await self.hass.async_add_executor_job(
                self.client.tbox_command, endpoint
            )
        except EvolUteAuthError:
            await self._async_refresh_and_persist()
            await self.hass.async_add_executor_job(
                self.client.tbox_command, endpoint
            )

        await self.async_request_refresh()
