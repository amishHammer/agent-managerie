<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# MQTT Protocol

Menagerie uses MQTT 3.1.1 for v1.

## Topics

- `menagerie/v1/events/{workspaceId}/{sessionId}`: append-only lifecycle events.
- `menagerie/v1/state/{workspaceId}/{sessionId}`: retained current session state.
- `menagerie/v1/health/{clientId}`: retained client heartbeat.
- `menagerie/v1/health/session/{workspaceId}/{sessionId}`: retained per-session heartbeat and timeout metadata.

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
  "lifecycle": {
    "schema": "menagerie.lifecycle.v1",
    "status": "active",
    "lastSeenAt": "2026-06-04T02:00:00.000Z",
    "idleAfter": "2026-06-04T02:02:00.000Z",
    "deadAfter": "2026-06-04T02:15:00.000Z",
    "exitedAfter": "2026-06-04T03:00:00.000Z",
    "idleState": "idle",
    "deadState": "dead",
    "exitedState": "exited",
    "inference": "timeout",
    "reason": "activityObserved"
  },
  "streamItem": {
    "schema": "menagerie.streamItem.v1",
    "kind": "tool.started",
    "role": "tool",
    "state": "runningTool",
    "severity": "info",
    "tone": "active",
    "icon": "terminal",
    "title": "Tool work started",
    "body": "The gremlin started using Bash.",
    "subject": "Bash",
    "contentRedacted": true,
    "refs": {
      "toolCommandHash": "sha256-prefix"
    }
  },
  "payload": {
    "rawKeys": ["cwd", "hook_event_name", "tool_input", "tool_name"],
    "toolName": "Bash",
    "toolCommandHash": "sha256-prefix"
  }
}
```

## Stream Items

Hook events include `streamItem`, a render-ready activity item for desktop timelines. This is not model private chain-of-thought. It is a redacted activity narrative derived from public hook metadata.

Fields:

- `schema`: currently `menagerie.streamItem.v1`.
- `kind`: event category such as `prompt.submitted`, `tool.started`, `permission.requested`, `tool.completed`, `context.compacting`, or `turn.completed`.
- `role`: `user`, `codex`, `tool`, or `system`.
- `state`, `severity`: mirrors the event state/severity.
- `tone`: UI hint such as `active`, `neutral`, `attention`, `warning`, or `success`.
- `icon`: symbolic UI hint.
- `title`, `body`: short text suitable for a feed row.
- `subject`: optional tool name, trigger, or other focus object.
- `context`: optional small metadata such as `exitCode`, `trigger`, or `agentType`.
- `refs`: optional hashes and identifiers that let the UI correlate entries without raw content.
- `preview`: optional redacted text preview, only emitted when `MENAGERIE_INCLUDE_TEXT=true`.
- `contentRedacted`: true when raw prompt/tool/assistant content was withheld.

Retained state messages include `lastStreamItem`, copied from the latest event for that session.

## Session Lifecycle

Hook events and retained state messages include `lifecycle`, which lets clients infer state when no new hook arrives. Codex does not currently provide a first-class session-end hook, so `dead` and `exited` are timeout-based display states.

Clients can classify a gremlin with local clock time:

- before `idleAfter`: use `lifecycle.status`.
- at or after `idleAfter`: show `idle`.
- at or after `deadAfter`: show `dead`.
- at or after `exitedAfter`: show `exited`.

`Stop` and `SubagentStop` events set `lifecycle.status` to `idle` immediately. Other hook activity starts as `active`.

Timeouts are configurable for hook publishers:

- `MENAGERIE_IDLE_AFTER_SECONDS`: default `120`.
- `MENAGERIE_DEAD_AFTER_SECONDS`: default `900`.
- `MENAGERIE_EXITED_AFTER_SECONDS`: default `3600`.

The publisher also emits retained session heartbeat documents to `menagerie/v1/health/session/{workspaceId}/{sessionId}`:

```json
{
  "schema": "menagerie.sessionHealth.v1",
  "workspaceId": "my-workspace",
  "sessionId": "session-id",
  "sessionState": "runningTool",
  "summary": "Tool use starting: Bash",
  "lastEventKind": "codex.hook.preToolUse",
  "lifecycle": {
    "schema": "menagerie.lifecycle.v1",
    "status": "active",
    "lastSeenAt": "2026-06-04T02:00:00.000Z",
    "idleAfter": "2026-06-04T02:02:00.000Z",
    "deadAfter": "2026-06-04T02:15:00.000Z",
    "exitedAfter": "2026-06-04T03:00:00.000Z"
  }
}
```

## States

- `idle`
- `dead` (inferred display state)
- `exited` (inferred display state)
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

The hook emitter does not publish raw prompts, commands, assistant output, or transcript paths by default. It publishes hashes, key summaries, and synthetic `streamItem` text so the app can show session state without leaking content to a shared broker.

Opt-in debugging flags:

- `MENAGERIE_INCLUDE_TEXT=true`: include redacted text previews.
- `MENAGERIE_INCLUDE_RAW=true`: include redacted raw hook input.
