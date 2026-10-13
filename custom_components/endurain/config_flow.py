"""Config flow for the Endurain integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_API_KEY,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import (
    EndurainAuthError,
    EndurainClient,
    EndurainConnectionError,
    EndurainError,
    EndurainForbiddenError,
    EndurainMfaRequiredError,
    EndurainRateLimitError,
    normalize_url,
)
from .const import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_MFA_CODE,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
    }
)
STEP_API_KEY_SCHEMA = vol.Schema(
    {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)
STEP_MFA_SCHEMA = vol.Schema({vol.Required(CONF_MFA_CODE): str})


def _credentials_schema(username: str | None = None) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=username or vol.UNDEFINED): str,
            vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }
    )


class EndurainConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Endurain."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._url: str = ""
        self._verify_ssl = True
        self._username: str | None = None
        self._client: EndurainClient | None = None

    def _new_client(self, **kwargs: Any) -> EndurainClient:
        session = async_get_clientsession(self.hass, verify_ssl=self._verify_ssl)
        return EndurainClient(session, self._url, **kwargs)

    # ------------------------------------------------------------------
    # Initial setup
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the instance URL, then for the authentication method."""
        if user_input is not None:
            self._url = normalize_url(user_input[CONF_URL])
            self._verify_ssl = user_input[CONF_VERIFY_SSL]
            return await self.async_step_auth_method()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

    async def async_step_auth_method(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user choose between API key and username/password."""
        return self.async_show_menu(step_id="auth_method", menu_options=["api_key", "credentials"])

    async def async_step_api_key(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Authenticate with an API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = self._new_client(api_key=user_input[CONF_API_KEY].strip())
            try:
                return await self._async_finish(
                    client,
                    {CONF_AUTH_TYPE: AUTH_TYPE_API_KEY, CONF_API_KEY: user_input[CONF_API_KEY].strip()},
                )
            except EndurainAuthError as err:
                errors["base"] = "invalid_api_key" if err.is_api_key_rejection else "api_key_unsupported"
            except EndurainForbiddenError:
                errors["base"] = "api_key_missing_scope"
            except EndurainConnectionError:
                errors["base"] = "cannot_connect"
            except EndurainError:
                _LOGGER.exception("Unexpected error validating Endurain API key")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="api_key",
            data_schema=STEP_API_KEY_SCHEMA,
            errors=errors,
            description_placeholders={"url": self._url},
        )

    async def async_step_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Authenticate with username and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._client = self._new_client()
            try:
                await self._client.async_login(self._username, user_input[CONF_PASSWORD])
                return await self._async_finish_session()
            except EndurainMfaRequiredError:
                return await self.async_step_mfa()
            except EndurainAuthError:
                errors["base"] = "invalid_auth"
            except EndurainRateLimitError:
                errors["base"] = "rate_limited"
            except EndurainConnectionError:
                errors["base"] = "cannot_connect"
            except EndurainError:
                _LOGGER.exception("Unexpected error logging in to Endurain")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(self._username),
            errors=errors,
            description_placeholders={"url": self._url},
        )

    async def async_step_mfa(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the MFA code of an MFA-enabled account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._client is not None and self._username is not None
            try:
                await self._client.async_verify_mfa(self._username, user_input[CONF_MFA_CODE])
                return await self._async_finish_session()
            except EndurainAuthError:
                errors["base"] = "invalid_mfa_code"
            except EndurainRateLimitError:
                errors["base"] = "rate_limited"
            except EndurainConnectionError:
                errors["base"] = "cannot_connect"
            except EndurainError:
                # Endurain answers a malformed code with a validation error.
                errors["base"] = "invalid_mfa_code"

        return self.async_show_form(step_id="mfa", data_schema=STEP_MFA_SCHEMA, errors=errors)

    async def _async_finish_session(self) -> ConfigFlowResult:
        assert self._client is not None and self._client.refresh_token is not None
        return await self._async_finish(
            self._client,
            {
                CONF_AUTH_TYPE: AUTH_TYPE_PASSWORD,
                CONF_USERNAME: self._username,
                CONF_REFRESH_TOKEN: self._client.refresh_token,
            },
        )

    async def _async_finish(self, client: EndurainClient, auth_data: dict[str, Any]) -> ConfigFlowResult:
        """Validate access by reading the profile, then create or update the entry."""
        profile = await client.async_get_profile()
        # The refresh token may have rotated while fetching the profile.
        if CONF_REFRESH_TOKEN in auth_data:
            auth_data[CONF_REFRESH_TOKEN] = client.refresh_token

        await self.async_set_unique_id(f"{self._url}#{profile['id']}")
        data = {CONF_URL: self._url, CONF_VERIFY_SSL: self._verify_ssl, **auth_data}

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)

        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=profile.get("name") or profile.get("username") or "Endurain", data=data)

    # ------------------------------------------------------------------
    # Re-authentication
    # ------------------------------------------------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after credentials stopped working."""
        self._url = entry_data[CONF_URL]
        self._verify_ssl = entry_data.get(CONF_VERIFY_SSL, True)
        self._username = entry_data.get(CONF_USERNAME)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user pick how to authenticate again."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", description_placeholders={"url": self._url})
        return await self.async_step_auth_method()
