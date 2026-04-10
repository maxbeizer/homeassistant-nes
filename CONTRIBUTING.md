# Contributing to homeassistant-nes

Thanks for your interest in contributing! This is a custom Home Assistant integration for Nashville Electric Service (NES).

## Development Setup

```bash
git clone https://github.com/maxbeizer/homeassistant-nes.git
cd homeassistant-nes
python3 -m venv .venv
source .venv/bin/activate
pip install homeassistant pytest-homeassistant-custom-component ruff
```

## Running Tests

```bash
pytest tests/ -v
```

## Linting

```bash
ruff check custom_components/ tests/
ruff format custom_components/ tests/
```

## Architecture

The integration follows standard Home Assistant patterns:

| File | Purpose |
|------|---------|
| `api.py` | NES API client — B2C auth + OAuth2 SSO + REST API |
| `config_flow.py` | UI setup flow (email/password) |
| `coordinator.py` | `DataUpdateCoordinator` — polls every 6 hours |
| `sensor.py` | Sensor entities (monthly/yearly usage and cost) |
| `entity.py` | Base `CoordinatorEntity` with device info |
| `data.py` | Typed runtime data |
| `const.py` | Constants (domain, URLs, logger) |

### Auth Flow

NES uses a complex 3-step authentication:

1. **Azure AD B2C** — headless Authorization Code + PKCE flow with manual cookie handling (aiohttp quotes B2C cookie values, breaking the session)
2. **JWT Exchange** — `GET /rest/auth/jwt?id_token=...` creates a server-side session and returns an SSO UUID via redirect
3. **NES OAuth2** — `POST /rest/oauth/token` with `logintype=sso` exchanges the UUID for an API bearer token

### Usage API

The usage endpoint (`POST /rest/usage`) requires `serviceId`, `billCycleCode` (from `paymentDueDate`), and the full `serviceType` string — all fetched from `/rest/account/services` and `/rest/account/summary` during setup.

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Add tests for any new functionality
3. Make sure all tests pass (`pytest tests/ -v`)
4. Make sure linting passes (`ruff check`)
5. Open a PR with a clear description of the change
