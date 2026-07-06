"""API client and OAuth2 helpers for the Resideo Shutoff Valve integration.

The Resideo / Honeywell Home cloud is the same backend used by the built-in
``lyric`` integration, but that integration only models thermostats. This module
provides a small, self-contained client (no external dependency) that speaks the
shutoff-valve endpoints, plus the OAuth2 implementation required by Honeywell's
token endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import BasicAuth, ClientError, ClientResponseError, ClientSession
from homeassistant.components.application_credentials import AuthImplementation
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE, LOGGER, REQUEST_TIMEOUT


class ResideoAuthError(Exception):
    """Raised when authentication with the Resideo cloud fails."""


class ResideoConnectionError(Exception):
    """Raised when the Resideo cloud cannot be reached."""


class ResideoLocalOAuth2Implementation(AuthImplementation):
    """Local OAuth2 implementation for the Resideo / Honeywell Home cloud.

    Honeywell's token endpoint expects the client credentials to be supplied via
    HTTP Basic auth rather than in the request body, so ``_token_request`` is
    overridden to match. ``appSelect=1`` is added to the authorize request to
    match the behaviour of the official Lyric integration.
    """

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data appended to the authorize request."""
        return {"response_type": "code", "appSelect": "1"}

    async def _token_request(self, data: dict[str, Any]) -> dict[str, Any]:
        """Make a token request authenticated with HTTP Basic auth."""
        session = async_get_clientsession(self.hass)
        data["client_id"] = self.client_id

        resp = await session.post(
            self.token_url,
            data=data,
            auth=BasicAuth(self.client_id, self.client_secret),
        )
        resp.raise_for_status()
        return await resp.json()


class ResideoClient:
    """Authenticated client for the Resideo shutoff-valve API."""

    def __init__(
        self,
        websession: ClientSession,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialise the client."""
        self._websession = websession
        self._oauth_session = oauth_session

    @property
    def _apikey(self) -> str:
        """Return the API key (the OAuth client id doubles as the apikey)."""
        return self._oauth_session.implementation.client_id  # type: ignore[attr-defined]

    async def _async_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an authenticated request against the API."""
        await self._oauth_session.async_ensure_token_valid()
        access_token = self._oauth_session.token["access_token"]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        params: dict[str, Any] = kwargs.pop("params", {})
        params["apikey"] = self._apikey

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._websession.request(
                    method,
                    f"{API_BASE}{path}",
                    headers=headers,
                    params=params,
                    **kwargs,
                )
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ResideoAuthError(
                    f"Authentication failed for {method} {path}: {err.status}"
                ) from err
            raise ResideoConnectionError(
                f"Error from Resideo API {method} {path}: {err.status}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise ResideoConnectionError(
                f"Error communicating with Resideo API {method} {path}: {err}"
            ) from err

    async def async_get_locations(self) -> list[dict[str, Any]]:
        """Return all locations (each with its embedded ``devices`` list)."""
        result = await self._async_request("GET", "/locations")
        if not isinstance(result, list):
            LOGGER.debug("Unexpected locations payload: %s", result)
            return []
        return result

    async def async_get_valve(self, location_id: str, device_id: str) -> dict[str, Any]:
        """Return the detailed state of a single shutoff valve."""
        return await self._async_request(
            "GET",
            f"/devices/shutoffvalve/{device_id}",
            params={"locationId": location_id},
        )

    async def async_control_valve(
        self, location_id: str, device_id: str, state: str
    ) -> None:
        """Open or close a shutoff valve.

        ``state`` must be ``"open"`` or ``"close"``.
        """
        await self._async_request(
            "PUT",
            f"/devices/shutoffvalve/{device_id}/control",
            params={"locationId": location_id},
            json={"state": state},
        )
