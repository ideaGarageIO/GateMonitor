# Gate / Farm Monitor Server

FastAPI server plus a React + TypeScript dashboard for the farm. It covers the
LoRa gate, chicken coop doors and the solar charge controller. Values stream to
the browser live over a WebSocket. The server keeps history in SQLite and
announces every device to Home Assistant through MQTT discovery.

> **Deploying to the home server?** Use `../scripts/provision-home-server.sh`.
> It runs this server, Mosquitto and Home Assistant in Docker. See
> [`../deploy/README.md`](../deploy/README.md). The rest of this page covers
> development.

## Features

- **Tabs.** Overview (alerts, tiles for every device, quick gate control),
  Gate, Coops and Solar. Each page uses hash URLs (`#/coops`) so it can be
  bookmarked, and the tabs become a bottom bar on phones. The page can be
  installed to a phone's home screen.
- **Live charts.** Gate battery, RSSI and SNR; coop temperature; solar panel
  power, state of charge and load. Windows of 5m, 15m or 1h, a hover readout,
  and backfill from SQLite on page load.
- **Controls.** Gate open/stop/close. Coop door open/stop/close and the
  sunrise/sunset schedule switch.
- **Activity log.** Gate and coop door state changes and online/offline
  transitions, stored in SQLite.
- **Alerts in the UI.** Server, MQTT or gateway offline; gate error; low
  batteries; a jammed coop door; a coop door open after dark; low solar charge.
- **Simulator.** Two coops and one solar array, so everything works before the
  hardware exists (`SIMULATE_DEVICES=true`).
- **Home Assistant.** MQTT discovery for a gate cover, coop door covers, sensors
  and switches. See [`../docs/mqtt-topics.md`](../docs/mqtt-topics.md).

## Run it (development)

```bash
cd server
uv sync
uv run gate-monitor                          # http://localhost:8000
uv run python scripts/mock_gateway.py        # optional: fake gate + gateway (obeys commands)
```

You need a broker on `MQTT_HOST` (default `localhost:1883`). Without one, the
server still starts and keeps retrying. Simulated coops and solar still work,
but gate commands return `503`.

### Frontend

The built dashboard is served from `frontend/dist/`. After changing frontend
code:

```bash
cd frontend
npm install && npm run build      # or, without Node installed:
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/app -w /app node:22-alpine sh -c "npm install && npm run build"
```

For hot reload, run `npm run dev` and open http://localhost:5173. Vite passes
`/api` and `/ws` through to the server on `:8000` (set `GATE_BACKEND` to change
that).

### Docker

```bash
docker build -t gate-monitor .    # builds the frontend too; no Node needed
docker run --network host -e MQTT_HOST=127.0.0.1 -v gm-data:/data gate-monitor
```

## Configuration

Set these in the environment or in `.env`. The full list with defaults is in
[`.env.example`](.env.example). The main ones:

| Variable | Default | |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` / `MQTT_USER` / `MQTT_PASSWORD` | `localhost` / `1883` | Broker |
| `SIMULATE_DEVICES` | `true` | Run simulated coops and solar |
| `LATITUDE` / `LONGITUDE` | `40.0` / `-105.0` | Sunrise/sunset for the simulator |
| `HA_DISCOVERY` | `true` | Publish Home Assistant discovery |
| `DB_PATH` | `./data/gate_monitor.db` | SQLite history |
| `HISTORY_DAYS` | `30` | Telemetry retention |

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Versions and connectivity |
| `/api/devices` | GET | `{gate, devices: [...]}` |
| `/api/devices/{id}` | GET | One device (`gate`, `main-coop`, `barn-solar`, …) |
| `/api/devices/{id}/command/{cmd}` | POST | Gate: `open` / `close` / `stop` / `status`. Coop: `open` / `close` / `stop` / `auto` / `manual`. |
| `/api/readings/{id}?minutes=60` | GET | Stored telemetry `[{t, field: value}]`, thinned to ≤720 points |
| `/api/events?device=&limit=50` | GET | Activity log |
| `/api/status`, `/api/history`, `/api/command/{cmd}` | | Older gate-only endpoints, kept for compatibility |
| `/ws` | WS | Live stream: `status`, `devices`, `device`, `event`, `command_result`. Send `{"type":"command","device":"main-coop","command":"close"}`. |

## Scripts

| Script | |
|---|---|
| `scripts/mock_gateway.py` | Stands in for the LoRa gateway and gate on MQTT and responds to commands |
| `scripts/clear_retained.py` | Removes simulated or test retained messages from the broker (dry run by default) |

## Testing

```bash
uv run --group dev pytest        # 36 tests: models, registry, simulator, HA discovery, DB, API/WebSocket
cd frontend && npm run typecheck
```

## Layout

```
src/gate_monitor/
  main.py           FastAPI app: wiring, REST, WebSocket, frontend
  mqtt_client.py    paho client: gate topics, generic topic handlers, LWT, reconnect
  devices.py        coop/solar models and registry
  simulator.py      simulated coops and solar
  sun.py            sunrise/sunset maths
  homeassistant.py  MQTT discovery payloads
  database.py       SQLite history
  models.py         gate models (match firmware gate_protocol.h)
frontend/src/
  useFarmSocket.ts  WebSocket and state for every device
  pages/            Overview, Gate, Coops, Solar
  components/       LiveChart (SVG), StatusCard, Controls, shared UI
  alerts.ts         alert rules for the Overview tab
static/             old vanilla-JS page (fallback when frontend/dist is missing)
```
