# MQTT topic contract

Every component talks over the Mosquitto broker. This page tells future
coop and solar hardware what to publish, so it shows up in the web dashboard
and Home Assistant with no server changes.

## Gate (existing firmware: `firmware/house_gateway`)

| Topic | Dir | Retained | Payload |
|---|---|---|---|
| `gate/status` | gateway → | yes | `{"state":"OPEN\|CLOSED\|MOVING\|UNKNOWN\|ERROR","battery":12400,"rssi":-85,"snr":8,"online":true}` (battery in mV) |
| `gate/battery` | gateway → | yes | `12400` (mV) |
| `gate/rssi` | gateway → | yes | `-85` |
| `gate/online` | gateway → | yes | `online` / `offline` (gate node reachable over LoRa) |
| `gateway/online` | gateway → | yes | `online` |
| `gateway/heartbeat` | gateway → | no | JSON at 2 Hz. The server marks the gateway offline after 2 s of silence. |
| `gate/command` | → gateway | no | `OPEN`, `CLOSE`, `STOP`, `STATUS` |

## Chicken coop door controller

Any id matching `[a-z0-9][a-z0-9_-]{0,31}` works, e.g. `main-coop`.

**`coop/<id>/state`**: publish retained, on change and at least every 60 s:

```json
{
  "name": "Main Coop",
  "door": "OPEN",              // OPEN | CLOSED | OPENING | CLOSING | JAMMED | UNKNOWN
  "mode": "auto",              // auto = follows sunrise/sunset, manual = schedule paused
  "temperature_c": 14.2,
  "humidity": 55.0,
  "battery_v": 12.6,
  "last_opened": "2026-11-12T07:41:02-06:00",
  "last_closed": "2026-11-11T18:16:58-06:00",
  "next_open":  "2026-11-13T07:42:12-06:00",
  "next_close": "2026-11-12T18:16:50-06:00",
  "online": true
}
```

All fields except `door` are optional. Set the MQTT Last Will to the same topic
with `{"online": false}` (retained) so HA shows the device unavailable when it
drops.

**`coop/<id>/command`**: subscribe. Payloads: `OPEN`, `CLOSE`, `STOP`, `AUTO`,
`MANUAL`. Respond by publishing the new state.

## Solar charge controller

**`solar/<id>/state`**: publish retained, every 5–30 s:

```json
{
  "name": "Barn Solar",
  "battery_soc": 78.5,         // %
  "battery_v": 13.31,
  "battery_a": 4.2,            // + charging, − discharging
  "panel_v": 19.8,
  "panel_w": 180.0,
  "load_w": 24.0,
  "charge_state": "bulk",      // off | bulk | absorption | float | fault
  "yield_today_wh": 640.0,     // resets at midnight (HA Energy dashboard uses it)
  "online": true
}
```

No commands are defined for solar yet.

## Published by the Gate Monitor server

| Topic | Retained | Payload |
|---|---|---|
| `gatemonitor/status` | yes | `online` / `offline` (Last Will) |
| `gatemonitor/gate/cover` | yes | `open`, `closed`, `opening`, `closing`, `stopped`, `None`. The gateway's `MOVING` gets its direction from the last `gate/command`. |
| `gatemonitor/gateway/online` | yes | `online` / `offline` from the heartbeat timeout |
| `homeassistant/<component>/gatemonitor/<uid>/config` | yes | HA discovery. Republished on connect and whenever HA publishes `online` to `homeassistant/status`. |

While `SIMULATE_DEVICES=true` the server also publishes simulated
`coop/main-coop`, `coop/brooder` and `solar/barn-solar` states, marked
`"simulated": true`. A server running with the simulator off ignores those.
To clear the leftovers after switching to real hardware, run (dry run first):

```bash
cd server && uv run python scripts/clear_retained.py --host <broker> [--username ... --password ...] --yes
```
