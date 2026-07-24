# Resideo Shutoff Valve for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/rumil/Homeassistant-Resideo-Shutoff-Valve/actions/workflows/validate.yml/badge.svg)](https://github.com/rumil/Homeassistant-Resideo-Shutoff-Valve/actions/workflows/validate.yml)

A custom [Home Assistant](https://www.home-assistant.io/) integration that adds support for the
**Resideo (Honeywell) L5 Wi-Fi Water Shutoff Valve** via the Resideo / Honeywell Home cloud API.

The official built-in [`lyric`](https://www.home-assistant.io/integrations/lyric/) integration uses
the same cloud but only exposes thermostats. This integration fills the gap by adding the L5 shutoff
valve as a first-class Home Assistant [`valve`](https://www.home-assistant.io/integrations/valve/)
entity, plus diagnostic sensors.

## Features

For each L5 valve on your account this integration creates:

| Entity | Platform | Description |
| --- | --- | --- |
| Valve | `valve` | Open / close the water shutoff valve; reports open / closed / opening / closing |
| Leak | `binary_sensor` (moisture) | On when the valve reports an active leak |
| Connectivity | `binary_sensor` (connectivity, diagnostic) | Device online status |
| Device temperature | `sensor` (diagnostic) | On-device temperature (°F) |
| Leak status | `sensor` (enum, diagnostic) | Raw leak status (`ok` / `leak` / `na` / `err`) |
| Motor cycles | `sensor` (diagnostic) | Cumulative actuator motor cycles |
| Last check-in | `sensor` (timestamp, diagnostic) | Time of the device's last cloud check-in |
| Last anti-scale cycle | `sensor` (timestamp, diagnostic, disabled by default) | Last automatic anti-scale exercise |

> **Note:** This is a cloud-polling integration. State refreshes every 5 minutes; after you send an
> open/close command the state is refreshed immediately.

## Prerequisites

You need a free Resideo developer application to obtain OAuth credentials:

1. Sign in at the [Resideo Developer Portal](https://developer.honeywellhome.com).
2. Create a new **App**.
3. Set the app's **Callback URL** to exactly:
   ```
   https://my.home-assistant.io/redirect/oauth
   ```
4. After the app is created, note its **Consumer Key** (OAuth Client ID) and **Consumer Secret**
   (OAuth Client Secret).

Your Resideo account must already have the L5 valve set up and working in the Resideo / Honeywell
Home mobile app.

## Installation

### HACS (recommended)

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/rumil/Homeassistant-Resideo-Shutoff-Valve` with category
   **Integration**.
3. Search for **Resideo Shutoff Valve**, install it, and restart Home Assistant.

### Manual

Copy `custom_components/resideo_shutoff_valve` into your Home Assistant `config/custom_components/`
directory and restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration** and search for **Resideo Shutoff
   Valve**.
2. The first time, you'll be asked for **Application Credentials** — enter the Consumer Key as the
   Client ID and the Consumer Secret as the Client Secret.
3. Complete the OAuth login with your Resideo account and authorize access.
4. Your valve(s) and their entities are created automatically.

## Troubleshooting

- **"missing_credentials" / no credentials prompt** — add credentials under **Settings → Devices &
  Services → Application Credentials** first, or re-run the flow.
- **OAuth redirect fails** — confirm the app's callback URL is exactly
  `https://my.home-assistant.io/redirect/oauth` and that your Home Assistant is linked to
  [My Home Assistant](https://my.home-assistant.io/).
- **Re-authentication prompt** — Resideo tokens expire periodically; follow the reauth flow when
  prompted.
- Enable debug logging by adding to `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.resideo_shutoff_valve: debug
  ```

## Disclaimer

This is an unofficial, community-maintained integration and is not affiliated with or endorsed by
Resideo or Honeywell. "Resideo" and "Honeywell" are trademarks of their respective owners.

## License

Released under the [MIT License](LICENSE).
