# Endurain for Home Assistant

A [Home Assistant](https://www.home-assistant.io/) custom integration that pulls your training and health data from any self-hosted [Endurain](https://github.com/endurain-project/endurain) instance. It is MIT licensed, needs no cloud account and talks only to your own server.

## Features

- Config flow setup with two authentication modes:
  - **API key** (recommended): a stateless key with read-only scopes.
  - **Username and password**: works with every Endurain version, including accounts with two-factor authentication. The password is used once to log in and is **not stored**; Home Assistant keeps a session token that Endurain rotates on every renewal.
- Re-authentication when credentials stop working; you can switch between the two modes.
- Sensors per account:
  - This week / month / year / lifetime: distance, moving time, number of activities (elevation gain and calories available, disabled by default)
  - Latest activity: name (with type, start time, distance, duration, link as attributes), start time, distance, duration
  - Health: steps, weight, sleep duration, sleep score, resting heart rate (BMI and body fat disabled by default)
- An `event` entity firing `new_activity` when a new workout shows up, for automations such as "congratulate me after a run".
- Values are reported in metric units, so Home Assistant converts them to your unit system.
- Diagnostics with secrets and personal data redacted.

Data is polled every 15 minutes.

## Installation

### HACS (custom repository)

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/schms27/endurain-hass` with category **Integration**.
3. Install **Endurain** and restart Home Assistant.

### Manual

Copy `custom_components/endurain` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

**Settings → Devices & services → Add integration → Endurain**, then enter your instance URL (for example `https://endurain.example.com`) and choose an authentication method.

### API key

Create a key in Endurain under **Settings → Security → API keys** and grant it:

| Scope | Needed for |
| --- | --- |
| `profile` | Required: identifies the account |
| `activities:read` | Summaries and latest activity |
| `health:read` | Steps, weight and sleep |

Sensors whose scope is missing are simply not created.

> [!NOTE]
> Reading data with API keys needs an Endurain server where API keys accept read scopes. Current upstream Endurain releases only allow the `activities:upload` scope for API keys; if your server rejects the key for that reason, the setup tells you so and you can use username and password instead.

### Username and password

Enter your Endurain credentials (and your two-factor code if enabled). If your server sets `SESSION_IDLE_TIMEOUT_ENABLED=true`, sessions end after `SESSION_ABSOLUTE_TIMEOUT_HOURS` and Home Assistant will ask you to sign in again; use an API key in that case.

## Notes

- Activity start times are sent by Endurain without a UTC offset, in the server's time zone. The integration interprets them in Home Assistant's time zone, which matches for typical setups where both run in the same place.
- `hacs.json` declares Home Assistant 2025.2 as the minimum, based on the APIs used. Only the current release (2026.10) is actually tested.

## Development

Home Assistant only runs on Linux and macOS (on Windows, use WSL):

```bash
uv venv --python 3.14
uv pip install pytest-homeassistant-custom-component ruff
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## License

MIT. This project is not affiliated with the Endurain project.
