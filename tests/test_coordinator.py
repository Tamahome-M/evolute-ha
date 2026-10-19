"""Test session recovery and the polling options used at runtime."""

from datetime import timedelta
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evolute import async_setup_entry
from custom_components.evolute.const import (
    BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
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
    requests_mock.get(f"{BASE_URL}/car-service/tbox/car/info", status_code=401)
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
