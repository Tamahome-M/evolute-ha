"""Config flow for Evolute integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import EvolUteClient, EvolUteAuthError, EvolUteAPIError
from .const import (
    DOMAIN,
    CONF_CAR_ID,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _test_and_get_car_name(car_id: str, access_token: str, refresh_token: str) -> str:
    """Try fetching car info. Returns car name or raises."""
    client = EvolUteClient(car_id, access_token, refresh_token)
    # First try to refresh tokens to validate the pair
    try:
        client.refresh_tokens()
    except EvolUteAuthError as exc:
        raise exc
    # Then fetch car info to validate car_id
    info = client.fetch_car_info()
    cm = info.get("carModel") if isinstance(info, dict) else {}
    name = (cm.get("name") if isinstance(cm, dict) else None) or "Evolute"
    year = (cm.get("modelYear") if isinstance(cm, dict) else None) or ""
    return f"{name} {year}".strip(), client.access_token, client.refresh_token


_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CAR_ID): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=30, max=3600)
        ),
    }
)


class EvolUteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Evolute."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_CAR_ID])
            self._abort_if_unique_id_configured()

            try:
                car_title, fresh_access, fresh_refresh = await self.hass.async_add_executor_job(
                    _test_and_get_car_name,
                    user_input[CONF_CAR_ID],
                    user_input[CONF_ACCESS_TOKEN],
                    user_input[CONF_REFRESH_TOKEN],
                )
            except EvolUteAuthError:
                errors["base"] = "invalid_auth"
            except EvolUteAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                # Store refreshed tokens
                data = dict(user_input)
                data[CONF_ACCESS_TOKEN] = fresh_access
                data[CONF_REFRESH_TOKEN] = fresh_refresh
                return self.async_create_entry(title=car_title, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/Tamahome-M/evolute_proxy#как-получить-токены"
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EvolUteOptionsFlow(config_entry)


class EvolUteOptionsFlow(config_entries.OptionsFlow):
    """Allow changing scan interval and re-entering tokens."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._entry.options.get(
            CONF_SCAN_INTERVAL,
            self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_access = self._entry.data.get(CONF_ACCESS_TOKEN, "")
        current_refresh = self._entry.data.get(CONF_REFRESH_TOKEN, "")

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    int, vol.Range(min=30, max=3600)
                ),
                vol.Optional(CONF_ACCESS_TOKEN, default=current_access): str,
                vol.Optional(CONF_REFRESH_TOKEN, default=current_refresh): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
