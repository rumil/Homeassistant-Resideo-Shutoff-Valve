"""Base entity for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResideoDataUpdateCoordinator, ResideoValveData


class ResideoValveEntity(CoordinatorEntity[ResideoDataUpdateCoordinator]):
    """Base class for entities backed by a single shutoff valve."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ResideoDataUpdateCoordinator, device_id: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def valve_data(self) -> ResideoValveData:
        """Return the current data for this valve."""
        return self.coordinator.data[self._device_id]

    @property
    def available(self) -> bool:
        """Return whether the valve is present in the latest update."""
        return super().available and self._device_id in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this valve."""
        data = self.valve_data
        connections = {(CONNECTION_NETWORK_MAC, data.mac)} if data.mac else set()
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            connections=connections,
            manufacturer="Resideo",
            model="L5 Wi-Fi Water Shutoff Valve",
            name=data.name,
        )
