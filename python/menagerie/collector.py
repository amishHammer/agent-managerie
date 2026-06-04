# SPDX-License-Identifier: AGPL-3.0-only
"""MQTT event collector with a tiny HTTP backfill API."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .events import EVENT_TOPIC_PREFIX, HEALTH_TOPIC_PREFIX, PROFILE_TOPIC_PREFIX, STATE_TOPIC_PREFIX, dumps
from .mqtt import PublishMessage
from .publisher import client_from_settings, mqtt_settings


class EventStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT NOT NULL,
                    workspace_id TEXT,
                    session_id TEXT,
                    kind TEXT,
                    severity TEXT,
                    state TEXT,
                    summary TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS current_state (
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    state TEXT,
                    severity TEXT,
                    summary TEXT,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, session_id)
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_workspace_session ON events(workspace_id, session_id, ts)"
            )

    def add(self, topic: str, event: dict[str, Any]) -> None:
        event_id = str(event.get("id") or f"collector-{time.time_ns()}")
        workspace_id = event.get("workspaceId")
        session_id = event.get("sessionId")
        payload = dumps(event)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO events
                (id, ts, topic, workspace_id, session_id, kind, severity, state, summary, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    str(event.get("ts") or ""),
                    topic,
                    workspace_id,
                    session_id,
                    event.get("kind") or event.get("lastEventKind"),
                    event.get("severity"),
                    event.get("state"),
                    event.get("summary"),
                    payload,
                ),
            )
            if workspace_id and session_id and ("/state/" in topic or event.get("state")):
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO current_state
                    (workspace_id, session_id, ts, topic, state, severity, summary, event_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_id,
                        session_id,
                        str(event.get("ts") or ""),
                        topic,
                        event.get("state"),
                        event.get("severity"),
                        event.get("summary"),
                        payload,
                    ),
                )

    def delete_retained(self, topic: str) -> None:
        state_target = _topic_workspace_session(topic, STATE_TOPIC_PREFIX)
        if not state_target:
            return
        workspace_id, session_id = state_target
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM current_state WHERE workspace_id = ? AND session_id = ?",
                (workspace_id, session_id),
            )

    def recent(self, *, limit: int, workspace_id: str | None, session_id: str | None) -> list[dict[str, Any]]:
        query = "SELECT payload_json FROM events"
        clauses = []
        values: list[Any] = []
        if workspace_id:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY ts DESC LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._conn.execute(query, values).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def states(self, *, workspace_id: str | None) -> list[dict[str, Any]]:
        query = "SELECT event_json FROM current_state"
        values: list[Any] = []
        if workspace_id:
            query += " WHERE workspace_id = ?"
            values.append(workspace_id)
        query += " ORDER BY ts DESC"
        with self._lock:
            rows = self._conn.execute(query, values).fetchall()
        return [json.loads(row["event_json"]) for row in rows]


class CollectorHandler(BaseHTTPRequestHandler):
    store: EventStore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self._json({"ok": True})
            return
        if parsed.path == "/v1/events/recent":
            limit = min(int(query.get("limit", ["100"])[0]), 500)
            self._json(
                {
                    "events": self.store.recent(
                        limit=limit,
                        workspace_id=_one(query, "workspaceId"),
                        session_id=_one(query, "sessionId"),
                    )
                }
            )
            return
        if parsed.path == "/v1/status":
            self._json({"states": self.store.states(workspace_id=_one(query, "workspaceId"))})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("COLLECTOR_HTTP_LOGS", "").lower() in {"1", "true", "yes"}:
            super().log_message(format, *args)

    def _json(self, value: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def run_http(store: EventStore) -> None:
    host = os.environ.get("COLLECTOR_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("COLLECTOR_HTTP_PORT", "8080"))
    CollectorHandler.store = store
    server = ThreadingHTTPServer((host, port), CollectorHandler)
    print(f"collector HTTP listening on {host}:{port}", flush=True)
    server.serve_forever()


def run_mqtt(store: EventStore) -> None:
    topics = [
        (f"{EVENT_TOPIC_PREFIX}/#", 1),
        (f"{STATE_TOPIC_PREFIX}/#", 1),
        (f"{HEALTH_TOPIC_PREFIX}/#", 1),
        (f"{PROFILE_TOPIC_PREFIX}/#", 1),
    ]
    while True:
        try:
            settings = mqtt_settings(prefix="MQTT")
            client = client_from_settings(settings)
            client.connect()
            client.subscribe(topics)
            print(f"collector subscribed to MQTT at {settings.host}:{settings.port}", flush=True)

            def on_message(message: PublishMessage) -> None:
                handle_message(store, message)

            client.loop_forever(on_message)
        except Exception as exc:
            print(f"collector MQTT connection failed: {exc}; retrying", flush=True)
            time.sleep(5)


def handle_message(store: EventStore, message: PublishMessage) -> None:
    if not message.payload:
        store.delete_retained(message.topic)
        return
    try:
        event = json.loads(message.payload.decode("utf-8"))
    except Exception as exc:
        print(f"collector ignored invalid payload on {message.topic}: {exc}", flush=True)
        return
    if isinstance(event, dict):
        store.add(message.topic, event)


def _topic_workspace_session(topic: str, prefix: str) -> tuple[str, str] | None:
    normalized_prefix = prefix.strip("/")
    if not topic.startswith(f"{normalized_prefix}/"):
        return None
    tail = topic[len(normalized_prefix) + 1 :].split("/")
    if len(tail) < 2:
        return None
    return tail[0], tail[1]


def main() -> int:
    db_path = Path(os.environ.get("COLLECTOR_DB", "/data/menagerie-events.sqlite3"))
    store = EventStore(db_path)
    threading.Thread(target=run_http, args=(store,), daemon=True).start()
    run_mqtt(store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
