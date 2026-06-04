# SPDX-License-Identifier: AGPL-3.0-only
"""Event normalization for Menagerie MQTT messages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TOPIC_ROOT = os.environ.get("MENAGERIE_TOPIC_ROOT", "menagerie/v1").strip("/")
EVENT_TOPIC_PREFIX = f"{TOPIC_ROOT}/events"
STATE_TOPIC_PREFIX = f"{TOPIC_ROOT}/state"
HEALTH_TOPIC_PREFIX = f"{TOPIC_ROOT}/health"
PROFILE_TOPIC_PREFIX = f"{TOPIC_ROOT}/profile"
DEFAULT_IDLE_AFTER_SECONDS = 120
DEFAULT_DEAD_AFTER_SECONDS = 900
DEFAULT_EXITED_AFTER_SECONDS = 3600

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(r"([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*=\s*)\S+", re.IGNORECASE),
]

EVENT_ALIASES = {
    "sessionstart": "sessionStart",
    "userpromptsubmit": "userPromptSubmit",
    "pretooluse": "preToolUse",
    "permissionrequest": "permissionRequest",
    "posttooluse": "postToolUse",
    "precompact": "preCompact",
    "postcompact": "postCompact",
    "subagentstart": "subagentStart",
    "subagentstop": "subagentStop",
    "stop": "stop",
}

STATE_BY_HOOK_EVENT = {
    "sessionStart": "starting",
    "userPromptSubmit": "thinking",
    "preToolUse": "runningTool",
    "permissionRequest": "waitingForPermission",
    "postToolUse": "thinking",
    "preCompact": "compacting",
    "postCompact": "thinking",
    "subagentStart": "thinking",
    "subagentStop": "readyForReview",
    "stop": "readyForReview",
}

SUMMARY_BY_HOOK_EVENT = {
    "sessionStart": "Codex session started",
    "userPromptSubmit": "Prompt submitted",
    "preToolUse": "Tool use starting",
    "permissionRequest": "Permission requested",
    "postToolUse": "Tool use completed",
    "preCompact": "Conversation compaction starting",
    "postCompact": "Conversation compacted",
    "subagentStart": "Subagent started",
    "subagentStop": "Subagent stopped",
    "stop": "Turn stopped",
}

STREAM_BY_HOOK_EVENT = {
    "sessionStart": {
        "kind": "session.started",
        "role": "system",
        "title": "A gremlin woke up",
        "body": "A Codex session started.",
        "icon": "sparkles",
        "tone": "active",
    },
    "userPromptSubmit": {
        "kind": "prompt.submitted",
        "role": "user",
        "title": "A prompt landed",
        "body": "The gremlin is thinking over the latest prompt.",
        "icon": "message",
        "tone": "active",
    },
    "preToolUse": {
        "kind": "tool.started",
        "role": "tool",
        "title": "Tool work started",
        "body": "The gremlin reached for a tool.",
        "icon": "terminal",
        "tone": "active",
    },
    "permissionRequest": {
        "kind": "permission.requested",
        "role": "tool",
        "title": "Permission needed",
        "body": "The gremlin needs permission before continuing.",
        "icon": "lock",
        "tone": "attention",
    },
    "postToolUse": {
        "kind": "tool.completed",
        "role": "tool",
        "title": "Tool work finished",
        "body": "The gremlin put the tool away.",
        "icon": "check",
        "tone": "neutral",
    },
    "preCompact": {
        "kind": "context.compacting",
        "role": "system",
        "title": "Packing context",
        "body": "The gremlin is compressing the conversation.",
        "icon": "archive",
        "tone": "active",
    },
    "postCompact": {
        "kind": "context.compacted",
        "role": "system",
        "title": "Context packed",
        "body": "The gremlin finished compressing the conversation.",
        "icon": "archive",
        "tone": "neutral",
    },
    "subagentStart": {
        "kind": "subagent.started",
        "role": "codex",
        "title": "A helper joined",
        "body": "A subagent started working in the background.",
        "icon": "users",
        "tone": "active",
    },
    "subagentStop": {
        "kind": "subagent.stopped",
        "role": "codex",
        "title": "A helper wrapped up",
        "body": "A subagent finished its work.",
        "icon": "users",
        "tone": "neutral",
    },
    "stop": {
        "kind": "turn.completed",
        "role": "codex",
        "title": "Ready for review",
        "body": "The gremlin is ready for you to look things over.",
        "icon": "flag",
        "tone": "success",
    },
}

STATE_BY_JSONL_TYPE = {
    "thread.started": "starting",
    "turn.started": "thinking",
    "turn.completed": "readyForReview",
    "turn.failed": "error",
    "error": "error",
}


def now_iso() -> str:
    return to_iso(datetime.now(timezone.utc))


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def stable_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def topic_segment(value: Any, fallback: str = "unknown") -> str:
    text = str(value or fallback)
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "-", text).strip("-")
    return text[:96] or fallback


def redact_text(value: str, *, limit: int = 240) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]" if m.groups() else "[REDACTED]", redacted)
    redacted = redacted.replace("\r", " ").replace("\n", " ")
    if len(redacted) > limit:
        return redacted[: limit - 1] + "…"
    return redacted


def redact_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_json(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            if re.search(r"(token|secret|password|api[_-]?key|authorization)", str(key), re.IGNORECASE):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = redact_json(item, depth=depth + 1)
        return out
    return value


def env_value(name: str, legacy_name: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if legacy_name:
        return os.environ.get(legacy_name)
    return None


def env_bool(name: str, legacy_name: str | None = None) -> bool:
    return str(env_value(name, legacy_name) or "").lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, legacy_name: str | None = None) -> int:
    value = env_value(name, legacy_name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(parsed, 0)


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def cwd_from_raw(raw: dict[str, Any]) -> str:
    return str(raw.get("cwd") or os.environ.get("PWD") or os.getcwd())


def workspace_id_for(cwd: str) -> str:
    configured = env_value("MENAGERIE_WORKSPACE_ID", "CODEX_PET_WORKSPACE_ID")
    if configured:
        return topic_segment(configured, "workspace")
    name = Path(cwd).name or "workspace"
    return topic_segment(f"{name}-{stable_hash(cwd, 8)}", "workspace")


def cwd_hash(cwd: str) -> str:
    return stable_hash(str(Path(cwd).expanduser()), 16)


def canonical_hook_event(raw: dict[str, Any]) -> str:
    value = (
        raw.get("hook_event_name")
        or raw.get("hookEventName")
        or raw.get("eventName")
        or raw.get("event")
        or "unknown"
    )
    normalized = re.sub(r"[^A-Za-z0-9]", "", str(value)).lower()
    return EVENT_ALIASES.get(normalized, str(value))


def session_id_from(raw: dict[str, Any], *, fallback: str) -> str:
    value = (
        raw.get("session_id")
        or raw.get("sessionId")
        or raw.get("thread_id")
        or raw.get("threadId")
        or env_value("MENAGERIE_SESSION_ID", "CODEX_PET_SESSION_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or fallback
    )
    return topic_segment(value, "unknown")


def turn_id_from(raw: dict[str, Any]) -> str | None:
    value = raw.get("turn_id") or raw.get("turnId")
    return str(value) if value else None


def hook_summary(event_name: str, raw: dict[str, Any]) -> str:
    summary = SUMMARY_BY_HOOK_EVENT.get(event_name, f"Codex hook {event_name}")
    tool_name = raw.get("tool_name") or raw.get("toolName")
    if tool_name and event_name in {"preToolUse", "permissionRequest", "postToolUse"}:
        summary = f"{summary}: {tool_name}"
    trigger = raw.get("trigger")
    if trigger and event_name in {"preCompact", "postCompact"}:
        summary = f"{summary}: {trigger}"
    source = raw.get("source")
    if source and event_name == "sessionStart":
        summary = f"{summary}: {source}"
    return redact_text(summary, limit=180)


def hook_severity(event_name: str, raw: dict[str, Any]) -> str:
    if event_name == "permissionRequest":
        return "attention"
    if event_name in {"subagentStop", "stop"} and raw.get("last_assistant_message") is None:
        return "info"
    if event_name == "postToolUse":
        tool_response = raw.get("tool_response") or raw.get("toolResponse")
        if isinstance(tool_response, dict) and tool_response.get("exit_code") not in (None, 0):
            return "warning"
    return "info"


def hook_payload(raw: dict[str, Any]) -> dict[str, Any]:
    include_text = env_bool("MENAGERIE_INCLUDE_TEXT", "CODEX_PET_INCLUDE_TEXT")
    include_raw = env_bool("MENAGERIE_INCLUDE_RAW", "CODEX_PET_INCLUDE_RAW")
    payload: dict[str, Any] = {
        "rawKeys": sorted(str(key) for key in raw.keys()),
    }
    for raw_key, out_key in [
        ("source", "source"),
        ("permission_mode", "permissionMode"),
        ("tool_name", "toolName"),
        ("tool_use_id", "toolUseId"),
        ("trigger", "trigger"),
        ("agent_id", "agentId"),
        ("agent_type", "agentType"),
    ]:
        if raw_key in raw:
            payload[out_key] = redact_json(raw[raw_key])
    tool_input = raw.get("tool_input") or raw.get("toolInput")
    if isinstance(tool_input, dict):
        payload["toolInputKeys"] = sorted(str(key) for key in tool_input.keys())
        if include_text:
            payload["toolInputPreview"] = redact_json(tool_input)
        elif "command" in tool_input:
            payload["toolCommandHash"] = stable_hash(str(tool_input.get("command")), 16)
    prompt = raw.get("prompt")
    if isinstance(prompt, str):
        payload["promptHash"] = stable_hash(prompt, 16)
        if include_text:
            payload["promptPreview"] = redact_text(prompt)
    last_message = raw.get("last_assistant_message") or raw.get("lastAssistantMessage")
    if isinstance(last_message, str):
        payload["lastAssistantMessageHash"] = stable_hash(last_message, 16)
        if include_text:
            payload["lastAssistantMessagePreview"] = redact_text(last_message)
    if include_raw:
        payload["raw"] = redact_json(raw)
    return payload


def _tool_response(raw: dict[str, Any]) -> dict[str, Any] | None:
    response = raw.get("tool_response") or raw.get("toolResponse")
    return response if isinstance(response, dict) else None


def _exit_code(raw: dict[str, Any]) -> int | None:
    response = _tool_response(raw)
    if not response:
        return None
    value = response.get("exit_code") if "exit_code" in response else response.get("exitCode")
    return value if isinstance(value, int) else None


def _string_payload_value(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value:
            return str(value)
    return None


def hook_stream_item(
    event_name: str,
    raw: dict[str, Any],
    *,
    state: str,
    severity: str,
    summary: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    template = STREAM_BY_HOOK_EVENT.get(
        event_name,
        {
            "kind": f"hook.{event_name}",
            "role": "system",
            "title": "Codex activity",
            "body": summary,
            "icon": "activity",
            "tone": "neutral",
        },
    )
    tool_name = _string_payload_value(raw, "tool_name", "toolName")
    trigger = _string_payload_value(raw, "trigger")
    agent_type = _string_payload_value(raw, "agent_type", "agentType")
    exit_code = _exit_code(raw)
    refs: dict[str, Any] = {}
    for key in [
        "promptHash",
        "toolCommandHash",
        "lastAssistantMessageHash",
        "toolUseId",
        "agentId",
        "agentType",
        "trigger",
    ]:
        if key in payload:
            refs[key] = payload[key]
    item: dict[str, Any] = {
        "schema": "menagerie.streamItem.v1",
        "kind": template["kind"],
        "role": template["role"],
        "state": state,
        "severity": severity,
        "tone": stream_tone(event_name, severity, exit_code, str(template["tone"])),
        "icon": template["icon"],
        "title": template["title"],
        "body": template["body"],
        "contentRedacted": True,
    }
    if refs:
        item["refs"] = refs
    if tool_name:
        item["subject"] = tool_name
        item["body"] = stream_body_with_subject(event_name, str(template["body"]), tool_name, exit_code)
    if trigger:
        item["subject"] = trigger if not item.get("subject") else item["subject"]
        item["context"] = {"trigger": trigger}
    if agent_type:
        item.setdefault("context", {})["agentType"] = agent_type
    if exit_code is not None:
        item.setdefault("context", {})["exitCode"] = exit_code
    preview = stream_preview(payload)
    if preview:
        item["preview"] = preview
        item["contentRedacted"] = False
    return item


def stream_tone(event_name: str, severity: str, exit_code: int | None, default: str) -> str:
    if severity == "attention":
        return "attention"
    if severity == "warning" or (exit_code is not None and exit_code != 0):
        return "warning"
    if event_name in {"stop", "subagentStop"}:
        return "success"
    return default


def stream_body_with_subject(event_name: str, body: str, subject: str, exit_code: int | None) -> str:
    if event_name == "preToolUse":
        return f"The gremlin started using {subject}."
    if event_name == "permissionRequest":
        return f"The gremlin needs permission to use {subject}."
    if event_name == "postToolUse" and exit_code not in (None, 0):
        return f"{subject} finished with exit code {exit_code}."
    if event_name == "postToolUse":
        return f"The gremlin finished using {subject}."
    return body


def stream_preview(payload: dict[str, Any]) -> str | None:
    for key in ["promptPreview", "lastAssistantMessagePreview"]:
        value = payload.get(key)
        if isinstance(value, str):
            return value
    tool_preview = payload.get("toolInputPreview")
    if isinstance(tool_preview, dict):
        command = tool_preview.get("command")
        if isinstance(command, str):
            return redact_text(command, limit=180)
        keys = ", ".join(str(key) for key in tool_preview.keys())
        return f"Tool input: {keys}" if keys else None
    return None


def lifecycle_document(event_name: str, ts: str, state: str) -> dict[str, Any]:
    idle_seconds = env_int("MENAGERIE_IDLE_AFTER_SECONDS", DEFAULT_IDLE_AFTER_SECONDS)
    dead_seconds = env_int("MENAGERIE_DEAD_AFTER_SECONDS", DEFAULT_DEAD_AFTER_SECONDS)
    exited_seconds = env_int("MENAGERIE_EXITED_AFTER_SECONDS", DEFAULT_EXITED_AFTER_SECONDS)
    dead_seconds = max(dead_seconds, idle_seconds)
    exited_seconds = max(exited_seconds, dead_seconds)

    seen_at = parse_iso(ts)
    starts_idle = state in {"idle", "readyForReview"} or event_name in {"stop", "subagentStop"}
    idle_after = seen_at if starts_idle else seen_at + timedelta(seconds=idle_seconds)
    dead_after = seen_at + timedelta(seconds=dead_seconds)
    exited_after = seen_at + timedelta(seconds=exited_seconds)
    return {
        "schema": "menagerie.lifecycle.v1",
        "status": "idle" if starts_idle else "active",
        "lastSeenAt": ts,
        "idleAfter": to_iso(idle_after),
        "deadAfter": to_iso(dead_after),
        "exitedAfter": to_iso(exited_after),
        "idleState": "idle",
        "deadState": "dead",
        "exitedState": "exited",
        "inference": "timeout",
        "reason": "turnComplete" if starts_idle else "activityObserved",
    }


def normalize_hook_event(raw: dict[str, Any]) -> dict[str, Any]:
    cwd = cwd_from_raw(raw)
    workspace_id = workspace_id_for(cwd)
    session_id = session_id_from(raw, fallback=cwd_hash(cwd))
    event_name = canonical_hook_event(raw)
    state = STATE_BY_HOOK_EVENT.get(event_name, "thinking")
    severity = hook_severity(event_name, raw)
    summary = hook_summary(event_name, raw)
    payload = hook_payload(raw)
    ts = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "ts": ts,
        "source": "codex-hook",
        "kind": f"codex.hook.{event_name}",
        "severity": severity,
        "workspaceId": workspace_id,
        "sessionId": session_id,
        "turnId": turn_id_from(raw),
        "cwdHash": cwd_hash(cwd),
        "model": raw.get("model"),
        "state": state,
        "summary": summary,
        "lifecycle": lifecycle_document(event_name, ts, state),
        "streamItem": hook_stream_item(
            event_name,
            raw,
            state=state,
            severity=severity,
            summary=summary,
            payload=payload,
        ),
        "payload": payload,
    }


def normalize_jsonl_event(raw: dict[str, Any], *, workspace_id: str, session_id: str | None) -> dict[str, Any]:
    event_type = str(raw.get("type") or "unknown")
    thread_id = raw.get("thread_id") or raw.get("threadId")
    if thread_id:
        session_id = str(thread_id)
    session = topic_segment(session_id or "unknown", "unknown")
    state = STATE_BY_JSONL_TYPE.get(event_type)
    severity = "error" if event_type in {"error", "turn.failed"} else "info"
    summary = jsonl_summary(event_type, raw)
    ts = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "ts": ts,
        "source": "codex-exec-jsonl",
        "kind": f"codex.exec.{event_type}",
        "severity": severity,
        "workspaceId": topic_segment(workspace_id, "workspace"),
        "sessionId": session,
        "turnId": raw.get("turn_id") or raw.get("turnId"),
        "cwdHash": cwd_hash(os.getcwd()),
        "model": raw.get("model"),
        "state": state,
        "summary": summary,
        "lifecycle": lifecycle_document(event_type, ts, state) if state else None,
        "payload": redact_json(raw),
    }


def jsonl_summary(event_type: str, raw: dict[str, Any]) -> str:
    if event_type == "thread.started":
        return "Codex thread started"
    if event_type == "turn.started":
        return "Codex turn started"
    if event_type == "turn.completed":
        return "Codex turn completed"
    if event_type == "turn.failed":
        return "Codex turn failed"
    if event_type == "error":
        message = raw.get("message") or raw.get("error")
        return redact_text(f"Codex error: {message}" if message else "Codex error")
    if event_type.startswith("item."):
        item = raw.get("item")
        item_type = item.get("type") if isinstance(item, dict) else None
        return redact_text(f"Codex {event_type}: {item_type or 'item'}")
    return redact_text(f"Codex event: {event_type}")


def state_document(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "ts": event["ts"],
        "source": event["source"],
        "workspaceId": event["workspaceId"],
        "sessionId": event["sessionId"],
        "turnId": event.get("turnId"),
        "state": event.get("state") or "idle",
        "severity": event.get("severity") or "info",
        "summary": event.get("summary") or "",
        "lastEventKind": event.get("kind"),
        "lastStreamItem": event.get("streamItem"),
        "lifecycle": event.get("lifecycle"),
    }


def health_document(client_id: str, status: str = "online") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "ts": now_iso(),
        "source": "menagerie-client",
        "clientId": client_id,
        "host": socket.gethostname(),
        "status": status,
    }


def session_health_document(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{event['id']}:session-health",
        "ts": event["ts"],
        "source": event["source"],
        "schema": "menagerie.sessionHealth.v1",
        "kind": "menagerie.sessionHealth",
        "workspaceId": event["workspaceId"],
        "sessionId": event["sessionId"],
        "turnId": event.get("turnId"),
        "sessionState": event.get("state"),
        "summary": event.get("summary") or "",
        "lastEventKind": event.get("kind"),
        "lifecycle": event.get("lifecycle"),
    }


def session_profile_document(
    *,
    workspace_id: str,
    session_id: str,
    display_name: str | None,
    source: str = "menagerie-tool",
) -> dict[str, Any]:
    if display_name is None:
        sanitized_name = None
    else:
        sanitized_name = redact_text(display_name.strip(), limit=80) or None
    summary = "Session name cleared" if sanitized_name is None else f"Session named {sanitized_name}"
    return {
        "id": str(uuid.uuid4()),
        "ts": now_iso(),
        "source": source,
        "schema": "menagerie.sessionProfile.v1",
        "kind": "menagerie.sessionProfile",
        "workspaceId": topic_segment(workspace_id, "workspace"),
        "sessionId": topic_segment(session_id, "unknown"),
        "displayName": sanitized_name,
        "summary": summary,
    }


def topics_for(event: dict[str, Any]) -> tuple[str, str]:
    workspace = topic_segment(event.get("workspaceId"), "workspace")
    session = topic_segment(event.get("sessionId"), "unknown")
    return (
        f"{EVENT_TOPIC_PREFIX}/{workspace}/{session}",
        f"{STATE_TOPIC_PREFIX}/{workspace}/{session}",
    )


def health_topic(client_id: str) -> str:
    return f"{HEALTH_TOPIC_PREFIX}/{topic_segment(client_id, 'client')}"


def session_health_topic(event: dict[str, Any]) -> str:
    workspace = topic_segment(event.get("workspaceId"), "workspace")
    session = topic_segment(event.get("sessionId"), "unknown")
    return f"{HEALTH_TOPIC_PREFIX}/session/{workspace}/{session}"


def session_profile_topic(workspace_id: str, session_id: str) -> str:
    workspace = topic_segment(workspace_id, "workspace")
    session = topic_segment(session_id, "unknown")
    return f"{PROFILE_TOPIC_PREFIX}/session/{workspace}/{session}"


def dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
