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

Hook configuration can be installed either for one working directory or globally.

### Working Directory Hooks

Use working-directory hooks when only one project should publish Menagerie events. Add a project-local Codex config:

```toml
# .codex/config.toml
[features]
hooks = true
```

Then add `.codex/hooks.json` for that project. Codex discovers `hooks.json` next to active config layers. The hook definitions can mirror `plugins/codex-menagerie-events/hooks/hooks.json`, but each `command` should point at this repository's hook wrapper:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "/absolute/path/to/menagerie/bin/codex-menagerie-hook",
            "timeout": 10,
            "statusMessage": "Publishing Menagerie session status"
          }
        ]
      }
    ]
  }
}
```

Repeat the same command shape for the other supported events listed above, or start by copying the plugin `hooks.json` and replacing the `command` values.

### Global Hooks

Use global hooks when every Codex project on the machine should publish Menagerie events. Enable hooks in your global Codex config:

```toml
# ~/.codex/config.toml
[features]
hooks = true
```

Then put the Menagerie hook definitions in `~/.codex/hooks.json`, again with `command` values pointing at an absolute `bin/codex-menagerie-hook` path.

When using global hooks, set `MENAGERIE_WORKSPACE_ID` per shell or per project launch if you want stable, human-readable workspace names. If it is unset, Menagerie derives a workspace id from the current working directory.

Codex requires non-managed command hooks to be reviewed and trusted. Use `/hooks` in Codex after adding or changing either working-directory or global hook configuration.

Hook payloads redact prompts, commands, and assistant text by default. Set `MENAGERIE_INCLUDE_TEXT=true` only for trusted test brokers. Set `MENAGERIE_INCLUDE_RAW=true` only for local debugging.

Menagerie does not rely on a Codex session-end hook. Instead, retained session state includes timeout metadata that lets the desktop app infer idle, dead, and exited gremlins. Tune it with:

- `MENAGERIE_IDLE_AFTER_SECONDS`, default `120`
- `MENAGERIE_DEAD_AFTER_SECONDS`, default `900`
- `MENAGERIE_EXITED_AFTER_SECONDS`, default `3600`

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
