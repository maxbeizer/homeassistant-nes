"""Tests for the NES API client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import aiohttp
import pytest

from custom_components.nes.api import (
    NESApiClient,
    NESAuthError,
    NESConnectionError,
    NESApiError,
)
from custom_components.nes.const import B2C_TOKEN_URL


def _make_response(
    status: int,
    json_data: dict | list | None = None,
    text: str = "",
    headers: dict | None = None,
) -> MagicMock:
    """Create a mock aiohttp response."""
    resp = MagicMock(spec=aiohttp.ClientResponse)
    resp.status = status
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    resp.text = AsyncMock(return_value=text)
    resp.headers = headers or {}
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
    ctx_managers = []
    for resp in responses:
        ctx_managers.append(_make_ctx(resp))

    session.post = MagicMock(side_effect=ctx_managers)
    session.get = MagicMock(side_effect=[])
    return session


# HTML returned by B2C authorize page with CSRF and transId
B2C_LOGIN_PAGE_HTML = """
<html>
<script>var SETTINGS = {"csrf": "test-csrf-token-123", "transId": "test-trans-id-456"};</script>
</html>
"""


def _make_auth_session_mock(
    login_page_status: int = 200,
    login_page_html: str = B2C_LOGIN_PAGE_HTML,
    self_asserted_status: int = 200,
    self_asserted_text: str = '{"status":"200"}',
    confirmed_status: int = 302,
    confirmed_location: str = "https://myaccount.nespower.com/eportal?code=auth-code-789&state=abc",
    token_status: int = 200,
    token_json: dict | None = None,
) -> MagicMock:
    """Create a mock auth session for the 4-step B2C flow."""
    if token_json is None:
        token_json = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_in": 3600,
        }

    # Step 1: GET /authorize → login page
    authorize_resp = _make_response(login_page_status, text=login_page_html)

    # Step 2: POST /SelfAsserted → credentials
    self_asserted_resp = _make_response(
        self_asserted_status, text=self_asserted_text
    )

    # Step 3: GET /confirmed → redirect with code
    confirmed_resp = _make_response(
        confirmed_status,
        headers={"Location": confirmed_location},
    )

    # Step 4: POST /token → tokens
    token_resp = _make_response(token_status, json_data=token_json)

    mock_session = MagicMock()
    mock_session.get = MagicMock(
        side_effect=[_make_ctx(authorize_resp), _make_ctx(confirmed_resp)]
    )
    mock_session.post = MagicMock(
        side_effect=[_make_ctx(self_asserted_resp), _make_ctx(token_resp)]
    )

    # Make it work as async context manager
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session


class TestAuthentication:
    """Test NES authentication via B2C Authorization Code + PKCE."""

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_successful_auth(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test successful 4-step B2C authentication."""
        mock_auth_session = _make_auth_session_mock()
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("user@example.com", "pass123", session)
        await client.async_authenticate()

        assert client._access_token == "test-access-token"
        assert client._refresh_token == "test-refresh-token"
        assert client._token_expiry is not None

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_auth_invalid_credentials(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test authentication with bad credentials."""
        mock_auth_session = _make_auth_session_mock(
            self_asserted_text='{"status":"FAIL","message":"Invalid credentials"}',
        )
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("bad@example.com", "wrong", session)
        with pytest.raises(NESAuthError, match="Invalid email or password"):
            await client.async_authenticate()

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_auth_login_page_failure(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test authentication when login page returns error."""
        mock_auth_session = _make_auth_session_mock(login_page_status=500)
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESAuthError, match="Failed to start auth flow"):
            await client.async_authenticate()

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_auth_missing_csrf(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test authentication when CSRF token is missing from page."""
        mock_auth_session = _make_auth_session_mock(
            login_page_html="<html>No tokens here</html>"
        )
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESAuthError, match="Failed to extract auth"):
            await client.async_authenticate()

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_auth_no_code_in_redirect(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test authentication when redirect has no auth code."""
        mock_auth_session = _make_auth_session_mock(
            confirmed_location="https://myaccount.nespower.com/eportal?error=access_denied",
        )
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESAuthError, match="Auth error"):
            await client.async_authenticate()

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_auth_token_exchange_failure(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test authentication when token exchange fails."""
        mock_auth_session = _make_auth_session_mock(
            token_status=400,
            token_json={"error": "invalid_grant"},
        )
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESAuthError, match="Token exchange failed"):
            await client.async_authenticate()

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_auth_connection_error(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test authentication with network failure."""
        mock_auth_session = MagicMock()
        mock_auth_session.__aenter__ = AsyncMock(return_value=mock_auth_session)
        mock_auth_session.__aexit__ = AsyncMock(return_value=False)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("Network down")
        )
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_auth_session.get = MagicMock(return_value=ctx)
        mock_session_cls.return_value = mock_auth_session

        session = MagicMock()
        client = NESApiClient("user@example.com", "pass", session)
        with pytest.raises(NESConnectionError, match="Connection error"):
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

    @patch("custom_components.nes.api.aiohttp.CookieJar")
    @patch("custom_components.nes.api.aiohttp.ClientSession")
    async def test_refresh_falls_back_to_reauth(
        self, mock_session_cls: MagicMock, mock_jar: MagicMock
    ) -> None:
        """Test that failed refresh triggers full re-authentication."""
        mock_auth_session = _make_auth_session_mock()
        mock_session_cls.return_value = mock_auth_session

        # Set up main session for the failed refresh
        failed_refresh = _make_response(401)
        session = _make_session(failed_refresh)

        client = NESApiClient("user@example.com", "pass", session)
        client._refresh_token = "expired-refresh"
        await client._async_refresh_token()

        assert client._access_token == "test-access-token"
        assert client._refresh_token == "test-refresh-token"


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
