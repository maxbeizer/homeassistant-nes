"""Tests for NES sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.nes.coordinator import NESDataUpdateCoordinator
from custom_components.nes.sensor import (
    SENSOR_DESCRIPTIONS,
    NESSensorEntity,
    _safe_float,
)


class TestSafeFloat:
    """Test the _safe_float helper."""

    def test_valid_float(self) -> None:
        assert _safe_float("19.0362") == pytest.approx(19.0362)

    def test_valid_int_string(self) -> None:
        assert _safe_float("82") == pytest.approx(82.0)

    def test_none(self) -> None:
        assert _safe_float(None) is None

    def test_empty_string(self) -> None:
        assert _safe_float("") is None

    def test_non_numeric(self) -> None:
        assert _safe_float("N/A") is None

    def test_numeric_zero(self) -> None:
        assert _safe_float("0") == pytest.approx(0.0)

    def test_actual_float(self) -> None:
        assert _safe_float(25.5) == pytest.approx(25.5)


class TestSensorDescriptions:
    """Test sensor entity descriptions are correct."""

    def test_correct_number_of_sensors(self) -> None:
        assert len(SENSOR_DESCRIPTIONS) == 5

    def test_daily_energy_is_energy_dashboard_compatible(self) -> None:
        daily = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_energy_usage")
        assert daily.device_class == SensorDeviceClass.ENERGY
        assert daily.state_class == SensorStateClass.TOTAL
        assert daily.native_unit_of_measurement == "kWh"

    def test_monthly_energy_is_energy_class(self) -> None:
        monthly = next(s for s in SENSOR_DESCRIPTIONS if s.key == "monthly_energy_usage")
        assert monthly.device_class == SensorDeviceClass.ENERGY

    def test_cost_is_monetary(self) -> None:
        cost = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_energy_cost")
        assert cost.device_class == SensorDeviceClass.MONETARY

    def test_temps_are_temperature(self) -> None:
        for key in ("daily_high_temp", "daily_low_temp"):
            temp = next(s for s in SENSOR_DESCRIPTIONS if s.key == key)
            assert temp.device_class == SensorDeviceClass.TEMPERATURE
            assert temp.native_unit_of_measurement == "°F"


class TestSensorValues:
    """Test sensor value extraction from coordinator data."""

    def _make_coordinator_data(self) -> dict:
        return {
            "daily": [],
            "latest": {
                "usageConsumptionValue": "19.0362",
                "billedCharge": "2.58",
                "usageHighTemp": "82",
                "usageLowTemp": "60",
            },
            "monthly_total_kwh": 74.64,
            "monthly_total_cost": 10.13,
        }

    def test_daily_energy_value(self) -> None:
        data = self._make_coordinator_data()
        desc = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_energy_usage")
        assert desc.value_fn(data) == pytest.approx(19.0362)

    def test_monthly_energy_value(self) -> None:
        data = self._make_coordinator_data()
        desc = next(s for s in SENSOR_DESCRIPTIONS if s.key == "monthly_energy_usage")
        assert desc.value_fn(data) == pytest.approx(74.64)

    def test_daily_cost_value(self) -> None:
        data = self._make_coordinator_data()
        desc = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_energy_cost")
        assert desc.value_fn(data) == pytest.approx(2.58)

    def test_high_temp_value(self) -> None:
        data = self._make_coordinator_data()
        desc = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_high_temp")
        assert desc.value_fn(data) == pytest.approx(82.0)

    def test_low_temp_value(self) -> None:
        data = self._make_coordinator_data()
        desc = next(s for s in SENSOR_DESCRIPTIONS if s.key == "daily_low_temp")
        assert desc.value_fn(data) == pytest.approx(60.0)

    def test_values_with_none_data(self) -> None:
        data = {"daily": [], "latest": {}, "monthly_total_kwh": 0.0, "monthly_total_cost": 0.0}
        for desc in SENSOR_DESCRIPTIONS:
            # Should not raise, should return None or 0.0
            value = desc.value_fn(data)
            assert value is None or isinstance(value, float)
