"""Fixtures for testing the integration with Home Assistant."""

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture
def mock_setup_entry():
    """Keep config flow tests independent of entity setup and polling."""
    with patch(
        "custom_components.evolute.async_setup_entry",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock:
        yield mock
