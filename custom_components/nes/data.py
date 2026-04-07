"""Custom types for the NES integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import NESApiClient
    from .coordinator import NESDataUpdateCoordinator


@dataclass
class NESData:
    """Runtime data for the NES integration."""

    client: NESApiClient
    coordinator: NESDataUpdateCoordinator
    integration: Integration


type NESConfigEntry = ConfigEntry[NESData]
