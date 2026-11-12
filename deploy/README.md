# Home server: Mosquitto + Home Assistant + Gate Monitor

One script turns a Debian, Ubuntu or Raspberry Pi OS machine (amd64 or arm64)
into the farm hub. Everything runs in Docker with host networking:

| Service | Port | What it does |
|---|---|---|
| **Mosquitto** 2.0 | 1883 | MQTT broker. The house gateway, Home Assistant and Gate Monitor all connect here. Password-protected. |
| **Home Assistant** | 8123 | Phone app, automations, alerts. Gate, coop and solar entities appear automatically through MQTT discovery. |
| **Gate Monitor** | 8000 | Live web dashboard (React) plus history, built from `../server`. Publishes the Home Assistant discovery messages. |

```
 ESP32 house gateway ──┐                      ┌── Gate Monitor :8000  (web dashboard, history, simulator)
 coop / solar devices ─┼── Mosquitto :1883 ───┤
                       │                      └── Home Assistant :8123 ── Companion app on your phone
                       └── (all MQTT, user/password per client)
```

## Quick start

```bash
git clone <this repo> && cd GateMonitor
sudo ./scripts/provision-home-server.sh \
    --lat 40.01 --lon -105.27 --country US \
    --ha-user farm --ha-password 'pick-a-strong-one'
```

The script does the following:

1. Installs Docker Engine and the compose plugin from Docker's apt repo, if Docker is missing.
2. Copies this directory and the server source to `/opt/farm-monitor`.
3. Generates random broker passwords for three users: `gatemonitor`, `homeassistant` and `gateway`. It stores them in `/opt/farm-monitor/.env` (mode 600) and writes the Mosquitto password file.
4. Writes Home Assistant's `core.yaml` with your location and time zone, so the sunrise/sunset coop automations fire at the right time.
5. Builds and starts the containers.
6. With `--ha-user`: creates the HA owner account and adds the MQTT integration, so no clicking is needed (`ha_bootstrap.py`).
7. Prints the `credentials.h` values for the house gateway firmware.

The script is safe to re-run. Passwords, HA data and your `configuration.yaml`
are kept. The managed files (`core.yaml`, `packages/farm_monitor.yaml`,
`dashboards/farm.yaml`) are refreshed, and HA restarts if any of them changed.
**Re-running is also how you update** after pulling new code.

### Options

```
--lat/--lon/--elevation   Farm location (sunrise/sunset schedules)
--tz America/Denver       Time zone (default: the host's)
--country US              Country code for Home Assistant
--metric                  Metric units in HA (default: US customary)
--ha-user/--ha-password   Automate HA onboarding and MQTT setup
--external-broker H[:P]   Keep an existing broker instead of the bundled one
--mqtt-user/--mqtt-password   ...and its credentials
--no-simulate             Turn off the simulated coops/solar once real ones report
--port 8000               Gate Monitor port
--dir /opt/farm-monitor   Install location
--skip-docker-install     Never touch Docker packages
```

### Migrating the existing Raspberry Pi setup

The old `scripts/setup-raspberry-pi.sh` installed Mosquitto and Gate Monitor
natively, the broker with anonymous access. The provisioning script stops if it
finds them on ports 1883 or 8000. Pick one of two ways forward:

- **Clean move (recommended):**
  ```bash
  sudo systemctl disable --now gate-monitor mosquitto
  sudo ./scripts/provision-home-server.sh --lat ... --lon ... --ha-user ...
  ```
  Then update `firmware/house_gateway/credentials.h` with the printed
  `MQTT_USER`/`MQTT_PASSWORD` and reflash the gateway. The new broker refuses
  anonymous clients.
- **Keep the native broker:** stop only `gate-monitor`, then pass
  `--external-broker 127.0.0.1:1883`, plus `--mqtt-user`/`--mqtt-password` if
  it has auth.

## Phone control

1. Install the **Home Assistant** Companion app (iOS/Android) and sign in to
   `http://<server-ip>:8123` with the account the script created.
2. Open **Farm** in the sidebar. It shows the gate with open/close buttons,
   each coop door, the coop schedule switches and the solar gauge.
3. For alerts, open **Developer tools → Actions** and find your phone's
   `notify.mobile_app_…` service. Put that name into the **Farm notify
   service** field at the bottom of the Farm dashboard.
4. Optionally, on iOS/Android, add HA's "Farm gate" tile to the home screen or
   lock screen. The companion app supports widgets and controls for any entity.

The Gate Monitor dashboard (`:8000`) also works on a phone: open it in the
browser and choose **Add to Home Screen**. Its bottom tab bar is sized for
thumbs.

### Alerts included (`packages/farm_monitor.yaml`)

| Alert | When | Button |
|---|---|---|
| Gate left open | Open longer than the configured minutes (default 5) | **Close gate** |
| Gate offline | Gate unavailable for 5 min (LoRa or gateway down) | – |
| Gate battery low | Below 20% for 30 min | – |
| Coop door open after dark | Any coop door not closed 1 h after sunset | **Close coop doors** |
| Coop door jammed | Jam sensor turns on | – |
| Solar battery low | Below 30% for 15 min | – |

The buttons work from the lock screen. Each sends an action that HA turns into
`cover.close_cover`. **Mute farm alerts** on the dashboard silences them all.

### Away from home

Don't port-forward 8123, 8000 or 1883. Use one of these:

- **Home Assistant Cloud (Nabu Casa)**: paid, a single toggle in HA, and the app just works.
- **Tailscale** (free for personal use): `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
  on the server and install the app on your phone. HA is then at
  `http://<tailscale-name>:8123` from anywhere.

Gate Monitor itself has no login. Anyone who can reach port 8000 can operate
the gate, so keep it on the LAN or tailnet. HA, with its accounts, is the
thing to expose.

## Day-to-day

```bash
cd /opt/farm-monitor
docker compose ps                        # status (uses .env automatically)
docker compose logs -f gate-monitor      # follow logs
docker compose restart homeassistant
docker compose --profile broker down     # stop everything
```

Back up `/opt/farm-monitor`, which holds HA config, the `.env` secrets and the
broker password file. Back up the Docker volumes too: `farm-monitor_gate-monitor-data`
holds history and `farm-monitor_mosquitto-data` holds retained messages.

To check MQTT traffic, using credentials from `.env`:
```bash
docker exec -it mosquitto mosquitto_sub -u gatemonitor -P "$(grep ^MQTT_SERVER_PASSWORD .env | cut -d= -f2)" -t '#' -v
```

## Files here

| Path | Purpose |
|---|---|
| `docker-compose.yml` | The three services. The broker is behind the `broker` profile so `--external-broker` can skip it. |
| `mosquitto/mosquitto.conf` | Auth required, persistence on, logs to stdout. |
| `homeassistant/configuration.yaml` | Copied only on first install; yours after that. |
| `homeassistant/core.yaml` | Location, units and packages. Regenerated by the script. |
| `homeassistant/packages/farm_monitor.yaml` | Helpers, notify script, alerts and the coop door group. |
| `homeassistant/dashboards/farm.yaml` | The "Farm" sidebar dashboard. |

## How it was tested

On HA 2026.11.1 in Docker:
- A full run of the script with `--external-broker`: fresh onboarding, MQTT added, all discovery entities created, and a re-run that kept every secret.
- Gate and coop control from HA, reaching the mock gateway and the simulator.
- The lock-screen action handler, triggered by a simulated button press.
- `check_config` passed on this configuration.

The bundled-broker path was tested separately: password generation, auth rejecting anonymous clients and bad passwords, and the healthcheck. It wasn't run on a full install, because the test machine already had a broker on port 1883.
