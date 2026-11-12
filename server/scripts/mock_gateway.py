"""Publish fake gateway traffic to MQTT so the dashboard has live data.

Sends a gateway heartbeat at 2 Hz and a gate status JSON every --interval
seconds, with battery/RSSI/SNR drifting and the gate occasionally moving.

    uv run python scripts/mock_gateway.py --host localhost --interval 1
"""

import argparse
import json
import random
import time

import paho.mqtt.client as mqtt


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--interval", type=float, default=2.0, help="seconds between gate status messages")
    args = p.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="gate_monitor_mock")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    battery_mv, rssi, snr = 12400.0, -85.0, 8.0
    state, state_ticks = "CLOSED", 0
    start = time.monotonic()
    next_status = 0.0
    print(f"Publishing mock traffic to {args.host}:{args.port} (Ctrl+C to stop)")

    try:
        while True:
            now = time.monotonic()
            client.publish(
                "gateway/heartbeat",
                json.dumps({"gate_online": True, "uptime": int(now - start)}),
            )
            if now >= next_status:
                next_status = now + args.interval
                battery_mv = min(12700, max(11000, battery_mv + random.uniform(-15, 12)))
                rssi = min(-40, max(-120, rssi + random.uniform(-2, 2)))
                snr = min(12, max(-10, snr + random.uniform(-0.6, 0.6)))

                state_ticks -= 1
                if state == "MOVING" and state_ticks <= 0:
                    state = random.choice(["OPEN", "CLOSED"])
                elif state != "MOVING" and random.random() < 0.03:
                    state, state_ticks = "MOVING", 3

                payload = {
                    "state": state,
                    "battery": int(battery_mv),
                    "rssi": int(rssi),
                    "snr": round(snr),
                    "online": True,
                }
                client.publish("gate/status", json.dumps(payload))
                print(payload)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
