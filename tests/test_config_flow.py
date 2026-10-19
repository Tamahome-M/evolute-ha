"""Exercise the real Home Assistant setup and recovery flows."""

from unittest.mock import AsyncMock, patch

import pytest
import requests
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evolute.const import (
    BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DEVICE_ID,
    CONF_PHONE_NUMBER,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SMS_CODE,
    DOMAIN,
    LOGIN_URL,
    REFRESH_URL,
)

SEARCH_URL = f"{BASE_URL}/car-service/car/v2/search"
CAR = {
    "_id": "car-1",
    "vin": "TEST-VIN-1",
    "carModel": {"name": "i-JOY", "modelYear": 2024},
}
TOKENS = {"accessToken": "access", "refreshToken": "refresh"}

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture(autouse=True)
def auth_responses(requests_mock, mock_setup_entry):
    """Default successful login and car discovery without any real requests."""
    requests_mock.post(LOGIN_URL, json=TOKENS)
    requests_mock.post(REFRESH_URL, json=TOKENS)
    requests_mock.post(SEARCH_URL, json={"rows": [CAR], "total": 1})
    requests_mock.get(f"{BASE_URL}/car-service/car/v2/car-1", json=CAR)


async def start(hass, method="phone", context=None, data=None):
    """Start a chosen login method through the actual flow manager."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context=context or {"source": config_entries.SOURCE_USER},
        data=data,
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["phone", "token"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": method},
    )


async def phone_step(hass, result):
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PHONE_NUMBER: "+7 (999) 123-45-67"},
    )


async def sms_step(hass, result):
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SMS_CODE: "0123"},
    )


async def test_sms_setup(hass):
    """A single car is discovered automatically and the code is never saved."""
    result = await phone_step(hass, await start(hass))
    assert result["step_id"] == "sms"
    assert result["description_placeholders"]["phone_number"] == "+79991234567"
    result = await sms_step(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "i-JOY 2024"
    assert result["data"] == {
        CONF_CAR_ID: "car-1",
        CONF_PHONE_NUMBER: "79991234567",
        CONF_ACCESS_TOKEN: "access",
        CONF_REFRESH_TOKEN: "refresh",
    }
    assert result["result"].unique_id == "car-1"
    assert CONF_SMS_CODE not in result["data"]


async def test_manual_tokens_still_work(hass, requests_mock):
    """Manual setup stores the refreshed pair and retains the car's unique ID."""
    requests_mock.post(
        REFRESH_URL, json={"accessToken": "fresh", "refreshToken": "rotated"}
    )
    result = await start(hass, "token")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CAR_ID: "car-1",
            CONF_ACCESS_TOKEN: "old",
            CONF_REFRESH_TOKEN: "old-refresh",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "car-1"
    assert result["data"][CONF_ACCESS_TOKEN] == "fresh"
    assert result["data"][CONF_REFRESH_TOKEN] == "rotated"
    assert CONF_PHONE_NUMBER not in result["data"]


@pytest.mark.parametrize("number", ["", "abc", "123", "+7 1234567", "7+9991234567"])
async def test_bad_phone(hass, number, requests_mock):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PHONE_NUMBER: number},
    )
    assert result["errors"] == {CONF_PHONE_NUMBER: "invalid_phone"}
    assert requests_mock.call_count == 0


@pytest.mark.parametrize(
    "response,error",
    [
        ({"status_code": 400}, "invalid_auth"),
        ({"status_code": 429}, "rate_limited"),
        ({"exc": requests.Timeout}, "cannot_connect"),
        ({"json": {}}, "cannot_connect"),
    ],
)
async def test_login_failures(hass, requests_mock, response, error):
    requests_mock.post(LOGIN_URL, **response)
    result = await sms_step(hass, await phone_step(hass, await start(hass)))
    assert result["step_id"] == "sms"
    assert result["errors"] == {"base": error}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_bad_code_then_retry(hass, requests_mock):
    result = await phone_step(hass, await start(hass))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SMS_CODE: "12ab"},
    )
    assert result["errors"] == {CONF_SMS_CODE: "invalid_code"}
    assert requests_mock.call_count == 0
    result = await sms_step(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_car_selection(hass, requests_mock):
    second = {**CAR, "_id": "car-2", "vin": "TEST-VIN-2"}
    requests_mock.post(SEARCH_URL, json={"rows": [CAR, second], "total": 2})
    result = await sms_step(hass, await phone_step(hass, await start(hass)))
    assert result["step_id"] == "select_car"
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CAR_ID: "not-in-account"}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CAR_ID: "car-2"},
    )
    assert result["data"][CONF_CAR_ID] == "car-2"


async def test_discovery_retry_keeps_rotated_session(hass, requests_mock):
    login = requests_mock.post(LOGIN_URL, json=TOKENS)
    requests_mock.post(
        REFRESH_URL, json={"accessToken": "fresh", "refreshToken": "rotated"}
    )
    requests_mock.post(
        SEARCH_URL,
        [
            {"status_code": 401},
            {"exc": requests.Timeout},
            {"json": {"rows": [CAR], "total": 1}},
        ],
    )
    result = await sms_step(hass, await phone_step(hass, await start(hass)))
    assert result["step_id"] == "select_car"
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REFRESH_TOKEN] == "rotated"
    assert login.call_count == 1
    assert "evy-platform-access=fresh" in requests_mock.last_request.headers["Cookie"]


@pytest.mark.parametrize(
    "existing,reason", [(False, "no_cars"), (True, "already_configured")]
)
async def test_empty_account_and_duplicate(hass, requests_mock, existing, reason):
    if existing:
        MockConfigEntry(domain=DOMAIN, unique_id="car-1", data={}).add_to_hass(hass)
    else:
        requests_mock.post(SEARCH_URL, json={"rows": [], "total": 0})
    result = await sms_step(hass, await phone_step(hass, await start(hass)))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


@pytest.mark.parametrize(
    "source", [config_entries.SOURCE_REAUTH, config_entries.SOURCE_RECONFIGURE]
)
@pytest.mark.parametrize("method", ["phone", "token"])
async def test_existing_entry_sign_in(hass, method, source):
    """Both methods recover legacy entries without replacing entities or options."""
    original = {
        CONF_CAR_ID: "car-1",
        CONF_ACCESS_TOKEN: "old",
        CONF_REFRESH_TOKEN: "old-refresh",
        CONF_DEVICE_ID: "123456789012345",
        CONF_SCAN_INTERVAL: 180,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="car-1",
        data=original,
        options={CONF_SCAN_INTERVAL: 240},
    )
    entry.add_to_hass(hass)
    entry.add_update_listener(AsyncMock())
    result = await start(
        hass, method, {"source": source, "entry_id": entry.entry_id}, original
    )
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as reload:
        if method == "phone":
            result = await sms_step(hass, await phone_step(hass, result))
        else:
            assert CONF_CAR_ID not in result["data_schema"].schema
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_ACCESS_TOKEN: "old",
                    CONF_REFRESH_TOKEN: "old-refresh",
                },
            )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == (
            "reauth_successful"
            if source == config_entries.SOURCE_REAUTH
            else "reconfigure_successful"
        )
        reload.assert_awaited_once_with(entry.entry_id)
    assert entry.data[CONF_ACCESS_TOKEN] == "access"
    assert entry.data[CONF_DEVICE_ID] == original[CONF_DEVICE_ID]
    assert entry.data[CONF_SCAN_INTERVAL] == 180
    assert dict(entry.options) == {CONF_SCAN_INTERVAL: 240}
    assert entry.unique_id == "car-1"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reauth_wrong_account(hass, requests_mock):
    original = {
        CONF_CAR_ID: "car-1",
        CONF_ACCESS_TOKEN: "old",
        CONF_REFRESH_TOKEN: "old-refresh",
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id="car-1", data=original)
    entry.add_to_hass(hass)
    requests_mock.post(
        SEARCH_URL, json={"rows": [{"_id": "different-car"}], "total": 1}
    )
    result = await start(
        hass,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=original,
    )
    result = await sms_step(hass, await phone_step(hass, result))
    assert result["reason"] == "wrong_account"
    assert dict(entry.data) == original


async def test_options_hide_credentials(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_SCAN_INTERVAL: 180})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert set(result["data_schema"].schema) == {
        "scan_interval",
        "timeout",
        "token_refresh_interval",
    }
    assert result["data_schema"]({})[CONF_SCAN_INTERVAL] == 180
