"""API client and OAuth2 helpers for the Resideo Shutoff Valve integration.

The Resideo / Honeywell Home cloud is the same backend used by the built-in
``lyric`` integration, but that integration only models thermostats. This module
provides a small, self-contained client (no external dependency) that speaks the
shutoff-valve endpoints, plus the OAuth2 implementation required by Honeywell's
token endpoint.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import (
    ClientError,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    encode_basic_auth,
)
from homeassistant.components.application_credentials import AuthImplementation
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE, LOGGER, REQUEST_TIMEOUT

# OAuth ``error`` codes (RFC 6749 §5.2) that mean the grant is dead: the stored
# refresh token will never work again, so the only recovery is reauthentication.
# Any other token-endpoint failure (other 4xx, 5xx, network) is treated as
# transient and retried; see ``ResideoTokenError.is_permanent``.
DEAD_GRANT_ERROR_CODES = frozenset({"invalid_grant", "invalid_client"})


class ResideoAuthError(Exception):
    """Raised when authentication has permanently failed (grant is dead).

    The coordinator maps this to ``ConfigEntryAuthFailed`` so Home Assistant
    marks every entity unavailable and immediately starts a reauth flow.
    """


class ResideoConnectionError(Exception):
    """Raised for a transient failure (network, 5xx, recoverable token error).

    The coordinator maps this to ``UpdateFailed`` so entities go unavailable but
    polling continues and recovers on its own once the cloud responds again.
    """


class ResideoTokenError(Exception):
    """A token-endpoint refresh failure, carrying the parsed OAuth error code.

    Raised from :meth:`ResideoLocalOAuth2Implementation._token_request` for the
    ``refresh_token`` grant. Because it is a plain ``Exception`` (not a
    ``ClientError`` or one of core's ``OAuth2TokenRequest*`` types), it passes
    straight through core's token-refresh machinery instead of being remapped to
    ``OAuth2TokenRequestReauthError`` — which would otherwise start a reauth flow
    for *every* 4xx and bypass this integration's own transient/permanent
    classification.
    """

    def __init__(self, *, status: int, error_code: str | None) -> None:
        """Store the HTTP status and the OAuth ``error`` code from the body."""
        self.status = status
        self.error_code = error_code
        detail = f"{status} {error_code}" if error_code else str(status)
        super().__init__(f"Token refresh failed: {detail}")

    @property
    def is_permanent(self) -> bool:
        """Return True when the grant is dead and reauth is the only recovery."""
        return self.status == 401 or self.error_code in DEAD_GRANT_ERROR_CODES

    def as_api_error(self) -> ResideoAuthError | ResideoConnectionError:
        """Return the client-level error matching this failure's severity."""
        if self.is_permanent:
            return ResideoAuthError(str(self))
        return ResideoConnectionError(str(self))


class ResideoOAuth2Session(config_entry_oauth2_flow.OAuth2Session):
    """OAuth2 session whose forced refresh shares the core token lock.

    Honeywell's cloud is known to reject access tokens *before* their nominal
    expiry: the stored token stops working even though ``expires_at`` is still in
    the future, and ``async_ensure_token_valid`` only refreshes once it has
    passed. :meth:`async_refresh_token_if_unchanged` forces a refresh in that
    case, but it does so under the session's own ``_token_lock`` — the same lock
    ``async_ensure_token_valid`` holds — so a forced refresh can never run
    concurrently with an expiry refresh or another forced refresh. Honeywell is
    believed to rotate refresh tokens, so two concurrent refreshes would send the
    same (soon-invalidated) refresh token and kill the grant.
    """

    async def async_refresh_token_if_unchanged(self, access_token_before: str) -> None:
        """Refresh the token once, unless another caller already refreshed it.

        ``access_token_before`` is the access token the caller used for the
        request that just failed. Under the lock, if the stored access token no
        longer matches it, another caller has already refreshed and the caller
        should simply retry with the current token — so this returns without
        making a second (racing) token request.
        """
        async with self._token_lock:
            if self.token.get("access_token") != access_token_before:
                return
            new_token = await self.implementation.async_refresh_token(self.token)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, "token": new_token},
            )


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
        """Make a token request authenticated with HTTP Basic auth.

        On an error response the body's ``error`` / ``error_description`` are
        logged at WARNING (never the request body, which holds the client secret
        and refresh token, nor any auth header). For the ``refresh_token`` grant
        the failure is raised as :class:`ResideoTokenError` carrying the parsed
        code so callers can tell a dead grant from a transient blip; the
        authorization-code grant (initial setup / reauth) keeps core's default
        handling so the config flow still reports errors the usual way.
        """
        session = async_get_clientsession(self.hass)
        data["client_id"] = self.client_id

        resp = await session.post(
            self.token_url,
            data=data,
            headers={
                "Authorization": encode_basic_auth(self.client_id, self.client_secret),
            },
        )
        if resp.status >= 400:
            error_code, error_description = await self._parse_token_error(resp)
            LOGGER.warning(
                "Resideo token request (%s) failed with HTTP %s: %s%s",
                data.get("grant_type", "unknown"),
                resp.status,
                error_code or "no error code",
                f" ({error_description})" if error_description else "",
            )
            if data.get("grant_type") == "refresh_token":
                raise ResideoTokenError(status=resp.status, error_code=error_code)
            resp.raise_for_status()
        return await resp.json()

    @staticmethod
    async def _parse_token_error(resp: ClientResponse) -> tuple[str | None, str | None]:
        """Extract ``error`` / ``error_description`` from a token error body."""
        try:
            body = await resp.text()
        except (ClientError, TimeoutError):
            return None, None
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            return None, None
        if not isinstance(parsed, dict):
            return None, None
        error = parsed.get("error")
        description = parsed.get("error_description")
        return (
            error if isinstance(error, str) else None,
            description if isinstance(description, str) else None,
        )


class ResideoClient:
    """Authenticated client for the Resideo shutoff-valve API."""

    def __init__(
        self,
        websession: ClientSession,
        oauth_session: ResideoOAuth2Session,
    ) -> None:
        """Initialise the client."""
        self._websession = websession
        self._oauth_session = oauth_session

    @property
    def _apikey(self) -> str:
        """Return the API key (the OAuth client id doubles as the apikey)."""
        return self._oauth_session.implementation.client_id  # type: ignore[attr-defined]

    async def _async_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an authenticated request, refreshing the token once on 401.

        ``async_ensure_token_valid`` is awaited *inside* this method's error
        mapping so a failure at the token endpoint surfaces as a
        ``ResideoAuthError`` / ``ResideoConnectionError`` — never as a raw core
        ``OAuth2TokenRequestReauthError``. That matters because the coordinator
        only ever sees our two error types, and core's ``DataUpdateCoordinator``
        notifies entity listeners for both (so entities go unavailable) whereas
        it silently returns on a leaked ``OAuth2TokenRequestReauthError``,
        leaving entities frozen on stale data.

        Honeywell is also known to reject a stored access token before its
        nominal expiry, so when a request comes back ``401``/``403`` the token is
        force-refreshed (unless another caller already refreshed it) and the
        request is retried exactly once before the failure is surfaced.
        """
        await self._async_ensure_token_valid()

        access_token_before = self._oauth_session.token.get("access_token")
        try:
            return await self._async_send(method, path, **kwargs)
        except ResideoAuthError:
            LOGGER.debug(
                "Access token rejected for %s %s; refreshing once and retrying",
                method,
                path,
            )
            await self._async_refresh_after_rejection(access_token_before)
            return await self._async_send(method, path, **kwargs)

    async def _async_ensure_token_valid(self) -> None:
        """Ensure the token is valid, normalising every failure to our errors."""
        try:
            await self._oauth_session.async_ensure_token_valid()
        except ResideoTokenError as err:
            raise err.as_api_error() from err
        except (ClientError, TimeoutError) as err:
            raise ResideoConnectionError(f"Token request failed: {err}") from err

    async def _async_refresh_after_rejection(
        self, access_token_before: str | None
    ) -> None:
        """Force a single-flight refresh, normalising every failure to our errors."""
        try:
            await self._oauth_session.async_refresh_token_if_unchanged(
                access_token_before or ""
            )
        except ResideoTokenError as err:
            raise err.as_api_error() from err
        except (ClientError, TimeoutError) as err:
            raise ResideoConnectionError(f"Token refresh failed: {err}") from err

    async def _async_send(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a single authenticated request against the API."""
        access_token = self._oauth_session.token["access_token"]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        params: dict[str, Any] = dict(kwargs.pop("params", {}))
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
