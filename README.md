# Nashville Electric Service (NES) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/maxbeizer/homeassistant-nes)](https://github.com/maxbeizer/homeassistant-nes/releases)
[![License: MIT](https://img.shields.io/github/license/maxbeizer/homeassistant-nes)](LICENSE)

A custom [Home Assistant](https://www.home-assistant.io/) integration for [Nashville Electric Service (NES)](https://www.nespower.com/) that provides energy usage and cost data from the NES customer portal.

## Sensors

| Sensor | Unit | Device Class | Description |
|--------|------|--------------|-------------|
| Monthly Energy Usage | kWh | `energy` | Billed energy for the most recent billing period |
| Monthly Energy Cost | USD | `monetary` | Billed cost for the most recent billing period |
| Yearly Energy Usage | kWh | `energy` | Total energy over the last 13 billing periods |
| Yearly Energy Cost | USD | `monetary` | Total cost over the last 13 billing periods |

The **Monthly Energy Usage** sensor is compatible with Home Assistant's [Energy Dashboard](https://www.home-assistant.io/docs/energy/).

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/maxbeizer/homeassistant-nes` with category **Integration**
4. Search for "Nashville Electric Service" and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → Nashville Electric Service**

### Manual

1. Copy the `custom_components/nes` directory into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration → Nashville Electric Service**

## Configuration

You'll need your NES customer portal credentials — the same email and password you use at [myaccount.nespower.com](https://myaccount.nespower.com/).

## How it works

The integration authenticates with NES through a multi-step flow:

1. **Azure AD B2C** headless login (Authorization Code + PKCE)
2. **NES JWT exchange** to create a server-side session
3. **NES OAuth2** token grant with the SSO session

Usage data is polled every **6 hours**. NES updates billing data monthly, so more frequent polling is unnecessary.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Invalid email or password | Verify your credentials work at [myaccount.nespower.com](https://myaccount.nespower.com/) |
| No data after setup | Usage data may take a few minutes to appear after initial setup |
| Integration won't load | Check Home Assistant logs: **Settings → System → Logs**, filter by `nes` |

## Development

```bash
# Clone and set up
git clone https://github.com/maxbeizer/homeassistant-nes.git
cd homeassistant-nes
python3 -m venv .venv && source .venv/bin/activate
pip install homeassistant pytest-homeassistant-custom-component

# Run tests
pytest tests/
```

## License

[MIT](LICENSE)
