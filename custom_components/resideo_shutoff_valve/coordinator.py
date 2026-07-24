"""DataUpdateCoordinator for the Resideo Shutoff Valve integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ResideoAuthError, ResideoClient, ResideoConnectionError
from .const import DEVICE_CLASS_SHUTOFF_VALVE, DOMAIN, LOGGER

type ResideoConfigEntry = ConfigEntry[ResideoDataUpdateCoordinator]

UPDATE_INTERVAL = timedelta(seconds=300)


@dataclass
class ResideoValveData:
    """Normalised view of a single shutoff valve's state."""

    location_id: str
    raw: dict[str, Any]

    @property
    def _actuator(self) -> dict[str, Any]:
        return self.raw.get("actuatorValve") or {}

    @property
    def device_id(self) -> str:
        """Return the unique Resideo device id."""
        return self.raw["deviceID"]

    @property
    def name(self) -> str:
        """Return a human-friendly device name."""
        return (
            self.raw.get("userDefinedDeviceName")
            or self.raw.get("name")
            or "Shutoff Valve"
        )

    @property
    def mac(self) -> str | None:
        """Return the device MAC address, if known."""
        return self.raw.get("deviceMac") or self.raw.get("macID")

    @property
    def is_alive(self) -> bool:
        """Return whether the device is currently online."""
        return bool(self.raw.get("isAlive"))

    @property
    def valve_status(self) -> str | None:
        """Return the ``valveStatus`` value, normalised to lower case.

        The cloud reports these values capitalised (e.g. ``"Open"``), so they
        are lower-cased here to give the rest of the integration a single,
        predictable casing to match against.
        """
        status = self._actuator.get("valveStatus")
        return status.lower() if status is not None else None

    @property
    def leak_status(self) -> str | None:
        """Return the ``leakStatus`` value, normalised to lower case."""
        status = self._actuator.get("leakStatus")
        return status.lower() if status is not None else None

    @property
    def device_temperature(self) -> float | None:
        """Return the device temperature in degrees Fahrenheit."""
        return self._actuator.get("deviceTemperature")

    @property
    def motor_cycles(self) -> int | None:
        """Return the cumulative number of motor cycles."""
        return self._actuator.get("motorCycles")

    @property
    def last_checkin(self) -> datetime | None:
        """Return the last check-in time as a timezone-aware datetime."""
        return _parse_datetime(self.raw.get("lastCheckin"))

    @property
    def last_antiscale(self) -> datetime | None:
        """Return the last anti-scale maintenance time."""
        return _parse_datetime(self._actuator.get("lastAntiScaleTime"))


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an API timestamp into a timezone-aware datetime."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


class ResideoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, ResideoValveData]]):
    """Coordinator that polls all shutoff valves across the account."""

    config_entry: ResideoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ResideoConfigEntry,
        client: ResideoClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        # Cached ``(location_id, device_id)`` pairs for every shutoff valve on
        # the account. Populated on the first refresh (see ``_async_update_data``)
        # and reused thereafter so steady-state polling never re-downloads the
        # whole account device tree. ``None`` means discovery has not run yet.
        self._valves: list[tuple[str, str]] | None = None

    async def _async_update_data(self) -> dict[str, ResideoValveData]:
        """Fetch the latest state of every shutoff valve.

        Discovery — *which* valves exist and the location each belongs to — is a
        one-time step. The ``/locations`` endpoint returns the entire account
        device tree (every thermostat, security panel and camera), so it is
        queried only once: on the first refresh, or after a reload. The
        resulting ids are cached, and subsequent polls fetch each valve directly
        by id, keeping every refresh to a single small request per valve.
        """
        try:
            if self._valves is None:
                self._valves = await self._async_discover_valves()

            valves: dict[str, ResideoValveData] = {}
            for location_id, device_id in self._valves:
                detail = await self.client.async_get_valve(location_id, device_id)
                valves[device_id] = ResideoValveData(location_id, detail)
        except ResideoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ResideoConnectionError as err:
            raise UpdateFailed(str(err)) from err

        LOGGER.debug("Updated %d shutoff valve(s)", len(valves))
        return valves

    async def _async_discover_valves(self) -> list[tuple[str, str]]:
        """Discover every shutoff valve and return its location/device ids.

        Adding a valve to the account requires reloading the integration to
        create its entities, so re-running discovery on every poll served no
        purpose; it is deliberately done just once and cached.
        """
        discovered: list[tuple[str, str]] = []
        locations = await self.client.async_get_locations()
        for location in locations:
            location_id = str(location.get("locationID"))
            for device in location.get("devices", []):
                if device.get("deviceClass") != DEVICE_CLASS_SHUTOFF_VALVE:
                    continue
                discovered.append((location_id, device["deviceID"]))

        LOGGER.debug("Discovered %d shutoff valve(s)", len(discovered))
        return discovered
