# Nashville Electric Service (NES) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

> [!CAUTION]
> This is still in early development and may never work

A custom Home Assistant integration for [Nashville Electric Service (NES)](https://www.nespower.com/) that provides energy usage data from the NES customer portal.

## Features

- **Daily Energy Usage** — kWh consumed per day (Energy Dashboard compatible)
- **Monthly Energy Usage** — total kWh for the current billing period
- **Daily Energy Cost** — billed charge per day
- **Temperature Correlation** — daily high/low temperatures alongside usage data

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/maxbeizer/homeassistant-nes` as an **Integration**
4. Search for "Nashville Electric Service" and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → Nashville Electric Service**

### Manual

1. Copy the `custom_components/nes` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration → Nashville Electric Service**

## Configuration

You'll need your NES customer portal credentials (the same email and password you use at [myaccount.nespower.com](https://myaccount.nespower.com/)).

## Energy Dashboard

The **Daily Energy Usage** sensor is compatible with Home Assistant's [Energy Dashboard](https://www.home-assistant.io/docs/energy/). After setup, go to **Settings → Dashboards → Energy** and add the `sensor.nes_daily_energy_usage` entity as a grid consumption source.

## Sensors

| Sensor | Unit | Device Class | Description |
|--------|------|--------------|-------------|
| Daily Energy Usage | kWh | `energy` | Energy consumed today |
| Monthly Energy Usage | kWh | `energy` | Energy consumed this billing period |
| Daily Energy Cost | USD | `monetary` | Cost of energy consumed today |
| Daily High Temperature | °F | `temperature` | High temperature for the day |
| Daily Low Temperature | °F | `temperature` | Low temperature for the day |

## Data Update

Usage data is polled every 6 hours. NES updates usage data once daily, so more frequent polling is unnecessary.

## Troubleshooting

- **Authentication errors**: Verify your credentials work at [myaccount.nespower.com](https://myaccount.nespower.com/)
- **No data**: Usage data may take up to 24 hours to appear for the current day
- **Multiple accounts**: Each NES account can be added as a separate integration entry

## License

MIT — see [LICENSE](LICENSE).
