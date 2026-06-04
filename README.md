<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# Menagerie

Menagerie is a Codex activity companion prototype. Each Codex session is tracked internally as a session and shown in the desktop app as a little gremlin.

- Remote MQTT broker and collector service via `docker compose up`.
- Codex hook publisher plugin for lifecycle events.
- `codex exec --json` adapter for non-interactive runs.
- Native SwiftUI macOS app with a transparent floating gremlin overlay.

The broker is intentionally standard MQTT. Hooks publish redacted session event envelopes, the app subscribes as a limited client, and the collector sidecar stores recent history in SQLite.

## Run The Broker

For local development:

```sh
docker compose up --build
```

After changing broker ACLs or the Mosquitto entrypoint, rebuild and recreate the containers. A plain `docker compose restart` reuses the old image:

```sh
docker compose up --build -d mqtt collector
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

## Friendly Session Names

### Install The Skill

The recommended path is to install the bundled Codex plugin; the skill is installed with it because the plugin manifest declares `skills: "./skills/"`.

From this checkout:

```sh
codex plugin marketplace add /absolute/path/to/menagerie
codex plugin add codex-menagerie-events --marketplace menagerie-local
```

Restart Codex after installing the plugin. The skill is then available as:

```text
$menagerie-session-name Menagerie-dev
```

For a skill-only personal install, put the deterministic CLI on `PATH` and link the skill into your Codex skills directory:

```sh
mkdir -p ~/.local/bin ~/.codex/skills
ln -sfn /absolute/path/to/menagerie/bin/codex-menagerie-name ~/.local/bin/codex-menagerie-name
ln -sfn /absolute/path/to/menagerie/plugins/codex-menagerie-events/skills/menagerie-session-name ~/.codex/skills/menagerie-session-name
```

Restart Codex after linking the skill. Use the full plugin install when you also want lifecycle hooks.

Publish a retained friendly name for the current Codex session with the deterministic CLI:

```sh
./bin/codex-menagerie-name "Bug Hunt"
```

In Codex, invoke the bundled skill for the same operation:

```text
$menagerie-session-name Menagerie-dev
```

When run from inside Codex, the command uses `CODEX_THREAD_ID` as the session id. Outside Codex, pass the target explicitly:

```sh
./bin/codex-menagerie-name --workspace-id demo --session-id demo-session "Bug Hunt"
./bin/codex-menagerie-name --workspace-id demo --session-id demo-session --clear
```

The command writes `menagerie.sessionProfile.v1` to `menagerie/v1/profile/session/{workspaceId}/{sessionId}` with MQTT retain enabled. The broker user configured in `MENAGERIE_MQTT_USERNAME` needs write access to `profile/#`; the Compose `codex-hook` and `menagerie-app` users have that access.

Menagerie does not parse arbitrary prompt text to set names. Use the CLI or the explicit Codex skill invocation so naming is intentional.

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

The app is a menu-bar SwiftUI app with a transparent floating gremlin panel. Configure it with the app credentials:

- host: your broker host
- port: `1883` for dev or `8883` for TLS deployments
- username: `menagerie-app`
- password: the app password
- workspace: `#` for all workspaces or a concrete workspace id

Passwords are stored in the macOS keychain.

The Compose `menagerie-app` user can read `events/#`, and can read/write `state/#`, `health/#`, and `profile/#`. The state and health writes let the macOS app publish retained deletes for stale UI-owned state and heartbeat records. It cannot publish Codex lifecycle events.

## Collector API

The collector subscribes to `menagerie/v1/events/#`, `state/#`, `health/#`, and `profile/#`.

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
