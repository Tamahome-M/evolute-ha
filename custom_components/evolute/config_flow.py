"""Config and reauthentication flows for Evolute."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

try:
    import probatio as vol
except ImportError:
    # Home Assistant versions before the validation library migration.
    import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import (
    EvolUteAPIError,
    EvolUteAuthError,
    EvolUteClient,
    EvolUteRateLimitError,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_PHONE_NUMBER,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SMS_CODE,
    CONF_TIMEOUT,
    CONF_TOKEN_REFRESH_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_TOKEN_REFRESH_INTERVAL,
    DOMAIN,
    LOGIN_PAGE_URL,
)
from .login_ui import EvoluteLoginSelector, async_ensure_login_ui


def _normalize_phone(value: str) -> str:
    """Accept formatted international numbers and common Russian formats."""
    if not re.fullmatch(r"\+?[0-9()\s-]+", value.strip()):
        raise ValueError("Invalid phone number")
    phone = re.sub(r"[^0-9]", "", value)
    if len(phone) == 10:
        phone = "7" + phone
    elif len(phone) == 11 and phone.startswith("8"):
        phone = "7" + phone[1:]
    if not re.fullmatch(r"[1-9][0-9]{7,14}", phone):
        raise ValueError("Invalid phone number")
    if phone.startswith("7") and len(phone) != 11:
        raise ValueError("Invalid phone number")
    return phone


def _login(phone: str, code: str) -> tuple[str, str]:
    """Run authentication in the executor and close the temporary session."""
    client = EvolUteClient()
    try:
        return client.login(phone, code)
    finally:
        client.close()


def _fetch_cars(access: str, refresh: str) -> list[dict]:
    """Discover cars and release the temporary HTTP session."""
    client = EvolUteClient(access_token=access, refresh_token=refresh)
    try:
        return client.fetch_cars()
    finally:
        client.close()


def _refresh_tokens(access: str, refresh: str) -> tuple[str, str]:
    """Refresh a session without tying rotation to successful car discovery."""
    client = EvolUteClient(access_token=access, refresh_token=refresh)
    try:
        return client.refresh_tokens()
    finally:
        client.close()


def _validate_tokens(car_id: str, access: str, refresh: str) -> tuple[dict, str, str]:
    """Validate manually supplied tokens and the selected car."""
    client = EvolUteClient(car_id, access, refresh)
    try:
        client.refresh_tokens()
        car = client.fetch_car_info()
        if not isinstance(car, dict):
            raise EvolUteAPIError("Evolute API returned invalid car information")
        return car, client.access_token, client.refresh_token
    finally:
        client.close()


def _car_title(car: dict) -> str:
    """Build a title using the model information returned by the app."""
    model = car.get("carModel")
    if not isinstance(model, dict):
        model = {}
    name = model.get("displayName") or model.get("name") or "Evolute"
    year = model.get("modelYear") or ""
    return f"{name} {year}".strip()


class EvolUteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Sign in with a phone number and SMS code, then discover the car."""

    VERSION = 1

    def __init__(self) -> None:
        self._phone = ""
        self._tokens: dict[str, str] = {}
        self._cars: dict[str, dict] = {}
        self._entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Choose between SMS authentication and manually supplied tokens."""
        return self.async_show_menu(step_id="user", menu_options=["phone", "token"])

    async def async_step_phone(self, user_input: dict | None = None) -> FlowResult:
        """Open the official SMS request form inside the current HA dialog."""
        await async_ensure_login_ui(self.hass)
        return await self.async_step_request_sms()

    async def async_step_request_sms(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Request the SMS before collecting the phone and code together."""
        if user_input is not None:
            return await self.async_step_sms()
        return self.async_show_form(
            step_id="request_sms",
            data_schema=vol.Schema(
                {vol.Optional("evassist"): self._login_selector("request")}
            ),
            description_placeholders={"official_login_url": LOGIN_PAGE_URL},
        )

    def _login_selector(self, mode: str) -> EvoluteLoginSelector:
        return EvoluteLoginSelector({"flow_id": self.flow_id, "mode": mode})

    async def async_step_token(self, user_input: dict | None = None) -> FlowResult:
        """Keep manual token authentication available for setup and recovery."""
        errors: dict[str, str] = {}
        if user_input is not None:
            car_id = (
                self._entry.data[CONF_CAR_ID]
                if self._entry is not None
                else user_input[CONF_CAR_ID].strip()
            )
            access = user_input[CONF_ACCESS_TOKEN].strip()
            refresh = user_input[CONF_REFRESH_TOKEN].strip()
            if not car_id or not access or not refresh:
                errors["base"] = "invalid_tokens"
            else:
                try:
                    car, access, refresh = await self.hass.async_add_executor_job(
                        _validate_tokens, car_id, access, refresh
                    )
                except EvolUteAuthError:
                    errors["base"] = "invalid_tokens"
                except EvolUteRateLimitError:
                    errors["base"] = "rate_limited"
                except EvolUteAPIError:
                    errors["base"] = "cannot_connect"
                else:
                    self._cars = {car_id: car}
                    self._tokens = {
                        CONF_ACCESS_TOKEN: access,
                        CONF_REFRESH_TOKEN: refresh,
                    }
                    return await self._async_finish(car_id)

        fields = {}
        if self._entry is None:
            fields[vol.Required(CONF_CAR_ID)] = str
        for key in (CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN):
            fields[vol.Required(key)] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        return self.async_show_form(
            step_id="token", data_schema=vol.Schema(fields), errors=errors
        )

    def _show_sms_form(self, errors: dict[str, str]) -> FlowResult:
        return self.async_show_form(
            step_id="sms",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PHONE_NUMBER, default=self._phone
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEL)
                    ),
                    # Empty defaults let the recovery action go back without
                    # submitting credentials. Both fields are validated below.
                    vol.Required(CONF_SMS_CODE, default=""): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                            autocomplete="one-time-code",
                        )
                    ),
                    vol.Optional("evassist"): self._login_selector("actions"),
                }
            ),
            errors=errors,
        )

    async def async_step_sms(self, user_input: dict | None = None) -> FlowResult:
        """Exchange a one-time code; never store the code in the config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get("evassist") == "request_again":
                self._tokens = {}
                self._cars = {}
                return await self.async_step_request_sms()
            try:
                self._phone = _normalize_phone(user_input[CONF_PHONE_NUMBER])
            except ValueError:
                errors[CONF_PHONE_NUMBER] = "invalid_phone"
            code = user_input[CONF_SMS_CODE].strip()
            if not re.fullmatch(r"[0-9]{4}", code):
                errors[CONF_SMS_CODE] = "invalid_code"
            if not errors:
                try:
                    access, refresh = await self.hass.async_add_executor_job(
                        _login, self._phone, code
                    )
                except EvolUteAuthError:
                    errors["base"] = "invalid_auth"
                except EvolUteRateLimitError:
                    errors["base"] = "rate_limited"
                except EvolUteAPIError:
                    errors["base"] = "cannot_connect"
                else:
                    self._tokens = {
                        CONF_ACCESS_TOKEN: access,
                        CONF_REFRESH_TOKEN: refresh,
                    }
                    return await self.async_step_select_car()

        return self._show_sms_form(errors)

    async def async_step_select_car(self, user_input: dict | None = None) -> FlowResult:
        """Allow retrying discovery without submitting an SMS code twice."""
        errors: dict[str, str] = {}
        if not self._cars:
            try:
                cars = await self._async_fetch_cars()
            except EvolUteAuthError:
                self._tokens = {}
                return self._show_sms_form({"base": "session_expired"})
            except EvolUteRateLimitError:
                errors["base"] = "rate_limited"
            except EvolUteAPIError:
                errors["base"] = "cannot_connect"
            else:
                self._cars = {car["_id"]: car for car in cars}
                if not self._cars:
                    self._tokens = {}
                    return self.async_abort(reason="no_cars")

        if self._cars:
            if self._entry is not None:
                car_id = self._entry.data[CONF_CAR_ID]
                if car_id not in self._cars:
                    self._tokens = {}
                    return self.async_abort(reason="wrong_account")
                return await self._async_finish(car_id)
            if len(self._cars) == 1:
                return await self._async_finish(next(iter(self._cars)))
            if user_input is not None and CONF_CAR_ID in user_input:
                if user_input[CONF_CAR_ID] in self._cars:
                    return await self._async_finish(user_input[CONF_CAR_ID])
                errors[CONF_CAR_ID] = "invalid_car"

        choices = {
            car_id: f"{_car_title(car)} ({car.get('vin') or car_id})"
            for car_id, car in self._cars.items()
        }
        fields = {vol.Required(CONF_CAR_ID): vol.In(choices)} if choices else {}
        fields[vol.Optional("evassist")] = self._login_selector("status")
        return self.async_show_form(
            step_id="select_car",
            data_schema=vol.Schema(fields),
            errors=errors,
        )

    async def _async_fetch_cars(self) -> list[dict]:
        """Keep rotated credentials even if the discovery retry fails."""
        try:
            return await self.hass.async_add_executor_job(
                _fetch_cars,
                self._tokens[CONF_ACCESS_TOKEN],
                self._tokens[CONF_REFRESH_TOKEN],
            )
        except EvolUteAuthError:
            access, refresh = await self.hass.async_add_executor_job(
                _refresh_tokens,
                self._tokens[CONF_ACCESS_TOKEN],
                self._tokens[CONF_REFRESH_TOKEN],
            )
            self._tokens = {
                CONF_ACCESS_TOKEN: access,
                CONF_REFRESH_TOKEN: refresh,
            }
            return await self.hass.async_add_executor_job(_fetch_cars, access, refresh)

    async def _async_finish(self, car_id: str) -> FlowResult:
        """Create an entry or update the same car after signing in again."""
        await self.async_set_unique_id(car_id)
        data = dict(self._tokens)
        if self._phone:
            data[CONF_PHONE_NUMBER] = self._phone
        self._tokens = {}
        if self._entry is not None:
            reason = (
                "reauth_successful"
                if self.context["source"] == config_entries.SOURCE_REAUTH
                else "reconfigure_successful"
            )
            self.hass.config_entries.async_update_entry(
                self._entry, data={**self._entry.data, **data}
            )
            await self.hass.config_entries.async_reload(self._entry.entry_id)
            return self.async_abort(reason=reason)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=_car_title(self._cars[car_id]),
            data={**data, CONF_CAR_ID: car_id},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Recover existing entries, including those originally set up with tokens."""
        self._entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if self._entry is None:
            return self.async_abort(reason="entry_removed")
        self._phone = entry_data.get(CONF_PHONE_NUMBER, "")
        return await self.async_step_user()

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Let users sign in again from the entry menu."""
        if self._entry is None:
            self._entry = self.hass.config_entries.async_get_entry(
                self.context["entry_id"]
            )
            if self._entry is None:
                return self.async_abort(reason="entry_removed")
            self._phone = self._entry.data.get(CONF_PHONE_NUMBER, "")
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EvolUteOptionsFlow(config_entry)


class EvolUteOptionsFlow(config_entries.OptionsFlow):
    """Change polling settings independently of authentication."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        fields = {}
        for key, default, minimum, maximum in (
            (CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, 30, 3600),
            (CONF_TIMEOUT, DEFAULT_TIMEOUT, 5, 120),
            (CONF_TOKEN_REFRESH_INTERVAL, DEFAULT_TOKEN_REFRESH_INTERVAL, 60, 86400),
        ):
            current = self._entry.options.get(key, self._entry.data.get(key, default))
            fields[vol.Optional(key, default=current)] = vol.All(
                int, vol.Range(min=minimum, max=maximum)
            )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
