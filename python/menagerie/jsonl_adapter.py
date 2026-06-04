"""Publish `codex exec --json` JSONL events to Menagerie MQTT."""

from __future__ import annotations

import json
import os
import sys

from .events import (
    dumps,
    env_bool,
    env_value,
    health_document,
    health_topic,
    normalize_jsonl_event,
    state_document,
    topics_for,
    workspace_id_for,
)
from .publisher import client_from_settings, mqtt_settings


def main() -> int:
    settings = mqtt_settings()
    workspace_id = env_value("MENAGERIE_WORKSPACE_ID", "CODEX_PET_WORKSPACE_ID") or workspace_id_for(os.getcwd())
    session_id: str | None = None
    passthrough = env_bool("MENAGERIE_PASSTHROUGH", "CODEX_PET_PASSTHROUGH")

    try:
        client = client_from_settings(settings)
        client.connect()
    except Exception as exc:
        print(f"codex-menagerie-jsonl could not connect to MQTT broker: {exc}", file=sys.stderr)
        for line in sys.stdin:
            if passthrough:
                sys.stdout.write(line)
        return 0

    try:
        client.publish(
            health_topic(settings.client_id),
            dumps(health_document(settings.client_id)),
            qos=1,
            retain=True,
        )
        for line in sys.stdin:
            if passthrough:
                sys.stdout.write(line)
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            thread_id = raw.get("thread_id") or raw.get("threadId")
            if thread_id:
                session_id = str(thread_id)
            event = normalize_jsonl_event(raw, workspace_id=workspace_id, session_id=session_id)
            event_topic, state_topic = topics_for(event)
            client.publish(event_topic, dumps(event), qos=1, retain=False)
            if event.get("state"):
                client.publish(state_topic, dumps(state_document(event)), qos=1, retain=True)
    finally:
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
