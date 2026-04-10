"""Fixtures for NES integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
                "accountContext": {
                    "accountNumber": "7013678056",
                    "userID": "test@example.com",
                },
                "accountSummaryType": {},
            }
        )
        client.async_get_usage = AsyncMock(return_value=MOCK_USAGE_DATA)
        client.customer_id = "105112"
        yield client


MOCK_USAGE_DATA = [
    {
        "chargeDate": "Feb 2026",
        "chargeDateRaw": "26-Feb-2026",
        "billedConsumption": "605",
        "billedCharge": "97.09",
        "daysOfService": "28",
        "counter": "KWH",
        "uom": "kWh",
        "meterNumber": "305244",
        "avgHigh": 0,
        "avgLow": 0,
        "temp": 43,
    },
    {
        "chargeDate": "Mar 2026",
        "chargeDateRaw": "26-Mar-2026",
        "billedConsumption": "797",
        "billedCharge": "128.50",
        "daysOfService": "31",
        "counter": "KWH",
        "uom": "kWh",
        "meterNumber": "305244",
        "avgHigh": 0,
        "avgLow": 0,
        "temp": 55,
    },
    {
        "chargeDate": "Apr 2026",
        "chargeDateRaw": "26-Apr-2026",
        "billedConsumption": "293",
        "billedCharge": "52.10",
        "daysOfService": "30",
        "counter": "KWH",
        "uom": "kWh",
        "meterNumber": "305244",
        "avgHigh": 0,
        "avgLow": 0,
        "temp": 65,
    },
]
