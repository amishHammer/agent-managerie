# SPDX-License-Identifier: AGPL-3.0-only
import os
import unittest
from datetime import datetime

from menagerie.events import (
    normalize_hook_event,
    normalize_jsonl_event,
    session_id_from,
    session_health_document,
    session_health_topic,
    session_profile_document,
    session_profile_topic,
    state_document,
    topics_for,
)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class EventNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ.pop("MENAGERIE_INCLUDE_TEXT", None)
        os.environ.pop("MENAGERIE_INCLUDE_RAW", None)
        os.environ.pop("MENAGERIE_IDLE_AFTER_SECONDS", None)
        os.environ.pop("MENAGERIE_DEAD_AFTER_SECONDS", None)
        os.environ.pop("MENAGERIE_EXITED_AFTER_SECONDS", None)
        os.environ.pop("CODEX_THREAD_ID", None)
        os.environ["MENAGERIE_WORKSPACE_ID"] = "demo-workspace"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_hook_event_redacts_prompt_by_default(self):
        event = normalize_hook_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "cwd": "/tmp/demo",
                "prompt": "please use sk-secret1234567890 in a command",
                "model": "gpt-test",
            }
        )
        self.assertEqual(event["workspaceId"], "demo-workspace")
        self.assertEqual(event["sessionId"], "session-1")
        self.assertEqual(event["state"], "thinking")
        self.assertEqual(event["payload"]["promptHash"], event["payload"]["promptHash"])
        self.assertNotIn("promptPreview", event["payload"])
        self.assertEqual(event["streamItem"]["schema"], "menagerie.streamItem.v1")
        self.assertEqual(event["streamItem"]["kind"], "prompt.submitted")
        self.assertEqual(event["streamItem"]["role"], "user")
        self.assertTrue(event["streamItem"]["contentRedacted"])
        self.assertEqual(event["streamItem"]["refs"]["promptHash"], event["payload"]["promptHash"])
        self.assertNotIn("preview", event["streamItem"])
        self.assertEqual(event["lifecycle"]["schema"], "menagerie.lifecycle.v1")
        self.assertEqual(event["lifecycle"]["status"], "active")
        self.assertEqual(event["lifecycle"]["lastSeenAt"], event["ts"])
        self.assertGreater(_parse_iso(event["lifecycle"]["idleAfter"]), _parse_iso(event["ts"]))

    def test_permission_request_sets_attention_state(self):
        event = normalize_hook_event(
            {
                "hook_event_name": "PermissionRequest",
                "session_id": "session-2",
                "cwd": "/tmp/demo",
                "tool_name": "Bash",
                "tool_input": {"command": "curl -H 'Authorization: Bearer secret-token-value' example.test"},
            }
        )
        self.assertEqual(event["severity"], "attention")
        self.assertEqual(event["state"], "waitingForPermission")
        self.assertEqual(event["payload"]["toolName"], "Bash")
        self.assertIn("toolCommandHash", event["payload"])
        self.assertNotIn("toolInputPreview", event["payload"])
        self.assertEqual(event["streamItem"]["kind"], "permission.requested")
        self.assertEqual(event["streamItem"]["tone"], "attention")
        self.assertEqual(event["streamItem"]["subject"], "Bash")
        self.assertIn("toolCommandHash", event["streamItem"]["refs"])

    def test_stream_preview_is_redacted_when_text_is_enabled(self):
        os.environ["MENAGERIE_INCLUDE_TEXT"] = "true"
        event = normalize_hook_event(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session-2",
                "cwd": "/tmp/demo",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "curl -H 'Authorization: Bearer secret-token-value' example.test"
                },
            }
        )
        self.assertIn("toolInputPreview", event["payload"])
        self.assertFalse(event["streamItem"]["contentRedacted"])
        self.assertIn("Bearer [REDACTED]", event["streamItem"]["preview"])
        self.assertNotIn("secret-token-value", event["streamItem"]["preview"])

    def test_state_document_carries_last_stream_item(self):
        event = normalize_hook_event(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "session-2",
                "cwd": "/tmp/demo",
                "tool_name": "Bash",
                "tool_response": {"exit_code": 1},
            }
        )
        state = state_document(event)
        self.assertEqual(state["lastStreamItem"]["kind"], "tool.completed")
        self.assertEqual(state["lastStreamItem"]["tone"], "warning")
        self.assertEqual(state["lastStreamItem"]["context"]["exitCode"], 1)
        self.assertEqual(state["lifecycle"]["status"], "active")

    def test_stop_state_is_idle_then_times_out_to_dead_and_exited(self):
        os.environ["MENAGERIE_IDLE_AFTER_SECONDS"] = "10"
        os.environ["MENAGERIE_DEAD_AFTER_SECONDS"] = "20"
        os.environ["MENAGERIE_EXITED_AFTER_SECONDS"] = "30"
        event = normalize_hook_event(
            {
                "hook_event_name": "Stop",
                "session_id": "session-3",
                "cwd": "/tmp/demo",
            }
        )
        lifecycle = event["lifecycle"]
        self.assertEqual(lifecycle["status"], "idle")
        self.assertEqual(lifecycle["idleAfter"], event["ts"])
        self.assertEqual(lifecycle["reason"], "turnComplete")
        self.assertGreater(_parse_iso(lifecycle["deadAfter"]), _parse_iso(lifecycle["idleAfter"]))
        self.assertGreater(_parse_iso(lifecycle["exitedAfter"]), _parse_iso(lifecycle["deadAfter"]))

    def test_session_health_document_carries_lifecycle_without_overwriting_state_shape(self):
        event = normalize_hook_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-4",
                "cwd": "/tmp/demo",
            }
        )
        topic = session_health_topic(event)
        health = session_health_document(event)
        self.assertEqual(topic, "menagerie/v1/health/session/demo-workspace/session-4")
        self.assertEqual(health["id"], f"{event['id']}:session-health")
        self.assertEqual(health["schema"], "menagerie.sessionHealth.v1")
        self.assertEqual(health["kind"], "menagerie.sessionHealth")
        self.assertEqual(health["sessionState"], "thinking")
        self.assertEqual(health["lifecycle"]["status"], "active")
        self.assertNotIn("state", health)

    def test_session_profile_document_names_session(self):
        profile = session_profile_document(
            workspace_id="demo workspace",
            session_id="session 5",
            display_name="Bug Hunt",
        )
        self.assertEqual(profile["schema"], "menagerie.sessionProfile.v1")
        self.assertEqual(profile["kind"], "menagerie.sessionProfile")
        self.assertEqual(profile["workspaceId"], "demo-workspace")
        self.assertEqual(profile["sessionId"], "session-5")
        self.assertEqual(profile["displayName"], "Bug Hunt")
        self.assertEqual(profile["summary"], "Session named Bug Hunt")
        self.assertEqual(
            session_profile_topic(profile["workspaceId"], profile["sessionId"]),
            "menagerie/v1/profile/session/demo-workspace/session-5",
        )

    def test_session_profile_document_can_clear_name(self):
        profile = session_profile_document(
            workspace_id="demo-workspace",
            session_id="session-6",
            display_name=None,
        )
        self.assertIsNone(profile["displayName"])
        self.assertEqual(profile["summary"], "Session name cleared")

    def test_session_id_can_fall_back_to_codex_thread_id(self):
        os.environ["CODEX_THREAD_ID"] = "thread-abc"
        self.assertEqual(session_id_from({}, fallback="fallback"), "thread-abc")

    def test_topics_are_versioned(self):
        event = normalize_hook_event(
            {
                "hook_event_name": "Stop",
                "session_id": "session-3",
                "cwd": "/tmp/demo",
            }
        )
        event_topic, state_topic = topics_for(event)
        self.assertEqual(event_topic, "menagerie/v1/events/demo-workspace/session-3")
        self.assertEqual(state_topic, "menagerie/v1/state/demo-workspace/session-3")

    def test_jsonl_event_maps_thread_started(self):
        event = normalize_jsonl_event(
            {"type": "thread.started", "thread_id": "thread-1"},
            workspace_id="demo-workspace",
            session_id=None,
        )
        self.assertEqual(event["source"], "codex-exec-jsonl")
        self.assertEqual(event["sessionId"], "thread-1")
        self.assertEqual(event["state"], "starting")
        self.assertEqual(event["lifecycle"]["status"], "active")


if __name__ == "__main__":
    unittest.main()
