"""API client for Nashville Electric Service."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    API_ENDPOINT_CUSTOMER,
    API_ENDPOINT_USAGE,
    B2C_CLIENT_ID,
    B2C_REDIRECT_URI,
    B2C_SCOPE,
    B2C_TOKEN_URL,
    LOGGER,
)


class NESAuthError(Exception):
    """Authentication error."""


class NESConnectionError(Exception):
    """Connection error."""


class NESApiError(Exception):
    """General API error."""


class NESApiClient:
    """Async client for the NES customer portal API."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: datetime | None = None
        self._account_context: dict[str, Any] | None = None
        self._customer_id: str | None = None
        self._token_lock = asyncio.Lock()

    @property
    def customer_id(self) -> str | None:
        """Return the NES customer ID."""
        return self._customer_id

    async def async_authenticate(self) -> None:
        """Authenticate with Azure AD B2C using ROPC flow."""
        data = {
            "grant_type": "password",
            "client_id": B2C_CLIENT_ID,
            "username": self._username,
            "password": self._password,
            "scope": B2C_SCOPE,
            "redirect_uri": B2C_REDIRECT_URI,
        }

        try:
            async with self._session.post(B2C_TOKEN_URL, data=data) as resp:
                if resp.status == 400:
                    error_body = await resp.json()
                    error_desc = error_body.get("error_description", "")
                    LOGGER.debug("Auth error response: %s", error_desc)
                    raise NESAuthError(
                        f"Authentication failed: {error_body.get('error', 'unknown')}"
                    )
                if resp.status != 200:
                    raise NESAuthError(
                        f"Authentication failed with status {resp.status}"
                    )

                result = await resp.json()
                self._access_token = result["access_token"]
                self._refresh_token = result.get("refresh_token")
                expires_in = result.get("expires_in", 3600)
                self._token_expiry = dt_util.utcnow() + timedelta(seconds=expires_in)
                LOGGER.debug("Successfully authenticated with NES")

        except aiohttp.ClientError as err:
            raise NESConnectionError(
                f"Connection error during authentication: {err}"
            ) from err

    async def _async_refresh_token(self) -> None:
        """Refresh the access token."""
        if not self._refresh_token:
            await self.async_authenticate()
            return

        data = {
            "grant_type": "refresh_token",
            "client_id": B2C_CLIENT_ID,
            "refresh_token": self._refresh_token,
            "scope": B2C_SCOPE,
        }

        try:
            async with self._session.post(B2C_TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    LOGGER.debug("Token refresh failed, re-authenticating")
                    self._refresh_token = None
                    await self.async_authenticate()
                    return

                result = await resp.json()
                self._access_token = result["access_token"]
                self._refresh_token = result.get("refresh_token", self._refresh_token)
                expires_in = result.get("expires_in", 3600)
                self._token_expiry = dt_util.utcnow() + timedelta(seconds=expires_in)
                LOGGER.debug("Successfully refreshed token")

        except aiohttp.ClientError:
            LOGGER.debug("Token refresh connection error, re-authenticating")
            self._refresh_token = None
            await self.async_authenticate()

    async def _async_ensure_token(self) -> None:
        """Ensure we have a valid access token."""
        async with self._token_lock:
            if self._access_token is None:
                await self.async_authenticate()
            elif self._token_expiry and dt_util.utcnow() >= self._token_expiry:
                await self._async_refresh_token()

    def _auth_headers(self) -> dict[str, str]:
        """Return authorization headers."""
        if not self._access_token:
            raise NESAuthError("No access token available")
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def async_get_customer(self) -> dict[str, Any]:
        """Fetch customer/account information."""
        await self._async_ensure_token()

        url = f"{API_BASE_URL}{API_ENDPOINT_CUSTOMER}"

        try:
            async with self._session.post(
                url, headers=self._auth_headers(), json={}
            ) as resp:
                if resp.status == 401:
                    # Token may be invalid, try re-auth
                    await self.async_authenticate()
                    async with self._session.post(
                        url, headers=self._auth_headers(), json={}
                    ) as retry_resp:
                        self._verify_response(retry_resp)
                        result = await retry_resp.json()
                else:
                    self._verify_response(resp)
                    result = await resp.json()

            if isinstance(result, list) and result:
                if len(result) > 1:
                    LOGGER.warning(
                        "Multiple NES accounts found, using first: %s",
                        [a.get("customerId") for a in result],
                    )
                account = result[0]
            elif isinstance(result, dict):
                account = result
            else:
                raise NESApiError("Unexpected customer response format")

            self._customer_id = account.get("customerId")
            self._account_context = account.get("accountContext", account)
            return account

        except aiohttp.ClientError as err:
            raise NESConnectionError(
                f"Connection error fetching customer info: {err}"
            ) from err

    async def async_get_usage(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch usage data for a date range."""
        await self._async_ensure_token()

        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        url = f"{API_BASE_URL}{API_ENDPOINT_USAGE}"
        payload = {
            "startDate": start_date.strftime("%m/%d/%Y"),
            "endDate": end_date.strftime("%m/%d/%Y"),
        }

        # Include account context if available
        if self._account_context:
            payload["accountContext"] = self._account_context

        try:
            async with self._session.post(
                url, headers=self._auth_headers(), json=payload
            ) as resp:
                if resp.status == 401:
                    await self.async_authenticate()
                    async with self._session.post(
                        url, headers=self._auth_headers(), json=payload
                    ) as retry_resp:
                        self._verify_response(retry_resp)
                        return await retry_resp.json()

                self._verify_response(resp)
                return await resp.json()

        except aiohttp.ClientError as err:
            raise NESConnectionError(
                f"Connection error fetching usage data: {err}"
            ) from err

    @staticmethod
    def _verify_response(resp: aiohttp.ClientResponse) -> None:
        """Verify the API response status."""
        if resp.status == 401:
            raise NESAuthError("Authentication failed")
        if resp.status == 403:
            raise NESAuthError("Access forbidden")
        if resp.status >= 400:
            raise NESApiError(f"API error: HTTP {resp.status}")
