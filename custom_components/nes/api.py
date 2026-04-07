"""API client for Nashville Electric Service."""

from __future__ import annotations

import asyncio
import hashlib
import base64
import os
import re
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs, quote

import aiohttp
from yarl import URL

from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    API_ENDPOINT_CUSTOMER,
    API_ENDPOINT_USAGE,
    B2C_AUTHORIZE_URL,
    B2C_CLIENT_ID,
    B2C_CONFIRMED_URL,
    B2C_REDIRECT_URI,
    B2C_SCOPE,
    B2C_SELF_ASSERTED_URL,
    B2C_TOKEN_URL,
    LOGGER,
)


class NESAuthError(Exception):
    """Authentication error."""


def _urlencode(value: str) -> str:
    """URL-encode a string for form data."""
    return quote(value, safe="")


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

    @staticmethod
    def _generate_pkce() -> tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        return code_verifier, code_challenge

    async def async_authenticate(self) -> None:
        """Authenticate with Azure AD B2C using Authorization Code + PKCE.

        Simulates the browser-based B2C login flow:
        1. GET /authorize -> get CSRF token and session cookies
        2. POST /SelfAsserted -> submit username/password
        3. GET /confirmed -> get authorization code via redirect
        4. POST /token -> exchange code for tokens

        Note: cookies are managed manually because aiohttp quotes cookie
        values containing +/=/; characters, which B2C cannot parse.
        """
        code_verifier, code_challenge = self._generate_pkce()
        state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
        nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()

        try:
            # Use DummyCookieJar — we manage cookies manually because
            # aiohttp quotes values with +/= chars, breaking B2C.
            async with aiohttp.ClientSession(
                cookie_jar=aiohttp.DummyCookieJar()
            ) as auth_session:
                # Step 1: Start the authorization flow
                auth_params = {
                    "client_id": B2C_CLIENT_ID,
                    "redirect_uri": B2C_REDIRECT_URI,
                    "response_type": "code",
                    "scope": B2C_SCOPE,
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                    "response_mode": "query",
                }

                async with auth_session.get(
                    B2C_AUTHORIZE_URL,
                    params=auth_params,
                ) as resp:
                    if resp.status != 200:
                        raise NESAuthError(
                            f"Failed to start auth flow: HTTP {resp.status}"
                        )

                    page_html = await resp.text()

                    # Capture raw Set-Cookie values (unquoted)
                    raw_cookies: dict[str, str] = {}
                    for hdr_key, hdr_val in resp.raw_headers:
                        if hdr_key.lower() == b"set-cookie":
                            cookie_str = hdr_val.decode()
                            cname = cookie_str.split("=", 1)[0]
                            cval = cookie_str.split("=", 1)[1].split(";")[0]
                            raw_cookies[cname] = cval

                    # Extract CSRF token and transaction ID
                    csrf_match = re.search(
                        r'"csrf"\s*:\s*"([^"]+)"', page_html
                    )
                    trans_match = re.search(
                        r'"transId"\s*:\s*"([^"]+)"', page_html
                    )

                    if not csrf_match or not trans_match:
                        LOGGER.warning(
                            "Could not find CSRF/transId. "
                            "Page length: %d, URL: %s",
                            len(page_html), str(resp.url),
                        )
                        raise NESAuthError(
                            "Failed to extract auth parameters from login page"
                        )

                    csrf_token = csrf_match.group(1)
                    trans_id = trans_match.group(1)

                LOGGER.warning(
                    "Step 1 complete: got CSRF token (%d chars) and transId",
                    len(csrf_token),
                )

                # Build Cookie header manually (no quoting)
                cookie_header = "; ".join(
                    f"{k}={v}" for k, v in raw_cookies.items()
                )

                # Step 2: Submit credentials to SelfAsserted endpoint
                sa_url = (
                    f"{B2C_SELF_ASSERTED_URL}"
                    f"?tx={trans_id}&p=B2C_1A_NES_SignUpOrSignIn"
                )
                login_data = (
                    f"request_type=RESPONSE"
                    f"&signInName={_urlencode(self._username)}"
                    f"&password={_urlencode(self._password)}"
                )
                headers = {
                    "X-CSRF-TOKEN": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type":
                        "application/x-www-form-urlencoded; charset=UTF-8",
                    "Cookie": cookie_header,
                }

                async with auth_session.post(
                    URL(sa_url, encoded=True),
                    data=login_data,
                    headers=headers,
                    allow_redirects=False,
                ) as resp:
                    resp_text = await resp.text()

                    LOGGER.warning(
                        "Step 2 SelfAsserted: status=%d, "
                        "content_type=%s, snippet=%s",
                        resp.status,
                        resp.headers.get("Content-Type", ""),
                        resp_text[:200],
                    )

                    if resp.status == 200 and resp_text.startswith("{"):
                        import json as json_mod
                        result = json_mod.loads(resp_text)
                        if str(result.get("status", "")) != "200":
                            raise NESAuthError("Invalid email or password")
                    elif resp.status == 200:
                        LOGGER.warning(
                            "B2C returned non-JSON from SelfAsserted "
                            "(length=%d)", len(resp_text),
                        )
                        raise NESAuthError(
                            "Unexpected response from login"
                        )
                    else:
                        raise NESAuthError(
                            f"SelfAsserted returned HTTP {resp.status}"
                        )

                    # Capture any new cookies from Step 2
                    for hdr_key, hdr_val in resp.raw_headers:
                        if hdr_key.lower() == b"set-cookie":
                            cookie_str = hdr_val.decode()
                            cname = cookie_str.split("=", 1)[0]
                            cval = cookie_str.split("=", 1)[1].split(";")[0]
                            raw_cookies[cname] = cval

                cookie_header = "; ".join(
                    f"{k}={v}" for k, v in raw_cookies.items()
                )

                LOGGER.warning("Step 2 done, requesting authorization code")

                # Step 3: Get the authorization code
                confirmed_url = (
                    f"{B2C_CONFIRMED_URL}"
                    f"?rememberMe=false"
                    f"&csrf_token={csrf_token}"
                    f"&tx={trans_id}"
                    f"&p=B2C_1A_NES_SignUpOrSignIn"
                )

                async with auth_session.get(
                    URL(confirmed_url, encoded=True),
                    headers={"Cookie": cookie_header},
                    allow_redirects=False,
                ) as resp:
                    LOGGER.warning(
                        "Step 3 confirmed: status=%d, has_location=%s",
                        resp.status, "Location" in resp.headers,
                    )

                    if resp.status not in (302, 303):
                        body = await resp.text()
                        LOGGER.warning(
                            "Step 3 unexpected: status=%d, body=%s",
                            resp.status, body[:300],
                        )
                        raise NESAuthError(
                            f"Expected redirect, got HTTP {resp.status}"
                        )

                    location = resp.headers.get("Location", "")
                    parsed = urlparse(location)
                    query_params = parse_qs(parsed.query)

                    if "error" in query_params:
                        error_desc = query_params.get(
                            "error_description", ["Unknown error"]
                        )[0]
                        raise NESAuthError(f"Auth error: {error_desc}")

                    if "code" not in query_params:
                        LOGGER.warning("Redirect: %s", location[:200])
                        raise NESAuthError(
                            "No authorization code in redirect"
                        )

                    auth_code = query_params["code"][0]

                LOGGER.warning(
                    "Step 3 complete: got auth code (%d chars)",
                    len(auth_code),
                )

                # Step 4: Exchange authorization code for tokens
                token_data = {
                    "grant_type": "authorization_code",
                    "client_id": B2C_CLIENT_ID,
                    "code": auth_code,
                    "redirect_uri": B2C_REDIRECT_URI,
                    "code_verifier": code_verifier,
                    "scope": B2C_SCOPE,
                }

                async with auth_session.post(
                    B2C_TOKEN_URL, data=token_data
                ) as resp:
                    resp_text = await resp.text()
                    LOGGER.warning(
                        "Step 4 token exchange: status=%d, "
                        "content_type=%s, length=%d, snippet=%s",
                        resp.status,
                        resp.headers.get("Content-Type", ""),
                        len(resp_text),
                        resp_text[:300],
                    )

                    if resp.status != 200:
                        raise NESAuthError(
                            f"Token exchange failed: HTTP {resp.status}"
                        )

                    try:
                        import json as json_mod
                        result = json_mod.loads(resp_text)
                    except (ValueError, TypeError) as err:
                        raise NESAuthError(
                            f"Token response is not valid JSON"
                        ) from err

                    LOGGER.warning(
                        "Token response keys: %s",
                        list(result.keys()) if isinstance(result, dict) else type(result),
                    )

                    # B2C may return access_token, id_token, or both.
                    # NES portal accepts id_token as bearer token.
                    token = result.get("access_token") or result.get("id_token")
                    if not token:
                        raise NESAuthError(
                            f"Token response missing access_token and "
                            f"id_token: {list(result.keys())}"
                        )
                    self._refresh_token = result.get("refresh_token")

                # Step 5: Exchange B2C id_token for NES API token
                jwt_url = (
                    f"{API_BASE_URL}/rest/auth/jwt"
                    f"?id_token={token}"
                )

                async with self._session.get(jwt_url) as resp:
                    LOGGER.warning(
                        "Step 5 JWT exchange: status=%d, "
                        "content_type=%s",
                        resp.status,
                        resp.headers.get("Content-Type", ""),
                    )

                    if resp.status != 200:
                        body = await resp.text()
                        LOGGER.warning(
                            "Step 5 failed: %s", body[:300]
                        )
                        raise NESAuthError(
                            f"NES JWT exchange failed: HTTP {resp.status}"
                        )

                    nes_result = await resp.json()
                    nes_token = nes_result.get("access_token")
                    if not nes_token:
                        LOGGER.warning(
                            "Step 5 response keys: %s",
                            list(nes_result.keys())
                            if isinstance(nes_result, dict)
                            else str(nes_result)[:200],
                        )
                        raise NESAuthError(
                            "NES JWT exchange missing access_token"
                        )

                    self._access_token = nes_token
                    expires_in = nes_result.get("expires_in", 3600)
                    self._token_expiry = (
                        dt_util.utcnow() + timedelta(seconds=expires_in)
                    )
                    LOGGER.warning(
                        "Successfully authenticated with NES"
                    )

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
                LOGGER.warning(
                    "Customer API: status=%d, content_type=%s",
                    resp.status,
                    resp.headers.get("Content-Type", ""),
                )
                if resp.status == 401:
                    resp_text = await resp.text()
                    LOGGER.warning(
                        "Customer API 401: %s", resp_text[:300]
                    )
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
            end_date = dt_util.utcnow()
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
