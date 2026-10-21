"""Command receipts must describe the correct command and never cause replays."""

from copy import deepcopy
from time import monotonic
from unittest.mock import AsyncMock, patch

import pytest
import requests
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evolute.api import (
    EvolUteAPIError,
    EvolUteClient,
    parse_telemetry,
)
from custom_components.evolute.binary_sensor import BINARY_SENSORS, EvolUteBinarySensor
from custom_components.evolute.const import (
    BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    REFRESH_URL,
)
from custom_components.evolute.coordinator import EvolUteCoordinator
from custom_components.evolute.lock import EvolUteLock
from custom_components.evolute.sensor import EvolUteCommandStatusSensor

DEVICE = "123456789012345"
COMMAND_URL = f"{BASE_URL}/client-bff-service/telemetry-commands"
STATUS_URL = f"{COMMAND_URL}/{DEVICE}"
TELEMETRY_URL = f"{BASE_URL}/client-bff-service/telemetry/{DEVICE}"
TELEMETRY = {
    "sensors": {
        "isCentralLockingOn": False, "isParkedOn": True, "isTrunkOpen": False,
        "isChargingGunInserted": True, "batteryTemp": "19", "batteryPercentage": "92",
        "remainsBatteryMileage": "101", "odometer": "1234", "12VBatteryVoltage": "13.8",
        "outsideTemp": "24", "inBoardTemp": "28", "climateTargetTemp": "24",
    },
    "isOnline": True,
    "onlineState": "connected",
    "carStateUpdatedAt": 1000,
    "buttons": [{
        "tag": "central-lock", "enabled": True, "status": True,
        "activateCommand": "centralLockingOff", "deactivateCommand": "centralLockingOn",
    }, {
        "tag": "trip-preparation", "enabled": True, "status": False,
        "activateCommand": "tripPreparationOn", "deactivateCommand": "tripPreparationOff",
    }],
    "firmwareCheck": {"actual": "old", "expected": "new", "mismatch": True},
    "settingsCheck": {"actual": "profile", "expected": "profile", "mismatch": False},
}


@pytest.fixture
async def command_coord(hass, requests_mock):
    original_time_zone = dt_util.DEFAULT_TIME_ZONE
    entry = MockConfigEntry(domain=DOMAIN, unique_id="car", data={
        CONF_CAR_ID: "car", CONF_DEVICE_ID: DEVICE,
        CONF_ACCESS_TOKEN: "access", CONF_REFRESH_TOKEN: "refresh",
    })
    entry.add_to_hass(hass)
    requests_mock.get(TELEMETRY_URL, json=deepcopy(TELEMETRY))
    requests_mock.get(f"{BASE_URL}/car-service/car/v2/car", json={"carModel": {}})
    coord = EvolUteCoordinator(hass, entry)
    # The fixture constructs this before HA enters the setup context which
    # normally associates DataUpdateCoordinator with its config entry.
    coord.config_entry = entry
    coord._last_token_refresh = monotonic()
    coord.async_request_refresh = AsyncMock()
    with patch("custom_components.evolute.coordinator.COMMAND_POLL_INTERVAL", 0):
        yield coord
    await coord.async_shutdown()
    coord.client.close()
    dt_util.set_default_time_zone(original_time_zone)


async def test_receipts_are_correlated_and_published(command_coord, requests_mock):
    """Ignore an old success, then publish each receipt for the accepted UUID."""
    coord = command_coord
    requests_mock.post(COMMAND_URL, status_code=201, json={"commandId": "ours"})
    requests_mock.get(STATUS_URL, [
        {"text": ""},
        {"json": {"commandId": "previous", "status": "success"}},
        {"json": {"commandId": "ours", "status": "pending"}},
        {"json": {"commandId": "ours", "status": "delivered"}},
        {"json": {"commandId": "ours", "status": "pending"}},
        {"json": {"commandId": "ours", "status": "success"}},
    ])
    sensor = EvolUteCommandStatusSensor(coord)
    lock = EvolUteLock(coord)
    states = []
    remove = coord.async_add_listener(lambda: states.append(sensor.native_value))
    try:
        await coord.async_send_action("lock_close")
    finally:
        remove()
    assert [s for i, s in enumerate(states) if not i or states[i - 1] != s] == [
        "idle", "sending", "pending", "delivered", "success",
    ]
    assert sensor.extra_state_attributes["command_id"] == "ours"
    assert sensor.extra_state_attributes["command"] == "centralLockingOn"
    assert lock.is_locking is False
    posts = [r for r in requests_mock.request_history if r.method == "POST"]
    assert len(posts) == 1
    assert posts[0].url == COMMAND_URL
    assert posts[0].json() == {"commandName": "centralLockingOn", "imei": DEVICE}
    assert "evy-platform-access=access" in posts[0].headers["Cookie"]
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_command_sensor_in_real_ha_service_flow(hass, command_coord, requests_mock):
    """Load the platforms and execute a lock service with mocked HTTP only."""
    coord = command_coord
    hass.config.language = "ru"
    coord.async_request_refresh = coord.async_refresh
    def executed(request, context):
        telemetry = deepcopy(TELEMETRY)
        telemetry["sensors"]["isCentralLockingOn"] = True
        telemetry["carStateUpdatedAt"] = 2000
        requests_mock.get(TELEMETRY_URL, json=telemetry)
        return {"commandId": "service-command", "status": "success"}
    requests_mock.post(COMMAND_URL, json={"commandId": "service-command"})
    requests_mock.get(STATUS_URL, [
        {"json": {"commandId": "service-command", "status": "delivered"}},
        {"json": executed},
    ])
    with patch("custom_components.evolute.EvolUteCoordinator", return_value=coord):
        assert await hass.config_entries.async_setup(coord._entry.entry_id)
        await hass.async_block_till_done()
    lock = next(s for s in hass.states.async_all("lock"))
    status = next(s for s in hass.states.async_all("sensor") if "Статус последней команды" in s.name)
    assert status.state == "idle"
    try:
        await hass.services.async_call("lock", "lock", {"entity_id": lock.entity_id}, blocking=True)
        await hass.async_block_till_done()
        state = hass.states.get(status.entity_id)
        assert state.state == "success"
        assert state.attributes["command_id"] == "service-command"
        assert hass.states.get(lock.entity_id).state == "locked"
        assert state.attributes["options"] == [
            "idle", "sending", "pending", "delivered", "success", "error",
            "timeout", "unconfirmed", "legacy_sent",
        ]
    finally:
        await hass.config_entries.async_unload(coord._entry.entry_id)
        await hass.async_stop()


@pytest.mark.parametrize("failure", ["error", "timeout", "network", "empty", "malformed"])
async def test_no_legacy_fallback_or_replay(command_coord, requests_mock, failure):
    coord = command_coord
    requests_mock.post(COMMAND_URL, status_code=201, json={"commandId": "ours"})
    status = {"commandId": "ours", "status": "error"}
    if failure == "timeout":
        status = {"commandId": "someone-else", "status": "success"}
    requests_mock.get(STATUS_URL, json=status)
    if failure == "network":
        requests_mock.post(COMMAND_URL, exc=requests.Timeout)
    if failure == "empty":
        requests_mock.post(COMMAND_URL, status_code=204)
    if failure == "malformed":
        requests_mock.post(COMMAND_URL, json={"accepted": True})
    with (
        patch("custom_components.evolute.coordinator.COMMAND_CONFIRM_TIMEOUT", 0.01),
        pytest.raises(HomeAssistantError),
    ):
        await coord.async_send_action("lock_close")
    expected = failure if failure in {"error", "timeout"} else "unconfirmed"
    assert coord.last_command["status"] == expected
    posts = [r for r in requests_mock.request_history if r.method == "POST"]
    assert len(posts) == 1
    assert posts[0].url == COMMAND_URL


async def test_status_auth_refresh_does_not_resubmit(command_coord, requests_mock):
    coord = command_coord
    requests_mock.post(COMMAND_URL, status_code=201, json={"commandId": "ours"})
    requests_mock.get(STATUS_URL, [
        {"status_code": 401},
        {"json": {"commandId": "ours", "status": "success"}},
    ])
    requests_mock.post(REFRESH_URL, json={"accessToken": "new", "refreshToken": "new-r"})
    await coord.async_send_action("lock_open")
    assert coord.last_command["status"] == "success"
    assert coord._entry.data[CONF_ACCESS_TOKEN] == "new"
    assert len([r for r in requests_mock.request_history if r.url == COMMAND_URL]) == 1
    assert "evy-platform-access=new" in requests_mock.last_request.headers["Cookie"]


async def test_another_action_cannot_queue_behind_a_pending_command(command_coord, requests_mock):
    coord = command_coord
    requests_mock.post(COMMAND_URL, json={"commandId": "ours"})
    requests_mock.get(STATUS_URL, json={"commandId": "ours", "status": "success"})
    rejected = []

    async def pending(command_id):
        assert EvolUteLock(coord).is_locking is True
        with pytest.raises(HomeAssistantError):
            await coord.async_send_action("lock_open")
        rejected.append(command_id)

    with patch.object(coord, "_wait_command", side_effect=pending):
        await coord.async_send_action("lock_close")
    assert rejected == ["ours"]
    assert len([r for r in requests_mock.request_history if r.method == "POST"]) == 1


@pytest.mark.parametrize("blocked", ["disabled", "missing", "offline", "moving"])
async def test_capability_and_current_state_checked_before_sending(command_coord, requests_mock, blocked):
    telemetry = deepcopy(TELEMETRY)
    if blocked == "disabled":
        telemetry["buttons"][0]["enabled"] = False
    elif blocked == "missing":
        telemetry["buttons"] = []
    elif blocked == "offline":
        telemetry["isOnline"] = False
    else:
        telemetry["sensors"]["isParkedOn"] = False
    requests_mock.get(TELEMETRY_URL, json=telemetry)
    with pytest.raises(HomeAssistantError):
        await command_coord.async_send_action("lock_close")
    assert not any(r.method == "POST" for r in requests_mock.request_history)


async def test_legacy_commands_keep_their_payload_and_do_not_claim_execution(command_coord, requests_mock):
    coord = command_coord
    coord.device_id = None
    coord.data = {"sensors": {"centralLockingStatus": 0}}
    url = f"{BASE_URL}/car-service/tbox/v1/car/centralLockingToggle"
    requests_mock.post(url, status_code=204)
    await coord.async_send_action("lock_close")
    assert requests_mock.last_request.json() == {}
    assert coord.last_command["status"] == "legacy_sent"
    requests_mock.post(f"{BASE_URL}/car-service/tbox/v1/car/PREPARE", status_code=204)
    coord.prepare_params.update(temp=25, fl=2)
    await coord.async_prepare()
    assert requests_mock.last_request.json()["value"]["temp"] == 25
    assert requests_mock.last_request.json()["value"]["flSeatHeating"] == 2


async def test_profile_diagnostics_and_connection_refresh_at_same_timestamp(command_coord, requests_mock):
    coord = command_coord
    await coord.async_refresh()
    assert coord.sensors["firmwareMismatch"] is True
    assert coord.sensors["settingsMismatch"] is False
    desc = next(d for d in BINARY_SENSORS if d.key == "firmware_mismatch")
    problem = EvolUteBinarySensor(coord, desc)
    assert problem.is_on is True
    assert problem.extra_state_attributes == {"actual": "old", "expected": "new"}
    changed = deepcopy(TELEMETRY)
    changed["isOnline"] = False
    changed["onlineState"] = "disconnected"
    changed["firmwareCheck"]["mismatch"] = False
    requests_mock.get(TELEMETRY_URL, json=changed)
    await coord.async_refresh()
    assert coord.sensors["isOnline"] is False
    assert coord.sensors["onlineState"] == "disconnected"
    assert problem.is_on is False
    assert coord.sensors["sensorDataTime"] == 1000


@pytest.mark.parametrize("payload", [{}, [], {"status": "success"}, {"commandId": "x", "status": "unexpected"}])
def test_invalid_receipt_is_not_treated_as_success(requests_mock, payload):
    requests_mock.get(STATUS_URL, json=payload)
    client = EvolUteClient("car", "access", "refresh")
    try:
        with pytest.raises(EvolUteAPIError):
            client.fetch_command_status(DEVICE)
    finally:
        client.close()


def test_profile_trip_preparation_and_absent_buttons():
    telemetry = deepcopy(TELEMETRY)
    telemetry["buttons"][1]["status"] = True
    sensors, _ = parse_telemetry(telemetry)
    assert sensors["tripPreparationRunning"] == 1
    telemetry["buttons"] = None
    assert parse_telemetry(telemetry) is not None
