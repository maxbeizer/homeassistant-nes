"""Tests for the NES data update coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.nes.api import NESApiClient, NESAuthError, NESConnectionError
from custom_components.nes.coordinator import NESDataUpdateCoordinator

from conftest import MOCK_USAGE_DATA


async def test_coordinator_successful_update(hass: HomeAssistant) -> None:
    """Test coordinator fetches and processes data correctly."""
    client = MagicMock(spec=NESApiClient)
    client.async_get_usage = AsyncMock(return_value=MOCK_USAGE_DATA)

    coordinator = NESDataUpdateCoordinator(hass, client)
    data = await coordinator._async_update_data()

    assert len(data["daily"]) == 3
    # Latest should be the most recent date
    assert data["latest"]["usageDate"] == "04/07/2026"
    # Monthly totals
    assert data["monthly_total_kwh"] == pytest.approx(74.64, abs=0.01)
    assert data["monthly_total_cost"] == pytest.approx(10.13, abs=0.01)


async def test_coordinator_empty_data(hass: HomeAssistant) -> None:
    """Test coordinator handles empty usage data."""
    client = MagicMock(spec=NESApiClient)
    client.async_get_usage = AsyncMock(return_value=[])

    coordinator = NESDataUpdateCoordinator(hass, client)
    data = await coordinator._async_update_data()

    assert data["daily"] == []
    assert data["latest"] == {}
    assert data["monthly_total_kwh"] == 0.0
    assert data["monthly_total_cost"] == 0.0


async def test_coordinator_auth_error_raises_reauth(
    hass: HomeAssistant,
) -> None:
    """Test coordinator converts auth errors to ConfigEntryAuthFailed."""
    client = MagicMock(spec=NESApiClient)
    client.async_get_usage = AsyncMock(side_effect=NESAuthError("Token expired"))

    coordinator = NESDataUpdateCoordinator(hass, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_connection_error_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    """Test coordinator converts connection errors to UpdateFailed."""
    client = MagicMock(spec=NESApiClient)
    client.async_get_usage = AsyncMock(
        side_effect=NESConnectionError("Network down")
    )

    coordinator = NESDataUpdateCoordinator(hass, client)

    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()


async def test_coordinator_handles_malformed_values(
    hass: HomeAssistant,
) -> None:
    """Test coordinator handles non-numeric values gracefully."""
    bad_data = [
        {
            "usageDate": "04/07/2026",
            "usageConsumptionValue": "N/A",
            "billedCharge": None,
        },
        {
            "usageDate": "04/06/2026",
            "usageConsumptionValue": "10.5",
            "billedCharge": "1.50",
        },
    ]
    client = MagicMock(spec=NESApiClient)
    client.async_get_usage = AsyncMock(return_value=bad_data)

    coordinator = NESDataUpdateCoordinator(hass, client)
    data = await coordinator._async_update_data()

    # "N/A" and None should be treated as 0
    assert data["monthly_total_kwh"] == pytest.approx(10.5, abs=0.01)
    assert data["monthly_total_cost"] == pytest.approx(1.50, abs=0.01)
