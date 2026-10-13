"""Tests for the Endurain config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_API_KEY,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.endurain.const import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_MFA_CODE,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

from .conftest import API, PROFILE, UNIQUE_ID, URL, mock_data_endpoints, token_payload


async def _start(hass: HomeAssistant, method: str) -> str:
    """Start a flow, submit the URL and choose an auth method. Return the flow id."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{URL}/", CONF_VERIFY_SSL: True}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": method})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == method
    return result["flow_id"]


async def test_api_key_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A valid API key creates an entry keyed by instance and user id."""
    mock_data_endpoints(aioclient_mock)
    flow_id = await _start(hass, "api_key")

    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_API_KEY: " endurain_secret "})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jane Runner"
    assert result["result"].unique_id == UNIQUE_ID
    assert result["data"] == {
        CONF_URL: URL,
        CONF_VERIFY_SSL: True,
        CONF_AUTH_TYPE: AUTH_TYPE_API_KEY,
        CONF_API_KEY: "endurain_secret",
    }


async def test_api_key_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """API key failures are reported distinctly and the flow can recover."""
    flow_id = await _start(hass, "api_key")

    cases = [
        (401, {"detail": "Invalid API key"}, "invalid_api_key"),
        (401, {"detail": "Not authenticated"}, "api_key_unsupported"),
        (403, {"detail": "Missing permissions"}, "api_key_missing_scope"),
        (503, {"detail": "down"}, "cannot_connect"),
    ]
    for status, body, error in cases:
        aioclient_mock.clear_requests()
        aioclient_mock.get(f"{API}/profile", status=status, json=body)
        result = await hass.config_entries.flow.async_configure(flow_id, {CONF_API_KEY: "k"})
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": error}, status

    aioclient_mock.clear_requests()
    mock_data_endpoints(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_API_KEY: "k"})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_credentials_flow_does_not_store_password(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Username/password login stores only the refresh token."""
    aioclient_mock.post(f"{API}/auth/login", json=token_payload("refresh-1"))
    mock_data_endpoints(aioclient_mock)
    flow_id = await _start(hass, "credentials")

    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_USERNAME: "jane", CONF_PASSWORD: "pw"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_URL: URL,
        CONF_VERIFY_SSL: True,
        CONF_AUTH_TYPE: AUTH_TYPE_PASSWORD,
        CONF_USERNAME: "jane",
        CONF_REFRESH_TOKEN: "refresh-1",
    }
    login_call = aioclient_mock.mock_calls[0]
    assert login_call[3]["X-Client-Type"] == "mobile"


async def test_credentials_invalid(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Wrong credentials show an error."""
    aioclient_mock.post(f"{API}/auth/login", status=401, json={"detail": "Incorrect username or password"})
    flow_id = await _start(hass, "credentials")
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_USERNAME: "jane", CONF_PASSWORD: "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_credentials_with_mfa(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """MFA-enabled accounts get a second step for the code."""
    aioclient_mock.post(f"{API}/auth/login", json={"mfa_required": True, "username": "jane", "message": "MFA"})
    flow_id = await _start(hass, "credentials")
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_USERNAME: "jane", CONF_PASSWORD: "pw"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"

    aioclient_mock.post(f"{API}/auth/mfa/verify", status=401, json={"detail": "Invalid MFA code"})
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_MFA_CODE: "000000"})
    assert result["errors"] == {"base": "invalid_mfa_code"}

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{API}/auth/mfa/verify", json=token_payload("refresh-mfa"))
    mock_data_endpoints(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_MFA_CODE: "123456"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REFRESH_TOKEN] == "refresh-mfa"


async def test_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """The same user on the same instance cannot be added twice."""
    api_key_entry.add_to_hass(hass)
    mock_data_endpoints(aioclient_mock)
    flow_id = await _start(hass, "api_key")
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_API_KEY: "k"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_switches_to_api_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, password_entry: MockConfigEntry
) -> None:
    """Re-authentication can replace a session with an API key."""
    password_entry.add_to_hass(hass)
    mock_data_endpoints(aioclient_mock)

    result = await password_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "api_key"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "new_key"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert password_entry.data[CONF_AUTH_TYPE] == AUTH_TYPE_API_KEY
    assert password_entry.data[CONF_API_KEY] == "new_key"
    assert CONF_REFRESH_TOKEN not in password_entry.data


async def test_reauth_wrong_account(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """Re-authenticating as another user is rejected."""
    api_key_entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/profile", json={**PROFILE, "id": 99})

    result = await api_key_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "api_key"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "other"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
