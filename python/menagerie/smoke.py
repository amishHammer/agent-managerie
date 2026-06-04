"""Small smoke-test helper for the Docker Compose stack."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from .events import dumps, env_value, normalize_hook_event, state_document, topics_for
from .publisher import client_from_settings, mqtt_settings


def publish() -> int:
    if not env_value("MENAGERIE_SMOKE_KEEP_CLIENT_ID", "CODEX_PET_SMOKE_KEEP_CLIENT_ID"):
        os.environ["MQTT_CLIENT_ID"] = env_value("MENAGERIE_SMOKE_CLIENT_ID", "CODEX_PET_SMOKE_CLIENT_ID") or "menagerie-smoke"
    raw = {
        "hook_event_name": "SessionStart",
        "session_id": env_value("MENAGERIE_SMOKE_SESSION", "CODEX_PET_SMOKE_SESSION") or "smoke-session",
        "cwd": env_value("MENAGERIE_SMOKE_CWD", "CODEX_PET_SMOKE_CWD") or "/tmp/menagerie-smoke",
        "source": "startup",
        "model": "smoke",
    }
    event = normalize_hook_event(raw)
    client = client_from_settings(mqtt_settings(prefix="MQTT"))
    client.connect()
    try:
        event_topic, state_topic = topics_for(event)
        client.publish(event_topic, dumps(event), qos=1, retain=False)
        client.publish(state_topic, dumps(state_document(event)), qos=1, retain=True)
    finally:
        client.disconnect()
    print(dumps(event))
    return 0


def status() -> int:
    url = os.environ.get("COLLECTOR_STATUS_URL", "http://localhost:8080/v1/status")
    with urllib.request.urlopen(url, timeout=5) as response:
        payload = response.read().decode("utf-8")
    parsed = json.loads(payload)
    print(json.dumps(parsed, indent=2, sort_keys=True))
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "publish"
    if command == "publish":
        return publish()
    if command == "status":
        return status()
    print("usage: python -m menagerie.smoke [publish|status]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
