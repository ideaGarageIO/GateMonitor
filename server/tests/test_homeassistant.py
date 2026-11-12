"""Tests for Home Assistant MQTT discovery payloads."""

import json

from gate_monitor.devices import DeviceRegistry
from gate_monitor.homeassistant import TOPIC_GATE_COVER, HomeAssistantDiscovery, gate_cover_state
from gate_monitor.models import Command, GateState, GateStatus


def _collect():
    sent: dict[str, str] = {}

    def publish(topic: str, payload: str, retain: bool) -> bool:
        assert retain
        sent[topic] = payload
        return True

    return sent, publish


class TestCoverState:
    def test_mapping(self) -> None:
        s = GateStatus(state=GateState.OPEN, online=True)
        assert gate_cover_state(s, None) == "open"
        s.state = GateState.CLOSED
        assert gate_cover_state(s, None) == "closed"
        s.state = GateState.MOVING
        assert gate_cover_state(s, Command.CLOSE) == "closing"
        assert gate_cover_state(s, Command.OPEN) == "opening"
        assert gate_cover_state(s, Command.STOP) == "stopped"
        s.state = GateState.ERROR
        assert gate_cover_state(s, None) == "None"  # HA: unknown

    def test_offline_is_unknown(self) -> None:
        assert gate_cover_state(GateStatus(state=GateState.OPEN, online=False), None) == "None"


class TestDiscovery:
    def test_gate_configs(self) -> None:
        sent, publish = _collect()
        HomeAssistantDiscovery(publish).announce_all([])
        cover = json.loads(sent["homeassistant/cover/gatemonitor/gate/config"])
        assert cover["command_topic"] == "gate/command"
        assert cover["payload_open"] == "OPEN"  # what house_gateway.ino expects
        assert cover["state_topic"] == TOPIC_GATE_COVER
        assert cover["device_class"] == "gate"
        assert cover["default_entity_id"] == "cover.farm_gate"
        # unique_ids must be unique across all configs
        uids = [json.loads(p)["unique_id"] for p in sent.values()]
        assert len(uids) == len(set(uids))

    def test_device_configs_once(self) -> None:
        sent, publish = _collect()
        disc = HomeAssistantDiscovery(publish, prefix="ha")
        reg = DeviceRegistry()
        coop = reg.update("coop", "main-coop", {"name": "Main Coop"})
        solar = reg.update("solar", "barn-solar", {"name": "Barn Solar"})
        disc.announce_device(coop)
        disc.announce_device(solar)
        n = len(sent)
        disc.announce_device(coop)
        assert len(sent) == n  # not re-announced
        door = json.loads(sent["ha/cover/gatemonitor/coop_main_coop_door/config"])
        assert door["command_topic"] == "coop/main-coop/command"
        assert door["state_topic"] == "coop/main-coop/state"
        yield_cfg = json.loads(sent["ha/sensor/gatemonitor/solar_barn_solar_yield_today/config"])
        assert yield_cfg["state_class"] == "total_increasing"
        assert yield_cfg["device_class"] == "energy"

    def test_gate_state_published_on_change_only(self) -> None:
        sent, publish = _collect()
        calls = []

        def counting(topic, payload, retain):
            calls.append(topic)
            return publish(topic, payload, retain)

        disc = HomeAssistantDiscovery(counting)
        st = GateStatus(state=GateState.CLOSED, online=True)
        disc.publish_gate_state(st, None, True)
        disc.publish_gate_state(st, None, True)
        assert calls.count(TOPIC_GATE_COVER) == 1
        assert sent[TOPIC_GATE_COVER] == "closed"
