"""Shared fixtures for the Resideo Shutoff Valve tests."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.resideo_shutoff_valve.api import (
    ResideoClient,
    ResideoLocalOAuth2Implementation,
    ResideoOAuth2Session,
)
from custom_components.resideo_shutoff_valve.const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)
from custom_components.resideo_shutoff_valve.coordinator import (
    ResideoDataUpdateCoordinator,
)

pytest_plugins = "pytest_homeassistant_custom_component"

CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"


def make_token(*, access_token: str = "initial-access", expired: bool = False) -> dict:
    """Return an OAuth token dict, optionally already past its expiry."""
    return {
        "access_token": access_token,
        "refresh_token": "initial-refresh",
        "expires_in": 3600,
        "expires_at": time.time() + (-10 if expired else 3600),
    }


@pytest.fixture
async def integration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    """Build a wired-up coordinator/client/session against a mock config entry.

    Everything is constructed directly (rather than via ``async_setup_entry``)
    so tests can drive refreshes and concurrency precisely. ``async_start_reauth``
    is replaced with a ``Mock`` so a refresh never spins up a real config flow;
    tests assert against that mock to check reauth was (or was not) triggered.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={"auth_implementation": "resideo", "token": make_token()},
    )
    entry.add_to_hass(hass)

    reauth = Mock()
    monkeypatch.setattr(entry, "async_start_reauth_if_available", reauth)

    implementation = ResideoLocalOAuth2Implementation(
        hass,
        "resideo",
        ClientCredential(CLIENT_ID, CLIENT_SECRET),
        AuthorizationServer(authorize_url=OAUTH2_AUTHORIZE, token_url=OAUTH2_TOKEN),
    )
    session = ResideoOAuth2Session(hass, entry, implementation)
    client = ResideoClient(async_get_clientsession(hass), session)
    coordinator = ResideoDataUpdateCoordinator(hass, entry, client)

    return SimpleNamespace(
        hass=hass,
        entry=entry,
        implementation=implementation,
        session=session,
        client=client,
        coordinator=coordinator,
        reauth=reauth,
    )
