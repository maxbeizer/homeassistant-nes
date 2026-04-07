"""Fixtures for NES integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.nes.const import DOMAIN


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.nes.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_nes_client() -> Generator[MagicMock]:
    """Create a mock NES API client."""
    with patch(
        "custom_components.nes.config_flow.NESApiClient",
        autospec=True,
    ) as mock_cls:
        client = mock_cls.return_value
        client.async_authenticate = AsyncMock()
        client.async_get_customer = AsyncMock(
            return_value={
                "customerId": "12345",
                "accountContext": {"accountNumber": "98765"},
            }
        )
        client.async_get_usage = AsyncMock(
            return_value=MOCK_USAGE_DATA,
        )
        client.customer_id = "12345"
        yield client


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MagicMock:
    """Create a mock config entry."""
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="NES (12345)",
        data={
            "username": "test@example.com",
            "password": "testpassword",
        },
        source="user",
        unique_id="12345",
    )
    return entry


MOCK_USAGE_DATA = [
    {
        "usageDate": "04/05/2026",
        "usageConsumptionValue": "25.5",
        "billedCharge": "3.45",
        "billedConsumption": "25.5",
        "usageHighTemp": "78",
        "usageLowTemp": "55",
        "uom": "KWH",
        "netReceivedValue": "0",
        "netReceivedCategory": None,
    },
    {
        "usageDate": "04/06/2026",
        "usageConsumptionValue": "19.0362",
        "billedCharge": "2.58",
        "billedConsumption": "19.0362",
        "usageHighTemp": "82",
        "usageLowTemp": "60",
        "uom": "KWH",
        "netReceivedValue": "0",
        "netReceivedCategory": None,
    },
    {
        "usageDate": "04/07/2026",
        "usageConsumptionValue": "30.1",
        "billedCharge": "4.10",
        "billedConsumption": "30.1",
        "usageHighTemp": "85",
        "usageLowTemp": "62",
        "uom": "KWH",
        "netReceivedValue": "0",
        "netReceivedCategory": None,
    },
]
