"""Evolute API client — direct access to app.evassist.ru."""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

from .const import BASE_URL, REFRESH_URL, USER_AGENT, DEFAULT_TIMEOUT


_LOGGER = logging.getLogger(__name__)


class EvolUteAuthError(Exception):
    """Raised when tokens are invalid and refresh fails."""


class EvolUteAPIError(Exception):
    """General API error."""


class EvolUteClient:
    """Low-level HTTP client for evassist.ru."""

    def __init__(self, car_id: str, access_token: str, refresh_token: str,
                 timeout: int = DEFAULT_TIMEOUT) -> None:
        self.car_id = car_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT

    def _cookies(self) -> dict[str, str]:
        return {
            "evy-platform-access": self.access_token,
            "evy-platform-refresh": self.refresh_token,
        }

    def refresh_tokens(self) -> tuple[str, str]:
        """Exchange refresh token for a new pair. Returns (access, refresh)."""
        try:
            resp = self._session.post(
                REFRESH_URL,
                json={"refreshToken": self.refresh_token},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EvolUteAPIError(f"Network error during token refresh: {exc}") from exc

        if resp.status_code == 401:
            raise EvolUteAuthError("Refresh token rejected (401). Re-enter tokens.")
        if resp.status_code == 403:
            raise EvolUteAuthError("Refresh token forbidden (403). Re-enter tokens.")
        if not resp.ok:
            raise EvolUteAPIError(f"Token refresh failed: HTTP {resp.status_code}")

        data = resp.json()
        self.access_token = data["accessToken"]
        self.refresh_token = data["refreshToken"]
        _LOGGER.debug("Tokens refreshed successfully")
        return self.access_token, self.refresh_token

    def _get(self, url: str) -> Any:
        resp = self._session.get(url, cookies=self._cookies(), timeout=self.timeout)
        if resp.status_code == 401:
            raise EvolUteAuthError("Access denied (401). Tokens expired.")
        resp.raise_for_status()
        return resp.json()

    def _post(self, url: str, payload: dict | None = None,
              timeout: int | None = None) -> Any:
        resp = self._session.post(
            url,
            cookies=self._cookies(),
            json=payload or {},
            timeout=timeout or self.timeout,
        )
        if resp.status_code == 401:
            raise EvolUteAuthError("Access denied (401). Tokens expired.")
        resp.raise_for_status()
        # Command endpoints may legitimately return an empty body.
        try:
            return resp.json()
        except ValueError:
            return None

    def fetch_tbox_info(self) -> dict:
        url = f"{BASE_URL}/car-service/tbox/{self.car_id}/info"
        return self._get(url)

    def fetch_telemetry(self, device_id: str) -> dict:
        """Fetch data from the new client-bff telemetry endpoint.

        Unlike the tbox endpoints (which use the car id), this one is keyed
        by the tbox device id (IMEI). Errors are normalised to
        EvolUteAuthError / EvolUteAPIError so the coordinator can cleanly
        fall back to the old API.
        """
        url = f"{BASE_URL}/client-bff-service/telemetry/{device_id}"
        try:
            resp = self._session.get(
                url,
                cookies=self._cookies(),
                headers={"x-app": "web", "Accept": "*/*"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EvolUteAPIError(f"Telemetry network error: {exc}") from exc
        if resp.status_code == 401:
            raise EvolUteAuthError("Access denied (401). Tokens expired.")
        if not resp.ok:
            raise EvolUteAPIError(f"Telemetry HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise EvolUteAPIError(f"Telemetry returned invalid JSON: {exc}") from exc

    def fetch_car_info(self) -> dict:
        url = f"{BASE_URL}/car-service/car/v2/{self.car_id}"
        return self._get(url)

    def tbox_command(self, endpoint: str, value: Any = None,
                     timeout: int | None = None) -> Any:
        """Send a remote command.

        Commands go to the versioned endpoint
        ``/car-service/tbox/v1/{car_id}/{command}``. For ordinary toggle/push
        commands ``value`` is None and the body is empty (the server flips the
        state by command name). For PREPARE, ``value`` is the heating/temp/time
        object and is wrapped as ``{"value": value}`` — exactly like the app.
        """
        url = f"{BASE_URL}/car-service/tbox/v1/{self.car_id}/{endpoint}"
        payload = {} if value is None else {"value": value}
        return self._post(url, payload, timeout=timeout)


# ---------------------------------------------------------------------------
# Helpers for the new client-bff telemetry API (pure functions, no HA deps)
# ---------------------------------------------------------------------------

# Mapping of new telemetry keys → legacy tbox keys used by the existing
# entities and by the INTELLIGENT_ACTIONS skip-logic. The second tuple item
# tells whether the value must be coerced to a 0/1 int flag.
_TELEMETRY_LEGACY_MAP: dict[str, tuple[str, bool]] = {
    "isIgnitionOn": ("ignitionStatus", True),
    "isCentralLockingOn": ("centralLockingStatus", True),
    "isTrunkOpen": ("trunkStatus", True),
    "isParkedOn": ("isParked", False),
    "remainsBatteryMileage": ("remainsMileage", False),
    "remainsFuelMileage": ("remainsMileageFuel", False),
}

_IMEI_RE = re.compile(r"^\d{15,17}$")


def _as_int_flag(value: Any) -> int:
    """Coerce bool / \"true\" / \"1\" style values to a 0/1 int."""
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("1", "true", "on") else 0
    return int(bool(value))


def parse_telemetry(raw: Any) -> tuple[dict, dict] | None:
    """Validate + normalise a client-bff telemetry payload.

    Returns ``(sensors, position)`` on success or ``None`` when the payload
    does not look like a usable telemetry response (the caller then falls
    back to the old tbox API).
    """
    if not isinstance(raw, dict):
        return None
    src = raw.get("sensors")
    if not isinstance(src, dict) or not src:
        return None

    sensors = dict(src)

    # Merge scalar meta fields from the top level (isOnline, onlineState,
    # isCarStateReady, carStateUpdatedAt, …).
    for key, value in raw.items():
        if isinstance(value, (dict, list)):
            continue
        sensors.setdefault(key, value)

    # Legacy aliases so the existing entities and the toggle skip-logic keep
    # working regardless of which API produced the data.
    for new_key, (legacy_key, to_flag) in _TELEMETRY_LEGACY_MAP.items():
        if new_key in sensors and legacy_key not in sensors:
            val = sensors[new_key]
            sensors[legacy_key] = _as_int_flag(val) if to_flag else val

    # climateStatus is not exposed directly — derive it from the heating /
    # cooling button states in the same payload.
    if "climateStatus" not in sensors:
        climate_on = any(
            btn.get("status")
            and btn.get("activateCommand") in ("heatingOn", "coolingOn")
            for btn in raw.get("buttons", [])
            if isinstance(btn, dict)
        )
        sensors["climateStatus"] = 1 if climate_on else 0

    # Keep the «Время данных» sensor and the coordinator's stale-data guard
    # working: carStateUpdatedAt is a ms unix timestamp.
    if "sensorDataTime" not in sensors and raw.get("carStateUpdatedAt"):
        sensors["sensorDataTime"] = raw["carStateUpdatedAt"]

    # Position: telemetry keeps GPS in the flat sensors dict. lat/lon == 0
    # means "no fix / hidden" — leave position empty in that case.
    position: dict = {}
    try:
        lat = float(sensors.get("lat"))
        lon = float(sensors.get("lon"))
        if abs(lat) > 1e-6 or abs(lon) > 1e-6:
            position = {"lat": lat, "lon": lon, "course": sensors.get("course")}
    except (TypeError, ValueError):
        pass

    return sensors, position


def find_device_id(*payloads: Any) -> str | None:
    """Best-effort search for the tbox device id (IMEI) in API payloads.

    The new telemetry endpoint is keyed by a 15-digit device id rather than
    the car id, and the id is not entered by the user — so we hunt for it in
    the tbox / car-info responses. Preference order: keys containing
    ``imei`` → device/tbox/terminal-like keys → any bare 15–17 digit value.
    """
    by_key: list[str] = []
    by_hint: list[str] = []
    by_value: list[str] = []

    def _walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(v, k)
        elif isinstance(node, list):
            for item in node:
                _walk(item, key)
        else:
            text = str(node)
            if not _IMEI_RE.match(text):
                return
            key_l = key.lower()
            if "imei" in key_l:
                by_key.append(text)
            elif any(h in key_l for h in ("device", "tbox", "terminal", "modem")):
                by_hint.append(text)
            else:
                by_value.append(text)

    for payload in payloads:
        _walk(payload)

    for bucket in (by_key, by_hint, by_value):
        if bucket:
            return bucket[0]
    return None
