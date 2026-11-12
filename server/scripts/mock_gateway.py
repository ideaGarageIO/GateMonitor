"""Pretend to be the LoRa house gateway + gate node, over MQTT.

Publishes what house_gateway.ino publishes (heartbeat at 2 Hz, retained
gate/status JSON, gate/battery, gate/rssi, gate/online) and obeys
OPEN / CLOSE / STOP / STATUS on gate/command, so the web UI and Home
Assistant can be exercised end-to-end with no hardware.

    uv run python scripts/mock_gateway.py --host localhost --interval 2
"""

import argparse
import json
import random
import threading
import time

import paho.mqtt.client as mqtt

TRAVEL_S = 12.0  # how long the mock gate takes to open/close


class MockGate:
    def __init__(self) -> None:
        self.state = "CLOSED"
        self.target: str | None = None
        self.motion_left = 0.0
        self.battery_mv = 12400.0
        self.rssi = -85.0
        self.snr = 8.0
        self.lock = threading.Lock()
        self.force_publish = threading.Event()

    def command(self, cmd: str) -> None:
        cmd = cmd.strip().upper()
        with self.lock:
            if cmd in ("OPEN", "CLOSE"):
                target = "OPEN" if cmd == "OPEN" else "CLOSED"
                if self.state != target:
                    self.state, self.target, self.motion_left = "MOVING", target, TRAVEL_S
            elif cmd == "STOP" and self.state == "MOVING":
                # Real gates stop mid-travel with neither limit switch made.
                self.target, self.motion_left = None, 0.0
        print(f"<- command {cmd}")
        self.force_publish.set()

    def step(self, dt: float) -> None:
        with self.lock:
            if self.state == "MOVING" and self.target:
                self.motion_left -= dt
                if self.motion_left <= 0:
                    self.state, self.target = self.target, None
            self.battery_mv = min(12700, max(11000, self.battery_mv + random.uniform(-6, 5.5)))
            self.rssi = min(-40, max(-120, self.rssi + random.uniform(-1.5, 1.5)))
            self.snr = min(12, max(-10, self.snr + random.uniform(-0.4, 0.4)))

    def payload(self) -> dict:
        with self.lock:
            return {
                "state": self.state,
                # Motor draw sags the terminal voltage while moving.
                "battery": int(self.battery_mv - (180 if self.state == "MOVING" else 0)),
                "rssi": int(self.rssi),
                "snr": round(self.snr),
                "online": True,
            }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between gate status messages")
    args = p.parse_args()

    gate = MockGate()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="gate_monitor_mock_gateway")
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.will_set("gate/online", "offline", retain=True)

    def on_connect(c, _u, _f, rc, _p=None):
        print(f"connected ({rc})")
        c.subscribe("gate/command")
        c.publish("gateway/online", "online", retain=True)
        c.publish("gate/online", "online", retain=True)

    client.on_connect = on_connect
    client.on_message = lambda _c, _u, msg: gate.command(msg.payload.decode(errors="replace"))
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    start = time.monotonic()
    next_status = 0.0
    print(f"Mock gateway on {args.host}:{args.port} (Ctrl+C to stop)")
    try:
        while True:
            now = time.monotonic()
            gate.step(0.5)
            client.publish("gateway/heartbeat", json.dumps({"gate_online": True, "uptime": int(now - start)}))
            if now >= next_status or gate.force_publish.is_set():
                gate.force_publish.clear()
                next_status = now + args.interval
                data = gate.payload()
                client.publish("gate/status", json.dumps(data), retain=True)
                client.publish("gate/battery", str(data["battery"]), retain=True)
                client.publish("gate/rssi", str(data["rssi"]), retain=True)
                print(data)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish("gate/online", "offline", retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
