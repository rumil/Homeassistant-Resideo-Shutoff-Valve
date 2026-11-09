"""Tests for the Resideo auth-failure / token-refresh behaviour.

These cover the incident this integration was hardened against: an auth failure
at the token endpoint used to leave every entity frozen on stale data because
the error escaped as a raw core ``OAuth2TokenRequestReauthError`` (which the
``DataUpdateCoordinator`` handles by returning without notifying listeners).
"""

from __future__ import annotations

import asyncio
import time

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.resideo_shutoff_valve.api import (
    ResideoAuthError,
    ResideoTokenError,
)
from custom_components.resideo_shutoff_valve.binary_sensor import (
    BINARY_SENSORS,
    ResideoBinarySensor,
)
from custom_components.resideo_shutoff_valve.const import (
    API_BASE,
    OAUTH2_TOKEN,
)

LOCATION_ID = "1234567"
DEVICE_ID = "8550114"

LOCATIONS = [
    {
        "locationID": LOCATION_ID,
        "devices": [{"deviceClass": "ShutoffValve", "deviceID": DEVICE_ID}],
    }
]
VALVE_DETAIL = {
    "deviceID": DEVICE_ID,
    "userDefinedDeviceName": "Cold Water Valve",
    "isAlive": True,
    "actuatorValve": {"valveStatus": "Open", "leakStatus": "ok"},
}
TOKEN_URL = OAUTH2_TOKEN
LOCATIONS_URL = f"{API_BASE}/locations"
VALVE_URL = f"{API_BASE}/devices/shutoffvalve/{DEVICE_ID}"

CONNECTIVITY_DESCRIPTION = next(d for d in BINARY_SENSORS if d.key == "connectivity")


def _mock_api_ok(aioclient_mock: AiohttpClientMocker) -> None:
    """Register successful locations + valve responses."""
    json_headers = {"Content-Type": "application/json"}
    aioclient_mock.get(LOCATIONS_URL, json=LOCATIONS, headers=json_headers)
    aioclient_mock.get(VALVE_URL, json=VALVE_DETAIL, headers=json_headers)


def _mock_token_ok(
    aioclient_mock: AiohttpClientMocker, *, access_token: str = "refreshed-access"
) -> None:
    """Register a successful token refresh response."""
    aioclient_mock.post(
        TOKEN_URL,
        json={
            "access_token": access_token,
            "refresh_token": "rotated-refresh",
            "expires_in": 3600,
        },
    )


def _expire_token(ns) -> None:
    """Mark the stored access token as expired so the next request refreshes."""
    ns.hass.config_entries.async_update_entry(
        ns.entry,
        data={
            **ns.entry.data,
            "token": {**ns.entry.data["token"], "expires_at": time.time() - 10},
        },
    )


async def test_auth_failure_marks_entities_unavailable_same_refresh(
    integration, aioclient_mock: AiohttpClientMocker
) -> None:
    """A dead-grant auth failure must make entities unavailable on that refresh.

    Reproduces the incident: previously the entities kept their last values
    (connectivity ``on``) after the token endpoint returned 400 until a manual
    reload. They must now go unavailable on the same refresh and stay so.
    """
    coordinator = integration.coordinator

    # First refresh succeeds and populates data (token still valid, no refresh).
    _mock_api_ok(aioclient_mock)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    entity = ResideoBinarySensor(coordinator, DEVICE_ID, CONNECTIVITY_DESCRIPTION)
    assert entity.available is True

    # A listener stands in for a real entity: it must be notified so the entity
    # actually re-renders as unavailable (the crux of the original bug).
    notified = 0

    def _listener() -> None:
        nonlocal notified
        notified += 1

    coordinator.async_add_listener(_listener)

    # Now the token is expired and the token endpoint rejects the grant.
    aioclient_mock.clear_requests()
    _expire_token(integration)
    aioclient_mock.post(TOKEN_URL, status=400, json={"error": "invalid_grant"})
    _mock_api_ok(aioclient_mock)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)
    assert notified >= 1
    assert entity.available is False
    assert integration.reauth.called

    # It stays unavailable on later checks (no silent revert to stale data).
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert entity.available is False


async def test_concurrent_401s_trigger_single_token_request(
    integration, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests that 401 at once must share one refresh, not race it."""
    client = integration.client
    session = integration.session

    token_requests = 0

    async def fake_token_request(data: dict) -> dict:
        nonlocal token_requests
        if data.get("grant_type") == "refresh_token":
            token_requests += 1
        return {
            "access_token": "rotated-access",
            "refresh_token": "rotated-refresh",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        integration.implementation, "_token_request", fake_token_request
    )

    async def fake_send(method: str, path: str, **kwargs):
        # Yield so both callers capture the pre-refresh token before either
        # refreshes, i.e. a genuine concurrent 401.
        await asyncio.sleep(0)
        if session.token["access_token"] == "initial-access":
            raise ResideoAuthError("API rejected the access token: 401")
        return VALVE_DETAIL

    monkeypatch.setattr(client, "_async_send", fake_send)

    results = await asyncio.gather(
        client.async_get_valve(LOCATION_ID, DEVICE_ID),
        client.async_get_valve(LOCATION_ID, DEVICE_ID),
    )

    assert results == [VALVE_DETAIL, VALVE_DETAIL]
    assert token_requests == 1
    assert session.token["access_token"] == "rotated-access"


async def test_transient_token_error_is_update_failed_and_retries(
    integration, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-dead-grant token error must be transient: UpdateFailed, keep polling."""
    coordinator = integration.coordinator

    _mock_api_ok(aioclient_mock)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    # Transient 400 (no invalid_grant/invalid_client code).
    aioclient_mock.clear_requests()
    _expire_token(integration)
    aioclient_mock.post(
        TOKEN_URL, status=400, json={"error": "temporarily_unavailable"}
    )
    _mock_api_ok(aioclient_mock)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert not integration.reauth.called

    # The next refresh recovers once the endpoint is healthy again.
    aioclient_mock.clear_requests()
    _mock_token_ok(aioclient_mock)
    _mock_api_ok(aioclient_mock)

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert not integration.reauth.called


async def test_invalid_grant_escalates_to_reauth(
    integration, aioclient_mock: AiohttpClientMocker
) -> None:
    """A dead refresh token (invalid_grant) must escalate to reauth immediately."""
    coordinator = integration.coordinator

    _mock_api_ok(aioclient_mock)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    aioclient_mock.clear_requests()
    _expire_token(integration)
    aioclient_mock.post(TOKEN_URL, status=400, json={"error": "invalid_grant"})
    _mock_api_ok(aioclient_mock)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)
    assert integration.reauth.called


async def test_persistent_transient_failure_escalates_after_timeout(
    integration, aioclient_mock: AiohttpClientMocker
) -> None:
    """A transient failure that persists ~15 min must finally escalate to reauth."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    coordinator = integration.coordinator

    _mock_api_ok(aioclient_mock)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    aioclient_mock.clear_requests()
    _expire_token(integration)
    aioclient_mock.post(TOKEN_URL, status=503, json={"error": "server_error"})
    _mock_api_ok(aioclient_mock)

    # First transient failure: UpdateFailed, no reauth yet.
    await coordinator.async_refresh()
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert not integration.reauth.called
    assert coordinator._transient_failure_since is not None

    # Simulate that the transient failures began more than 15 minutes ago.
    coordinator._transient_failure_since = dt_util.utcnow() - timedelta(minutes=16)

    await coordinator.async_refresh()
    assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)
    assert integration.reauth.called


async def test_token_request_classifies_errors(
    integration, aioclient_mock: AiohttpClientMocker
) -> None:
    """``_token_request`` parses the body and classifies dead vs transient grants."""
    implementation = integration.implementation
    token = {
        "access_token": "a",
        "refresh_token": "r",
        "expires_in": 3600,
        "expires_at": 0,
    }

    aioclient_mock.post(TOKEN_URL, status=400, json={"error": "invalid_grant"})
    with pytest.raises(ResideoTokenError) as dead:
        await implementation.async_refresh_token(token)
    assert dead.value.is_permanent is True
    assert dead.value.error_code == "invalid_grant"

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        TOKEN_URL, status=400, json={"error": "temporarily_unavailable"}
    )
    with pytest.raises(ResideoTokenError) as transient:
        await implementation.async_refresh_token(token)
    assert transient.value.is_permanent is False
    assert transient.value.error_code == "temporarily_unavailable"
