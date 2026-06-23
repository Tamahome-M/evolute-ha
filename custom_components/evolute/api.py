"""Evolute API client — direct access to app.evassist.ru."""
from __future__ import annotations

import logging
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
