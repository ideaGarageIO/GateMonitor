#!/usr/bin/env python3
"""Finish Home Assistant setup without clicking through the UI.

1. Onboards a fresh instance (creates the owner account), or logs in to an
   existing one with the same username/password.
2. Adds the MQTT integration pointed at the farm broker (skipped if present),
   which makes every gate/coop/solar entity appear via discovery.

Standard library only, so it runs on a bare server. Idempotent: re-running
is safe.

    python3 scripts/ha_bootstrap.py --url http://localhost:8123 \
        --username farm --password '...' \
        --mqtt-host 127.0.0.1 --mqtt-user homeassistant --mqtt-password '...'

Exit codes: 0 ok, 1 error, 2 HA not reachable.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class HAError(RuntimeError):
    pass


class HA:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.client_id = self.url + "/"
        self.token: Optional[str] = None

    def request(self, method: str, path: str, body: Any = None, form: Optional[dict] = None, auth: bool = True) -> Any:
        headers = {}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise HAError(f"{method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
        return json.loads(raw) if raw else None

    # ------------------------------------------------------------ waiting

    def wait_until_up(self, timeout_s: int) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                self.request("GET", "/api/onboarding", auth=False)
                return
            except (HAError, urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(3)
        raise TimeoutError(f"Home Assistant not reachable at {self.url} after {timeout_s}s")

    # ------------------------------------------------------------ auth

    def onboarding_steps(self) -> dict[str, bool]:
        try:
            steps = self.request("GET", "/api/onboarding", auth=False)
        except HAError:
            return {}  # onboarding API disappears once complete on some versions
        return {s["step"]: s["done"] for s in steps}

    def _exchange(self, code: str) -> None:
        tok = self.request(
            "POST",
            "/auth/token",
            form={"grant_type": "authorization_code", "code": code, "client_id": self.client_id},
            auth=False,
        )
        self.token = tok["access_token"]

    def onboard(self, name: str, username: str, password: str, language: str) -> None:
        res = self.request(
            "POST",
            "/api/onboarding/users",
            {"client_id": self.client_id, "name": name, "username": username, "password": password, "language": language},
            auth=False,
        )
        self._exchange(res["auth_code"])
        steps = self.onboarding_steps()
        # Location/units come from core.yaml (written by the provision script).
        for step in ("core_config", "analytics", "integration"):
            if not steps.get(step, True):
                payload = {"client_id": self.client_id, "redirect_uri": self.client_id + "?auth_callback=1"}
                self.request("POST", f"/api/onboarding/{step}", payload)

    def login(self, username: str, password: str) -> None:
        flow = self.request(
            "POST",
            "/auth/login_flow",
            {"client_id": self.client_id, "handler": ["homeassistant", None], "redirect_uri": self.client_id},
            auth=False,
        )
        res = self.request(
            "POST",
            f"/auth/login_flow/{flow['flow_id']}",
            {"client_id": self.client_id, "username": username, "password": password},
            auth=False,
        )
        if res.get("type") != "create_entry":
            raise HAError(f"Login failed: {res.get('errors') or res}")
        self._exchange(res["result"])

    # ------------------------------------------------------------ MQTT

    def mqtt_entries(self) -> list[dict]:
        entries = self.request("GET", "/api/config/config_entries/entry?domain=mqtt")
        return [e for e in entries if e.get("domain") == "mqtt"]

    def add_mqtt(self, host: str, port: int, user: str, password: str) -> dict:
        flow = self.request("POST", "/api/config/config_entries/flow", {"handler": "mqtt", "show_advanced_options": False})
        if flow.get("type") == "abort":
            raise HAError(f"MQTT setup aborted: {flow.get('reason')}")
        fields = {f["name"] for f in flow.get("data_schema", [])}
        data: dict[str, Any] = {"broker": host, "port": port}
        if user:
            data["username"] = user
            data["password"] = password
        if "other_settings" in fields:  # HA 2025+ groups TLS options in a section
            data["other_settings"] = {"set_client_cert": False, "set_ca_cert": "off"}
        res = self.request("POST", f"/api/config/config_entries/flow/{flow['flow_id']}", data)
        if res.get("type") != "create_entry":
            raise HAError(f"MQTT setup failed: {res.get('errors') or res}")
        return res

    def states(self) -> list[dict]:
        return self.request("GET", "/api/states")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8123")
    p.add_argument("--name", default="Farm Admin", help="display name for a new owner account")
    p.add_argument("--username", required=True)
    p.add_argument("--password", help="prompted if omitted")
    p.add_argument("--language", default="en")
    p.add_argument("--mqtt-host", default="127.0.0.1")
    p.add_argument("--mqtt-port", type=int, default=1883)
    p.add_argument("--mqtt-user", default="")
    p.add_argument("--mqtt-password", default="")
    p.add_argument("--wait", type=int, default=300, help="seconds to wait for HA to come up")
    args = p.parse_args()
    password = args.password or getpass.getpass(f"Home Assistant password for {args.username}: ")

    ha = HA(args.url)
    try:
        print(f"Waiting for Home Assistant at {args.url} ...")
        ha.wait_until_up(args.wait)
    except TimeoutError as e:
        print(e, file=sys.stderr)
        return 2

    try:
        steps = ha.onboarding_steps()
        if steps and not steps.get("user", True):
            print(f"Onboarding: creating owner account '{args.username}'")
            ha.onboard(args.name, args.username, password, args.language)
        else:
            print(f"Already onboarded; logging in as '{args.username}'")
            ha.login(args.username, password)

        if ha.mqtt_entries():
            print("MQTT integration already configured")
        else:
            print(f"Adding MQTT integration -> {args.mqtt_host}:{args.mqtt_port}")
            ha.add_mqtt(args.mqtt_host, args.mqtt_port, args.mqtt_user, args.mqtt_password)

        # Discovery is retained on the broker, so entities show up within seconds.
        for _ in range(20):
            farm = [s for s in ha.states() if s["entity_id"] in ("cover.farm_gate", "cover.coop_doors")]
            if any(s["entity_id"] == "cover.farm_gate" for s in farm):
                break
            time.sleep(1.5)
        found = sorted(s["entity_id"] for s in ha.states() if "farm" in s["entity_id"] or "coop" in s["entity_id"])
        print(f"Farm entities in HA: {len(found)}")
        if "cover.farm_gate" not in found:
            print("  (cover.farm_gate not seen yet — is gate-monitor running and connected to the broker?)")
    except HAError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print("Home Assistant bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
