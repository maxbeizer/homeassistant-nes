"""Tests for the NES API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.nes.api import (
    NESApiClient,
    NESAuthError,
    NESConnectionError,
    NESApiError,
)


def _make_response(
    status: int,
    json_data: dict | list | None = None,
    text: str = "",
    headers: dict | None = None,
) -> MagicMock:
    """Create a mock aiohttp response."""
    import json as json_mod

    resp = MagicMock(spec=aiohttp.ClientResponse)
    resp.status = status
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    if json_data is not None and not text:
        text = json_mod.dumps(json_data)
    resp.text = AsyncMock(return_value=text)
    resp.headers = headers or {}
    resp.raw_headers = []
    resp.url = "https://example.com"
    return resp


def _make_ctx(resp: MagicMock) -> MagicMock:
    """Wrap a response in an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_session(*responses: MagicMock) -> MagicMock:
    """Create a mock aiohttp session that yields responses in order."""
    session = MagicMock()
    ctx_managers = [_make_ctx(r) for r in responses]
    session.post = MagicMock(side_effect=ctx_managers)
    session.get = MagicMock(side_effect=[])
    return session


class TestAuthentication:
    """Test NES OAuth2 password grant authentication."""

    async def test_successful_auth(self) -> None:
        """Test successful authentication."""
        token_resp = _make_response(200, {
            "access_token": "nes-api-token-xyz",
            "refresh_token": "refresh-abc",
            "expires_in": 3600,
        })
        session = _make_session(token_resp)

        client = NESApiClient("user@example.com", "pass123", session)
        await client.async_authenticate()

        assert client._access_token == "nes-api-token-xyz"
        assert client._refresh_token == "refresh-abc"
        assert client._token_expiry is not None

    async def test_auth_invalid_credentials(self) -> None:
        """Test authentication with bad credentials."""
        error_resp = _make_response(400, {
            "error": "invalid_grant",
            "error_description": "Unable to authenticate user",
        })
        session = _make_session(error_resp)

        client = NESApiClient("bad@example.com", "wrong", session)
        with pytest.raises(NESAuthError, match="Authentication failed"):
            await client.async_authenticate()

    async def test_auth_server_error(self) -> None:
        """Test authentication with server error."""
        error_resp = _make_response(500)
        session = _make_session(error_resp)

        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESAuthError, match="HTTP 500"):
            await client.async_authenticate()

    async def test_auth_connection_error(self) -> None:
        """Test authentication with network failure."""
        session = MagicMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("Network down")
        )
        ctx.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=ctx)

        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESConnectionError, match="Connection error"):
            await client.async_authenticate()

    async def test_auth_missing_access_token(self) -> None:
        """Test auth when response is missing access_token."""
        bad_resp = _make_response(200, {"token_type": "bearer"})
        session = _make_session(bad_resp)

        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESAuthError, match="missing access_token"):
            await client.async_authenticate()


class TestTokenRefresh:
    """Test token refresh logic."""

    async def test_refresh_success(self) -> None:
        """Test successful token refresh."""
        refresh_resp = _make_response(200, {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        })
        session = _make_session(refresh_resp)

        client = NESApiClient("user@example.com", "pass", session)
        client._refresh_token = "old-refresh"
        await client._async_refresh_token()

        assert client._access_token == "new-token"
        assert client._refresh_token == "new-refresh"

    async def test_refresh_falls_back_to_reauth(self) -> None:
        """Test that failed refresh triggers full re-authentication."""
        failed_refresh = _make_response(401)
        reauth_resp = _make_response(200, {
            "access_token": "reauth-token",
            "expires_in": 3600,
        })
        session = _make_session(failed_refresh, reauth_resp)

        client = NESApiClient("user@example.com", "pass", session)
        client._refresh_token = "expired-refresh"
        await client._async_refresh_token()

        assert client._access_token == "reauth-token"


class TestCustomerFetch:
    """Test customer info fetching."""

    async def test_get_customer_list_response(self) -> None:
        """Test customer fetch with list response."""
        customer_resp = _make_response(200, [
            {"customerId": "C123", "accountContext": {"acct": "A1"}},
        ])
        session = _make_session(customer_resp)

        client = NESApiClient("user@example.com", "pass", session)
        client._access_token = "valid-token"
        result = await client.async_get_customer()

        assert result["customerId"] == "C123"
        assert client.customer_id == "C123"

    async def test_get_customer_dict_response(self) -> None:
        """Test customer fetch with dict response."""
        customer_resp = _make_response(200, {
            "customerId": "C456",
            "accountContext": {"acct": "A2"},
        })
        session = _make_session(customer_resp)

        client = NESApiClient("user@example.com", "pass", session)
        client._access_token = "valid-token"
        result = await client.async_get_customer()

        assert result["customerId"] == "C456"

    async def test_get_customer_empty_list(self) -> None:
        """Test customer fetch with empty list raises error."""
        empty_resp = _make_response(200, [])
        session = _make_session(empty_resp)

        client = NESApiClient("user@example.com", "pass", session)
        client._access_token = "valid-token"
        with pytest.raises(NESApiError, match="Unexpected customer response"):
            await client.async_get_customer()

    async def test_get_customer_multi_account_warns(self, caplog) -> None:
        """Test that multiple accounts logs a warning."""
        multi_resp = _make_response(200, [
            {"customerId": "C1"},
            {"customerId": "C2"},
        ])
        session = _make_session(multi_resp)

        client = NESApiClient("user@example.com", "pass", session)
        client._access_token = "valid-token"

        with caplog.at_level("WARNING"):
            result = await client.async_get_customer()

        assert result["customerId"] == "C1"
        assert "Multiple NES accounts" in caplog.text


class TestAuthHeaders:
    """Test auth header generation."""

    async def test_auth_headers_with_valid_token(self) -> None:
        """Test headers with a valid token."""
        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)
        client._access_token = "my-token"

        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer my-token"

    async def test_auth_headers_without_token_raises(self) -> None:
        """Test headers raise when no token is available."""
        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)

        with pytest.raises(NESAuthError, match="No access token"):
            client._auth_headers()
