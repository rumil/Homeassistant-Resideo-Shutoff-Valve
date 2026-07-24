"""Sensor platform for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import LEAK_STATUS_OPTIONS
from .coordinator import (
    ResideoConfigEntry,
    ResideoDataUpdateCoordinator,
    ResideoValveData,
)
from .entity import ResideoValveEntity


@dataclass(frozen=True, kw_only=True)
class ResideoSensorEntityDescription(SensorEntityDescription):
    """Describes a Resideo shutoff-valve sensor."""

    value_fn: Callable[[ResideoValveData], StateType | datetime]


SENSORS: tuple[ResideoSensorEntityDescription, ...] = (
    ResideoSensorEntityDescription(
        key="device_temperature",
        translation_key="device_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda valve: valve.device_temperature,
    ),
    ResideoSensorEntityDescription(
        key="leak_status",
        translation_key="leak_status",
        device_class=SensorDeviceClass.ENUM,
        options=LEAK_STATUS_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Fall back to ``None`` for any value the cloud reports that is not a
        # known option, so an unexpected status never crashes entity setup.
        value_fn=lambda valve: (
            valve.leak_status if valve.leak_status in LEAK_STATUS_OPTIONS else None
        ),
    ),
    ResideoSensorEntityDescription(
        key="motor_cycles",
        translation_key="motor_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda valve: valve.motor_cycles,
    ),
    ResideoSensorEntityDescription(
        key="last_checkin",
        translation_key="last_checkin",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda valve: valve.last_checkin,
    ),
    ResideoSensorEntityDescription(
        key="last_antiscale",
        translation_key="last_antiscale",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda valve: valve.last_antiscale,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ResideoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        ResideoSensor(coordinator, device_id, description)
        for device_id in coordinator.data
        for description in SENSORS
    )


class ResideoSensor(ResideoValveEntity, SensorEntity):
    """Representation of a Resideo shutoff-valve diagnostic sensor."""

    entity_description: ResideoSensorEntityDescription

    def __init__(
        self,
        coordinator: ResideoDataUpdateCoordinator,
        device_id: str,
        description: ResideoSensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.valve_data)
