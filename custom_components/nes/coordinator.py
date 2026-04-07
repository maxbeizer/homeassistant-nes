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
            return {"daily": [], "latest": {}, "monthly_total_kwh": 0.0, "monthly_total_cost": 0.0}

        # Sort by date, most recent last
        sorted_data = sorted(
            usage_data,
            key=lambda x: x.get("usageDate", ""),
        )

        latest = sorted_data[-1] if sorted_data else {}

        # Sum up monthly totals
        monthly_total_kwh = sum(
            float(day.get("usageConsumptionValue", 0) or 0) for day in sorted_data
        )
        monthly_total_cost = sum(
            float(day.get("billedCharge", 0) or 0) for day in sorted_data
        )

        return {
            "daily": sorted_data,
            "latest": latest,
            "monthly_total_kwh": round(monthly_total_kwh, 2),
            "monthly_total_cost": round(monthly_total_cost, 2),
        }
