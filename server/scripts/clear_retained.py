"""Remove retained MQTT messages left by the simulator or by testing.

By default it clears only *simulated* devices: ``coop/*`` and ``solar/*`` states
marked ``"simulated": true`` plus their Home Assistant discovery configs.
Real devices' retained state is left alone.

    uv run python scripts/clear_retained.py --host localhost            # dry run
    uv run python scripts/clear_retained.py --host localhost --yes      # do it
    uv run python scripts/clear_retained.py --all-gatemonitor --yes     # + every gatemonitor discovery/state topic

Run it with the server stopped, or with SIMULATE_DEVICES=false, or the
simulator will just publish them again.
"""

import argparse
import json
import time

import paho.mqtt.client as mqtt


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--prefix", default="homeassistant", help="HA discovery prefix")
    p.add_argument("--all-gatemonitor", action="store_true",
                   help="also clear gate discovery and gatemonitor/* topics (full uninstall)")
    p.add_argument("--yes", action="store_true", help="actually delete (default is a dry run)")
    args = p.parse_args()

    retained: dict[str, bytes] = {}
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"gm_clear_{int(time.time())}")
    if args.username:
        c.username_pw_set(args.username, args.password)

    def on_connect(client, *_a):
        client.subscribe([("coop/#", 0), ("solar/#", 0), (f"{args.prefix}/+/gatemonitor/#", 0), ("gatemonitor/#", 0)])

    def on_message(_c, _u, msg):
        if msg.retain and msg.payload:
            retained[msg.topic] = msg.payload

    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(args.host, args.port)
    c.loop_start()
    time.sleep(2.0)  # retained messages arrive right after subscribing

    doomed: list[str] = []
    sim_ids: set[str] = set()
    for topic, payload in retained.items():
        parts = topic.split("/")
        if parts[0] in ("coop", "solar") and len(parts) == 3 and parts[2] == "state":
            try:
                simulated = bool(json.loads(payload).get("simulated"))
            except (ValueError, AttributeError):
                simulated = False
            if simulated or args.all_gatemonitor:
                doomed.append(topic)
                sim_ids.add(f"{parts[0]}_{parts[1].replace('-', '_')}")

    for topic in retained:
        if topic.startswith(f"{args.prefix}/"):
            uid = topic.split("/")[3]  # <prefix>/<component>/gatemonitor/<uid>/config
            if args.all_gatemonitor or any(uid == s or uid.startswith(s + "_") for s in sim_ids):
                doomed.append(topic)
        elif topic.startswith("gatemonitor/") and args.all_gatemonitor:
            doomed.append(topic)

    for topic in sorted(doomed):
        print(("clear  " if args.yes else "would clear  ") + topic)
        if args.yes:
            c.publish(topic, b"", qos=1, retain=True).wait_for_publish(5)
    if not doomed:
        print("Nothing to clear.")
    elif not args.yes:
        print(f"\n{len(doomed)} topics. Re-run with --yes to clear them.")
    c.loop_stop()
    c.disconnect()


if __name__ == "__main__":
    main()
