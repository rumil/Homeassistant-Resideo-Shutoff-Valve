"""Binary sensor platform for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    ResideoConfigEntry,
    ResideoDataUpdateCoordinator,
    ResideoValveData,
)
from .entity import ResideoValveEntity


@dataclass(frozen=True, kw_only=True)
class ResideoBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Resideo shutoff-valve binary sensor."""

    value_fn: Callable[[ResideoValveData], bool]


BINARY_SENSORS: tuple[ResideoBinarySensorEntityDescription, ...] = (
    ResideoBinarySensorEntityDescription(
        key="leak",
        translation_key="leak",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda valve: valve.leak_status == "leak",
    ),
    ResideoBinarySensorEntityDescription(
        key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda valve: valve.is_alive,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ResideoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        ResideoBinarySensor(coordinator, device_id, description)
        for device_id in coordinator.data
        for description in BINARY_SENSORS
    )


class ResideoBinarySensor(ResideoValveEntity, BinarySensorEntity):
    """Representation of a Resideo shutoff-valve binary sensor."""

    entity_description: ResideoBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: ResideoDataUpdateCoordinator,
        device_id: str,
        description: ResideoBinarySensorEntityDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        """Return True if the binary sensor is on."""
        return self.entity_description.value_fn(self.valve_data)
