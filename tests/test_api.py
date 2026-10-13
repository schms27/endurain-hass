"""Tests for the Endurain API client."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.endurain.api import (
    EndurainAuthError,
    EndurainClient,
    EndurainConnectionError,
    EndurainForbiddenError,
    EndurainMfaRequiredError,
    EndurainRateLimitError,
    normalize_url,
)

from .conftest import API, PROFILE, URL, token_payload


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://endurain.test", "https://endurain.test"),
        ("https://endurain.test/", "https://endurain.test"),
        (" https://endurain.test/api/v1/ ", "https://endurain.test"),
        ("http://10.0.0.5:8080/endurain", "http://10.0.0.5:8080/endurain"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    """URLs are reduced to the instance base URL."""
    assert normalize_url(raw) == expected


async def test_api_key_header(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """API-key mode sends the key and no bearer token."""
    aioclient_mock.get(f"{API}/profile", json=PROFILE)
    client = EndurainClient(async_get_clientsession(hass), URL, api_key="endurain_secret")

    assert await client.async_get_profile() == PROFILE
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["X-API-Key"] == "endurain_secret"
    assert "Authorization" not in headers


async def test_refresh_rotates_and_persists_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The first request refreshes the session and reports the rotated token."""
    aioclient_mock.post(f"{API}/auth/refresh", json=token_payload("refresh-2"))
    aioclient_mock.get(f"{API}/profile", json=PROFILE)
    rotated: list[str] = []
    client = EndurainClient(
        async_get_clientsession(hass),
        URL,
        refresh_token="refresh-1",
        on_refresh_token=rotated.append,
    )

    await client.async_get_profile()
    await client.async_get_profile()

    assert rotated == ["refresh-2"]
    assert client.refresh_token == "refresh-2"
    # Only one refresh: the access token is reused for the second call.
    assert aioclient_mock.call_count == 3
    refresh_call, profile_call = aioclient_mock.mock_calls[0], aioclient_mock.mock_calls[1]
    assert refresh_call[3]["Authorization"] == "Bearer refresh-1"
    assert refresh_call[3]["X-Client-Type"] == "mobile"
    assert profile_call[3]["Authorization"] == "Bearer access-1"


async def test_retry_after_401_with_fresh_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A 401 on a data call triggers one forced refresh and a retry."""
    client = EndurainClient(async_get_clientsession(hass), URL, refresh_token="refresh-1")
    aioclient_mock.post(f"{API}/auth/refresh", json=token_payload("refresh-2", "access-1"))
    aioclient_mock.get(f"{API}/profile", status=401, json={"detail": "Session revoked"})
    with pytest.raises(EndurainAuthError):
        # Both attempts hit the same mocked 401, so the retry fails too.
        await client.async_get_profile()
    assert [call[0] for call in aioclient_mock.mock_calls] == ["POST", "GET", "POST", "GET"]


async def test_invalid_refresh_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """An expired refresh token surfaces as an auth error."""
    aioclient_mock.post(f"{API}/auth/refresh", status=401, json={"detail": "Invalid refresh token"})
    client = EndurainClient(async_get_clientsession(hass), URL, refresh_token="stale")
    with pytest.raises(EndurainAuthError):
        await client.async_get_profile()


async def test_login_mfa_required(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A login answered with mfa_required raises the dedicated error."""
    aioclient_mock.post(
        f"{API}/auth/login",
        json={"mfa_required": True, "username": "jane", "message": "MFA verification required"},
    )
    client = EndurainClient(async_get_clientsession(hass), URL)
    with pytest.raises(EndurainMfaRequiredError):
        await client.async_login("jane", "pw")
    assert client.refresh_token is None


async def test_login_and_mfa_verify(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Verifying MFA stores the issued tokens."""
    aioclient_mock.post(f"{API}/auth/mfa/verify", json=token_payload("refresh-mfa"))
    client = EndurainClient(async_get_clientsession(hass), URL)
    await client.async_verify_mfa("jane", " 123456 ")
    assert client.refresh_token == "refresh-mfa"
    assert aioclient_mock.mock_calls[0][2] == {"username": "jane", "mfa_code": "123456"}


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (403, EndurainForbiddenError),
        (429, EndurainRateLimitError),
        (502, EndurainConnectionError),
    ],
)
async def test_status_mapping(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    error: type[Exception],
) -> None:
    """HTTP errors map to client exceptions."""
    aioclient_mock.get(f"{API}/profile", status=status, json={"detail": "nope"})
    client = EndurainClient(async_get_clientsession(hass), URL, api_key="k")
    with pytest.raises(error):
        await client.async_get_profile()


async def test_connection_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Network failures map to EndurainConnectionError."""
    aioclient_mock.get(f"{API}/profile", exc=TimeoutError)
    client = EndurainClient(async_get_clientsession(hass), URL, api_key="k")
    with pytest.raises(EndurainConnectionError):
        await client.async_get_profile()


@pytest.mark.parametrize(
    ("detail", "is_key_rejection"),
    [("Invalid API key", True), ("API key has expired", True), ("Not authenticated", False)],
)
def test_api_key_rejection_detection(detail: str, is_key_rejection: bool) -> None:
    """Only explicit API key rejections count as an invalid key."""
    assert EndurainAuthError("x", detail).is_api_key_rejection is is_key_rejection
