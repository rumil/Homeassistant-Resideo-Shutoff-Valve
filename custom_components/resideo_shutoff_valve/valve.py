"""Valve platform for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPENING,
    VALVE_STATE_CLOSE,
    VALVE_STATE_OPEN,
    VALVE_STATUS_MAP,
)
from .coordinator import ResideoConfigEntry, ResideoDataUpdateCoordinator
from .entity import ResideoValveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ResideoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the valve entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        ResideoValve(coordinator, device_id) for device_id in coordinator.data
    )


class ResideoValve(ResideoValveEntity, ValveEntity):
    """Representation of an L5 water shutoff valve."""

    _attr_name = None
    _attr_device_class = ValveDeviceClass.WATER
    _attr_reports_position = False
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE

    def __init__(
        self, coordinator: ResideoDataUpdateCoordinator, device_id: str
    ) -> None:
        """Initialise the valve entity."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = device_id

    @property
    def _mapped_status(self) -> str | None:
        """Return the normalised valve status, or ``None`` if unknown."""
        return VALVE_STATUS_MAP.get(self.valve_data.valve_status or "unknown")

    @property
    def is_closed(self) -> bool | None:
        """Return True if the valve is closed."""
        status = self._mapped_status
        if status in (STATE_OPENING, STATE_CLOSING):
            return False
        if status is None:
            return None
        return status == STATE_CLOSED

    @property
    def is_opening(self) -> bool:
        """Return True if the valve is opening."""
        return self._mapped_status == STATE_OPENING

    @property
    def is_closing(self) -> bool:
        """Return True if the valve is closing."""
        return self._mapped_status == STATE_CLOSING

    async def async_open_valve(self) -> None:
        """Open the valve."""
        await self.coordinator.client.async_control_valve(
            self.valve_data.location_id, self._device_id, VALVE_STATE_OPEN
        )
        await self.coordinator.async_request_refresh()

    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self.coordinator.client.async_control_valve(
            self.valve_data.location_id, self._device_id, VALVE_STATE_CLOSE
        )
        await self.coordinator.async_request_refresh()
