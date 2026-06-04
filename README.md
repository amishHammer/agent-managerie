<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# Menagerie

Menagerie is a Codex activity companion prototype. Each Codex session is tracked internally as a session and shown in the desktop app as a little gremlin.

- Remote MQTT broker and collector service via `docker compose up`.
- Codex hook publisher plugin for lifecycle events.
- `codex exec --json` adapter for non-interactive runs.
- Native SwiftUI macOS app with a transparent floating gremlin overlay.

The broker is intentionally standard MQTT. Hooks publish redacted session event envelopes, the app subscribes as a read-only client, and the collector sidecar stores recent history in SQLite.

## Run The Broker

For local development:

```sh
docker compose up --build
```

This starts:

- Mosquitto on `localhost:1883`
- Collector HTTP API on `localhost:18080`

Default development credentials are built into `docker-compose.yml` so the stack starts without a setup step. For real hosts, copy `.env.example` to `.env`, change every password, and put TLS in front of MQTT or mount a TLS listener config.

## Publish A Test Event

```sh
export MENAGERIE_MQTT_HOST=localhost
export MENAGERIE_MQTT_PORT=1883
export MENAGERIE_MQTT_USERNAME=codex-hook
export MENAGERIE_MQTT_PASSWORD=dev-hook-password
export MENAGERIE_WORKSPACE_ID=demo

printf '%s\n' '{"hook_event_name":"SessionStart","session_id":"demo-session","cwd":"/tmp/demo","source":"startup"}' \
  | ./bin/codex-menagerie-hook

curl -s http://localhost:18080/v1/status
```

## Codex Hook Integration

The plugin lives at `plugins/codex-menagerie-events`. It publishes:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `Stop`

Set these environment variables before launching Codex:

```sh
export MENAGERIE_MQTT_HOST=broker.example.com
export MENAGERIE_MQTT_PORT=8883
export MENAGERIE_MQTT_TLS=true
export MENAGERIE_MQTT_USERNAME=codex-hook
export MENAGERIE_MQTT_PASSWORD='...'
export MENAGERIE_WORKSPACE_ID=my-workspace
```

For local development against Compose, use port `1883`, `MENAGERIE_MQTT_TLS=false`, and the dev hook password.

Hook payloads redact prompts, commands, and assistant text by default. Set `MENAGERIE_INCLUDE_TEXT=true` only for trusted test brokers. Set `MENAGERIE_INCLUDE_RAW=true` only for local debugging.

## Non-Interactive Adapter

Pipe `codex exec --json` into the JSONL adapter:

```sh
codex exec --json "summarize this repository" | ./bin/codex-menagerie-jsonl
```

Set `MENAGERIE_PASSTHROUGH=true` if another command should also receive the original JSONL stream.

## macOS App

Open the package in Xcode on macOS:

```sh
open macos/Menagerie/Package.swift
```

The app is a menu-bar SwiftUI app with a transparent floating gremlin panel. Configure it with the read-only app credentials:

- host: your broker host
- port: `1883` for dev or `8883` for TLS deployments
- username: `menagerie-app`
- password: the app password
- workspace: `#` for all workspaces or a concrete workspace id

Passwords are stored in the macOS keychain.

## Collector API

The collector subscribes to `menagerie/v1/events/#`, `state/#`, and `health/#`.

```sh
curl http://localhost:18080/health
curl http://localhost:18080/v1/status
curl 'http://localhost:18080/v1/events/recent?workspaceId=demo&limit=20'
```

## Test

```sh
PYTHONPATH=python python3 -m unittest discover -s tests
```

## License

Menagerie is licensed under `AGPL-3.0-only`. See [LICENSE](LICENSE).
