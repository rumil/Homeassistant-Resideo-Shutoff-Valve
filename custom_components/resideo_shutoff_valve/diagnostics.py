"""Diagnostics support for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import ResideoConfigEntry

TO_REDACT = {
    "access_token",
    "refresh_token",
    "deviceMac",
    "macID",
    "userDefinedDeviceName",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ResideoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "valves": {
            device_id: async_redact_data(valve.raw, TO_REDACT)
            for device_id, valve in coordinator.data.items()
        },
    }
