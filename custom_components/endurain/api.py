"""Async client for the Endurain REST API.

Supports two authentication modes:

* **API key** - sent as ``X-API-Key``. Stateless; requires an Endurain
  server whose API keys can be granted read scopes.
* **Session tokens** - obtained by logging in as a ``mobile`` client.
  Only the refresh token is persisted. Endurain rotates refresh tokens on
  every use, so each new one is handed to ``on_refresh_token`` and must be
  stored by the caller, otherwise the next restart cannot authenticate.

The module has no Home Assistant dependencies.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import time
from typing import Any

import aiohttp

API_PREFIX = "/api/v1"
CLIENT_TYPE = "mobile"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# Refresh the access token this many seconds before it expires.
TOKEN_REFRESH_MARGIN = 60


class EndurainError(Exception):
    """Base error for the Endurain client."""


class EndurainConnectionError(EndurainError):
    """The server could not be reached or answered with a server error."""


class EndurainAuthError(EndurainError):
    """Credentials were rejected; the user has to authenticate again."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        """Store the server-provided detail next to the message."""
        super().__init__(message)
        self.detail = detail or ""

    @property
    def is_api_key_rejection(self) -> bool:
        """Return True if the server explicitly rejected the API key itself.

        Endurain answers an unknown, revoked or expired key with a detail
        mentioning the key. Any other 401 on an API-key request means the
        endpoint does not accept API keys at all (older servers).
        """
        return "api key" in self.detail.lower()


class EndurainMfaRequiredError(EndurainError):
    """The password was accepted but an MFA code is required."""


class EndurainForbiddenError(EndurainError):
    """The credential lacks the scope required by an endpoint."""


class EndurainRateLimitError(EndurainError):
    """The server rejected the request because of rate limiting or lockout."""


def normalize_url(url: str) -> str:
    """Return the instance base URL without trailing slash or API prefix."""
    url = url.strip().rstrip("/")
    if url.endswith(API_PREFIX):
        url = url[: -len(API_PREFIX)]
    return url


class EndurainClient:
    """Minimal async client for the endpoints this integration needs."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        api_key: str | None = None,
        refresh_token: str | None = None,
        on_refresh_token: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            session: Shared aiohttp session.
            url: Instance base URL, e.g. ``https://endurain.example.com``.
            api_key: API key for API-key mode.
            refresh_token: Persisted refresh token for session mode.
            on_refresh_token: Called with every newly issued refresh token.
        """
        self._session = session
        self.base_url = normalize_url(url)
        self._api_key = api_key
        self._refresh_token = refresh_token
        self._on_refresh_token = on_refresh_token
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def refresh_token(self) -> str | None:
        """Return the current refresh token."""
        return self._refresh_token

    # ------------------------------------------------------------------
    # Login (session mode)
    # ------------------------------------------------------------------

    async def async_login(self, username: str, password: str) -> None:
        """Log in with username and password.

        Raises:
            EndurainMfaRequiredError: MFA is enabled; call
                :meth:`async_verify_mfa` next.
            EndurainAuthError: Invalid credentials.
        """
        payload = await self._async_auth_request(
            "/auth/login",
            data={"username": username, "password": password},
        )
        if payload.get("mfa_required"):
            raise EndurainMfaRequiredError("MFA verification required")
        self._store_tokens(payload)

    async def async_verify_mfa(self, username: str, code: str) -> None:
        """Complete a login that requires MFA.

        Raises:
            EndurainAuthError: Invalid or expired MFA code.
        """
        payload = await self._async_auth_request(
            "/auth/mfa/verify",
            json={"username": username, "mfa_code": code.strip()},
        )
        self._store_tokens(payload)

    # ------------------------------------------------------------------
    # Data endpoints
    # ------------------------------------------------------------------

    async def async_get_profile(self) -> dict[str, Any]:
        """Return the authenticated user's profile."""
        return await self._async_get("/profile")

    async def async_get_summary(self, period: str) -> dict[str, Any]:
        """Return the activity summary for ``week``, ``month``, ``year`` or ``lifetime``."""
        return await self._async_get(f"/activities_summaries/{period}")

    async def async_get_latest_activity(self, user_id: int) -> dict[str, Any] | None:
        """Return the most recent activity of a user, or None."""
        activities = await self._async_get(f"/activities/user/{user_id}/page_number/1/num_records/1")
        return activities[0] if activities else None

    async def async_get_latest_health_record(self, kind: str) -> dict[str, Any] | None:
        """Return the newest ``steps``, ``weight`` or ``sleep`` record, or None."""
        payload = await self._async_get(
            f"/health/{kind}",
            params={"page_number": 1, "num_records": 1},
        )
        records = (payload or {}).get("records") or []
        return records[0] if records else None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{API_PREFIX}{path}"

    def _store_tokens(self, payload: dict[str, Any]) -> None:
        try:
            self._access_token = payload["access_token"]
            refresh_token = payload["refresh_token"]
            expires_in = int(payload["expires_in"])
        except (KeyError, TypeError, ValueError) as err:
            raise EndurainError(f"Unexpected token response: {err}") from err
        self._access_token_expires_at = time.monotonic() + expires_in
        if refresh_token != self._refresh_token:
            self._refresh_token = refresh_token
            if self._on_refresh_token is not None:
                self._on_refresh_token(refresh_token)

    async def _async_auth_request(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        json: dict[str, str] | None = None,
        bearer: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-Client-Type": CLIENT_TYPE}
        if bearer is not None:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            async with self._session.post(
                self._url(path),
                data=data,
                json=json,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                await self._async_raise_for_status(resp)
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EndurainConnectionError(f"Error talking to Endurain: {err}") from err

    async def _async_ensure_access_token(self, *, force: bool = False) -> str:
        async with self._token_lock:
            if (
                not force
                and self._access_token is not None
                and time.monotonic() < self._access_token_expires_at - TOKEN_REFRESH_MARGIN
            ):
                return self._access_token
            if self._refresh_token is None:
                raise EndurainAuthError("No refresh token available")
            payload = await self._async_auth_request("/auth/refresh", bearer=self._refresh_token)
            self._store_tokens(payload)
            assert self._access_token is not None
            return self._access_token

    async def _async_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self._api_key is not None:
            return await self._async_get_once(path, params, {"X-API-Key": self._api_key})

        token = await self._async_ensure_access_token()
        try:
            return await self._async_get_once(path, params, self._bearer_headers(token))
        except EndurainAuthError:
            # The access token may have been invalidated server-side
            # (e.g. session revoked); refresh once and retry.
            token = await self._async_ensure_access_token(force=True)
            return await self._async_get_once(path, params, self._bearer_headers(token))

    @staticmethod
    def _bearer_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "X-Client-Type": CLIENT_TYPE}

    async def _async_get_once(
        self,
        path: str,
        params: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> Any:
        try:
            async with self._session.get(
                self._url(path),
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                await self._async_raise_for_status(resp)
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EndurainConnectionError(f"Error talking to Endurain: {err}") from err

    @staticmethod
    async def _async_raise_for_status(resp: aiohttp.ClientResponse) -> None:
        if resp.status < 400:
            return
        detail = ""
        try:
            body = await resp.json(content_type=None)
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
        except (aiohttp.ClientError, ValueError):
            pass
        if resp.status == 401:
            raise EndurainAuthError(f"Authentication failed: {detail}", detail)
        if resp.status == 403:
            raise EndurainForbiddenError(f"Access denied: {detail}")
        if resp.status == 429:
            raise EndurainRateLimitError(f"Rate limited: {detail}")
        if resp.status >= 500:
            raise EndurainConnectionError(f"Server error {resp.status}: {detail}")
        raise EndurainError(f"Unexpected response {resp.status}: {detail}")
