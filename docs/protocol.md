<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# MQTT Protocol

Menagerie uses MQTT 3.1.1 for v1.

## Topics

- `menagerie/v1/events/{workspaceId}/{sessionId}`: append-only lifecycle events.
- `menagerie/v1/state/{workspaceId}/{sessionId}`: retained current session state.
- `menagerie/v1/health/{clientId}`: retained client heartbeat.

Publishers use QoS 1. State and health messages are retained; event messages are not retained.

## Formal Model

The protocol uses `session` as the formal model name. Desktop copy may call sessions "gremlins", but MQTT topics, JSON fields, database columns, and HTTP filters use `sessionId`.

## Envelope

```json
{
  "id": "uuid",
  "ts": "2026-06-04T02:00:00.000Z",
  "source": "codex-hook",
  "kind": "codex.hook.preToolUse",
  "severity": "info",
  "workspaceId": "my-workspace",
  "sessionId": "session-id",
  "turnId": "turn-id",
  "cwdHash": "sha256-prefix",
  "model": "gpt-5.5",
  "state": "runningTool",
  "summary": "Tool use starting: Bash",
  "payload": {
    "rawKeys": ["cwd", "hook_event_name", "tool_input", "tool_name"],
    "toolName": "Bash",
    "toolCommandHash": "sha256-prefix"
  }
}
```

## States

- `idle`
- `starting`
- `thinking`
- `runningTool`
- `waitingForPermission`
- `compacting`
- `readyForReview`
- `error`

## Authentication

The Compose broker creates three users:

- `codex-hook`: write-only access to `events/#`, `state/#`, and `health/#`.
- `menagerie-app`: read-only access to `events/#`, `state/#`, and `health/#`.
- `codex-collector`: read-only access to `events/#`, `state/#`, and `health/#`.

For production, expose MQTT over TLS and replace every default password.

## Privacy Defaults

The hook emitter does not publish raw prompts, commands, assistant output, or transcript paths by default. It publishes hashes and key summaries so the app can show session state without leaking content to a shared broker.

Opt-in debugging flags:

- `MENAGERIE_INCLUDE_TEXT=true`: include redacted text previews.
- `MENAGERIE_INCLUDE_RAW=true`: include redacted raw hook input.
