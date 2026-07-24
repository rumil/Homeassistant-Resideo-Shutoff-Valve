"""Constants for the Resideo Shutoff Valve integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "resideo_shutoff_valve"

LOGGER: Final = logging.getLogger(__package__)

# OAuth2 / API endpoints (shared with the Honeywell Home / Resideo cloud).
OAUTH2_AUTHORIZE: Final = "https://api.honeywellhome.com/oauth2/authorize"
OAUTH2_TOKEN: Final = "https://api.honeywellhome.com/oauth2/token"
API_BASE: Final = "https://api.honeywellhome.com/v2"

# Networking.
REQUEST_TIMEOUT: Final = 20

# Resideo device class that identifies an L5 shutoff valve.
DEVICE_CLASS_SHUTOFF_VALVE: Final = "ShutoffValve"

# Valve control states accepted by the ``/control`` endpoint.
VALVE_STATE_OPEN: Final = "open"
VALVE_STATE_CLOSE: Final = "close"

# Normalised HA-facing valve states.
STATE_OPEN: Final = "open"
STATE_CLOSED: Final = "closed"
STATE_OPENING: Final = "opening"
STATE_CLOSING: Final = "closing"

# Maps the Resideo ``valveStatus`` field to a normalised HA valve state.
# ``None`` means the state is unknown / indeterminate. Keys are lower case;
# ``ResideoValveData.valve_status`` lower-cases the raw value before lookup.
VALVE_STATUS_MAP: Final[dict[str, str | None]] = {
    "open": STATE_OPEN,
    "close": STATE_CLOSED,
    "closed": STATE_CLOSED,
    "notopen": STATE_CLOSED,
    "opening": STATE_OPENING,
    "antiscaleopening": STATE_OPENING,
    "closing": STATE_CLOSING,
    "antiscaleclosing": STATE_CLOSING,
    "notclose": None,
    "unknown": None,
    "err": None,
}

# Possible ``leakStatus`` values reported by the actuator valve.
LEAK_STATUS_OPTIONS: Final = ["ok", "leak", "na", "err"]
