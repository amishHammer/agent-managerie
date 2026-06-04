# SPDX-License-Identifier: AGPL-3.0-only
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from menagerie.collector import EventStore, handle_message
from menagerie.mqtt import PublishMessage


def _message(topic: str, payload: bytes) -> PublishMessage:
    return PublishMessage(topic=topic, payload=payload, qos=1, retain=True, packet_id=None)


class CollectorTests(unittest.TestCase):
    def test_empty_retained_state_payload_removes_current_state_without_log_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.sqlite3")
            event = {
                "id": "event-1",
                "ts": "2026-06-04T02:00:00.000Z",
                "source": "test",
                "workspaceId": "menagerie",
                "sessionId": "session-1",
                "state": "thinking",
                "summary": "Thinking",
            }
            topic = "menagerie/v1/state/menagerie/session-1"
            handle_message(store, _message(topic, json.dumps(event).encode("utf-8")))
            self.assertEqual(len(store.states(workspace_id="menagerie")), 1)

            with patch("sys.stdout", new_callable=StringIO) as stdout:
                handle_message(store, _message(topic, b""))

            self.assertEqual(store.states(workspace_id="menagerie"), [])
            self.assertEqual(stdout.getvalue(), "")

    def test_empty_retained_health_payload_is_not_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp, patch("sys.stdout", new_callable=StringIO) as stdout:
            store = EventStore(Path(tmp) / "events.sqlite3")
            handle_message(
                store,
                _message("menagerie/v1/health/session/menagerie/session-1", b""),
            )
            self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
