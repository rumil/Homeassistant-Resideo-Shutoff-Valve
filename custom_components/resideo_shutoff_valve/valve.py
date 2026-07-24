"""Valve platform for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
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


# The Resideo cloud is polled, and after a command it needs a moment to register
# the new state while the valve itself travels for a few seconds. An immediate
# poll therefore returns the *old* state, so short follow-up refreshes are
# scheduled to pick up the settled state within seconds rather than at the next
# regular (5-minute) update.
_SETTLE_REFRESH_DELAYS = (6, 18)
# Safety net: stop showing the optimistic transition after this long if the
# cloud never reports a state consistent with the command (e.g. it was operated
# elsewhere at the same time, or the command silently failed).
_OPTIMISTIC_TIMEOUT = 40


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
        # ``VALVE_STATE_OPEN`` / ``VALVE_STATE_CLOSE`` while a command is in
        # flight. The cloud lags the command, so without this the card would
        # flip back to the stale state; showing the transition until a poll
        # confirms it keeps the UI honest. ``None`` means the entity simply
        # mirrors the latest cloud reading.
        self._pending: str | None = None
        self._scheduled: list[CALLBACK_TYPE] = []

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any scheduled refreshes / the optimistic timeout."""
        self._cancel_scheduled()

    @callback
    def _cancel_scheduled(self) -> None:
        """Cancel and forget all pending scheduled callbacks."""
        for cancel in self._scheduled:
            cancel()
        self._scheduled.clear()

    @property
    def _mapped_status(self) -> str | None:
        """Return the normalised valve status, or ``None`` if unknown."""
        return VALVE_STATUS_MAP.get(self.valve_data.valve_status or "unknown")

    @property
    def is_closed(self) -> bool | None:
        """Return True if the valve is closed."""
        if self._pending is not None:
            # A command is in flight: report the transition (via is_opening /
            # is_closing), never a settled "closed", so the card animates
            # instead of prematurely reverting to the stale cloud value.
            return False
        status = self._mapped_status
        if status in (STATE_OPENING, STATE_CLOSING):
            return False
        if status is None:
            return None
        return status == STATE_CLOSED

    @property
    def is_opening(self) -> bool:
        """Return True if the valve is opening."""
        if self._pending == VALVE_STATE_OPEN:
            return True
        return self._mapped_status == STATE_OPENING

    @property
    def is_closing(self) -> bool:
        """Return True if the valve is closing."""
        if self._pending == VALVE_STATE_CLOSE:
            return True
        return self._mapped_status == STATE_CLOSING

    @callback
    def _handle_coordinator_update(self) -> None:
        """Drop the optimistic transition once the cloud agrees with it."""
        if self._pending is not None and self._command_confirmed():
            self._pending = None
        super()._handle_coordinator_update()

    def _command_confirmed(self) -> bool:
        """Return True when the latest poll reflects the in-flight command."""
        status = self._mapped_status
        if self._pending == VALVE_STATE_CLOSE:
            return status in (STATE_CLOSING, STATE_CLOSED)
        return status in (STATE_OPENING, STATE_OPEN)

    async def _async_command(self, state: str) -> None:
        """Send a control command and optimistically show the transition."""
        await self.coordinator.client.async_control_valve(
            self.valve_data.location_id, self._device_id, state
        )
        self._pending = state
        self._cancel_scheduled()
        self.async_write_ha_state()

        # Poll again shortly so the settled state shows within seconds instead
        # of at the next regular update, and time out the optimistic state as a
        # safety net if the cloud never catches up.
        for delay in _SETTLE_REFRESH_DELAYS:
            self._scheduled.append(
                async_call_later(self.hass, delay, self._async_scheduled_refresh)
            )
        self._scheduled.append(
            async_call_later(self.hass, _OPTIMISTIC_TIMEOUT, self._async_timeout)
        )

    async def _async_scheduled_refresh(self, _now) -> None:
        """Request a coordinator refresh from a scheduled callback."""
        await self.coordinator.async_request_refresh()

    @callback
    def _async_timeout(self, _now) -> None:
        """Give up on the optimistic transition after the timeout."""
        self._pending = None
        self._cancel_scheduled()
        self.async_write_ha_state()

    async def async_open_valve(self) -> None:
        """Open the valve."""
        await self._async_command(VALVE_STATE_OPEN)

    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self._async_command(VALVE_STATE_CLOSE)
