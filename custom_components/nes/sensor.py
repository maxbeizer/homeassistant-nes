"""Sensor platform for Nashville Electric Service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NESDataUpdateCoordinator
from .data import NESConfigEntry
from .entity import NESEntity


@dataclass(frozen=True, kw_only=True)
class NESSensorEntityDescription(SensorEntityDescription):
    """Describe an NES sensor entity."""

    value_fn: Callable[[dict[str, Any]], float | None]


SENSOR_DESCRIPTIONS: tuple[NESSensorEntityDescription, ...] = (
    NESSensorEntityDescription(
        key="monthly_energy_usage",
        translation_key="monthly_energy_usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: _safe_float(
            data.get("latest", {}).get("billedConsumption")
        ),
    ),
    NESSensorEntityDescription(
        key="monthly_energy_cost",
        translation_key="monthly_energy_cost",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: _safe_float(data.get("latest", {}).get("billedCharge")),
    ),
    NESSensorEntityDescription(
        key="yearly_energy_usage",
        translation_key="yearly_energy_usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("total_kwh"),
    ),
    NESSensorEntityDescription(
        key="yearly_energy_cost",
        translation_key="yearly_energy_cost",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("total_cost"),
    ),
)


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NESConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NES sensor entities."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        NESSensorEntity(
            coordinator=coordinator,
            entry_id=entry.entry_id,
            description=description,
        )
        for description in SENSOR_DESCRIPTIONS
    )


class NESSensorEntity(NESEntity, SensorEntity):
    """NES sensor entity."""

    entity_description: NESSensorEntityDescription

    def __init__(
        self,
        coordinator: NESDataUpdateCoordinator,
        entry_id: str,
        description: NESSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
