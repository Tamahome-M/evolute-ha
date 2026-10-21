"""Test session recovery and the polling options used at runtime."""

from datetime import timedelta
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evolute import async_setup_entry
from custom_components.evolute.const import (
    BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_TOKEN_REFRESH_INTERVAL,
    DOMAIN,
    REFRESH_URL,
)
from custom_components.evolute.coordinator import EvolUteCoordinator


def make_entry(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="car",
        options=options or {},
        data={
            CONF_CAR_ID: "car",
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize(
    "status,error", [(401, ConfigEntryAuthFailed), (503, UpdateFailed)]
)
async def test_auth_and_network_failures_differ(hass, requests_mock, status, error):
    """Only an unrecoverable session should send HA into reauthentication."""
    entry = make_entry(hass)
    requests_mock.get(f"{BASE_URL}/car-service/car/v2/car", status_code=401)
    requests_mock.post(REFRESH_URL, status_code=status)
    coordinator = EvolUteCoordinator(hass, entry)
    coordinator._last_token_refresh = monotonic()
    try:
        with pytest.raises(error):
            await coordinator._async_update_data()
    finally:
        coordinator.client.close()


async def test_options_are_applied(hass):
    entry = make_entry(
        hass,
        {
            CONF_SCAN_INTERVAL: 240,
            CONF_TIMEOUT: 35,
            CONF_TOKEN_REFRESH_INTERVAL: 900,
        },
    )
    coordinator = EvolUteCoordinator(hass, entry)
    try:
        assert coordinator.update_interval == timedelta(seconds=240)
        assert coordinator.client.timeout == 35
        assert coordinator._token_refresh_interval == 900
    finally:
        coordinator.client.close()


async def test_only_options_changes_reload(hass):
    """Token persistence must not make all entities unavailable every refresh."""
    entry = make_entry(hass)
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    with (
        patch("custom_components.evolute.EvolUteCoordinator", return_value=coordinator),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
        ),
        patch.object(
            hass.config_entries, "async_reload", new_callable=AsyncMock
        ) as reload,
    ):
        assert await async_setup_entry(hass, entry)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ACCESS_TOKEN: "rotated"}
        )
        await hass.async_block_till_done()
        reload.assert_not_called()
        hass.config_entries.async_update_entry(entry, options={CONF_SCAN_INTERVAL: 300})
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)


async def test_imei_discovered_before_first_telemetry_and_persisted(hass, requests_mock):
    """Existing token entries need no tbox request or manual IMEI entry."""
    entry = make_entry(hass)
    car_url = f"{BASE_URL}/car-service/car/v2/car"
    telemetry_url = f"{BASE_URL}/client-bff-service/telemetry/123456789012345"
    requests_mock.get(car_url, json={
        "imei": "123456789012345", "vin": "TESTVIN",
        "carModel": {"name": "Evolute", "modelYear": "2026"},
    })
    requests_mock.get(telemetry_url, json={"sensors": {"batteryPercentage": "92"}})
    coordinator = EvolUteCoordinator(hass, entry)
    coordinator._last_token_refresh = monotonic()
    try:
        data = await coordinator._async_update_data()
        assert [r.url for r in requests_mock.request_history] == [car_url, telemetry_url]
        assert entry.data[CONF_DEVICE_ID] == "123456789012345"
        assert data["sensors"]["vin"] == "TESTVIN"
        assert data["sensors"]["batteryPercentage"] == "92"
        coordinator.data = data
        data = await coordinator._async_update_data()
        assert [r.url for r in requests_mock.request_history] == [car_url, telemetry_url, telemetry_url]
        assert data["sensors"]["vin"] == "TESTVIN"
    finally:
        coordinator.client.close()


@pytest.mark.parametrize("payload,status", [({}, 200), ([], 200), (None, 503)])
async def test_bad_telemetry_fails_without_using_old_api(hass, requests_mock, payload, status):
    entry = make_entry(hass)
    requests_mock.get(f"{BASE_URL}/car-service/car/v2/car", json={"imei": "123456789012345"})
    requests_mock.get(
        f"{BASE_URL}/client-bff-service/telemetry/123456789012345",
        json=payload, status_code=status,
    )
    coordinator = EvolUteCoordinator(hass, entry)
    coordinator._last_token_refresh = monotonic()
    try:
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert len(requests_mock.request_history) == 2
        assert all("/tbox/" not in r.url for r in requests_mock.request_history)
    finally:
        coordinator.client.close()


async def test_missing_imei_cannot_send_a_command(hass, requests_mock):
    entry = make_entry(hass)
    requests_mock.get(f"{BASE_URL}/car-service/car/v2/car", json={"carModel": {}})
    coordinator = EvolUteCoordinator(hass, entry)
    coordinator._last_token_refresh = monotonic()
    try:
        with pytest.raises(UpdateFailed, match="IMEI"):
            await coordinator._async_update_data()
        assert coordinator.action_available("heating_on") is False
        assert len(requests_mock.request_history) == 1
        assert all(r.method == "GET" for r in requests_mock.request_history)
    finally:
        coordinator.client.close()


async def test_removes_retired_entities_but_preserves_other_entities(hass):
    """Clean renamed and disabled old helpers without touching another car."""
    entry = make_entry(hass)
    other = MockConfigEntry(domain=DOMAIN, unique_id="other-car", data={})
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    retired = [
        ("button", "prepare_on"), ("button", "prepare_off"),
        ("number", "prepare_temp"), ("number", "prepare_duration"),
        ("number", "prepare_seat_fl"), ("number", "prepare_seat_fr"),
        ("number", "prepare_seat_rl"), ("number", "prepare_seat_rr"),
        ("number", "prepare_wheel"), ("binary_sensor", "prepare_running"),
        ("binary_sensor", "prepare_available"), ("sensor", "prepare_end"),
    ]
    removed = [registry.async_get_or_create(
        domain, DOMAIN, f"evolute_TESTVIN_{key}", config_entry=entry,
        suggested_object_id=f"renamed_{key}", disabled_by=er.RegistryEntryDisabler.USER,
    ).entity_id for domain, key in retired]
    kept = [
        registry.async_get_or_create(
            "button", DOMAIN, "evolute_TESTVIN_heating_on", config_entry=entry,
        ).entity_id,
        registry.async_get_or_create(
            "button", DOMAIN, "evolute_TESTVIN_trip_prepare_on", config_entry=entry,
        ).entity_id,
        registry.async_get_or_create(
            "button", DOMAIN, "evolute_OTHER_prepare_on", config_entry=other,
        ).entity_id,
        registry.async_get_or_create(
            "sensor", DOMAIN, "evolute_TESTVIN_custom", config_entry=entry,
        ).entity_id,
    ]
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    with (
        patch("custom_components.evolute.EvolUteCoordinator", return_value=coordinator),
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
    ):
        assert await async_setup_entry(hass, entry)
        assert all(registry.async_get(entity_id) is None for entity_id in removed)
        assert all(registry.async_get(entity_id) is not None for entity_id in kept)
