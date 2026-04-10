"""DataUpdateCoordinator for the NES integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NESApiClient, NESAuthError, NESConnectionError
from .const import LOGGER, UPDATE_INTERVAL_HOURS


def _safe_float_or_zero(value: Any) -> float:
    """Safely convert a value to float, defaulting to 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class NESDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching NES usage data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: NESApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="NES Usage Data",
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the NES API."""
        try:
            usage_data = await self.client.async_get_usage()
        except NESAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain="nes",
                translation_key="auth_failed",
            ) from err
        except NESConnectionError as err:
            raise UpdateFailed(f"Error communicating with NES API: {err}") from err

        if not usage_data:
            return {"monthly": [], "latest": {}, "total_kwh": 0.0, "total_cost": 0.0}

        # Data comes as monthly history sorted chronologically
        # Each item: chargeDate, billedConsumption, billedCharge, etc.
        latest = usage_data[-1] if usage_data else {}

        total_kwh = sum(
            _safe_float_or_zero(m.get("billedConsumption")) for m in usage_data
        )
        total_cost = sum(
            _safe_float_or_zero(m.get("billedCharge")) for m in usage_data
        )

        return {
            "monthly": usage_data,
            "latest": latest,
            "total_kwh": round(total_kwh, 2),
            "total_cost": round(total_cost, 2),
        }
