# SPDX-License-Identifier: AGPL-3.0-only
import os
import unittest

from menagerie.events import normalize_hook_event, normalize_jsonl_event, state_document, topics_for


class EventNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ.pop("MENAGERIE_INCLUDE_TEXT", None)
        os.environ.pop("MENAGERIE_INCLUDE_RAW", None)
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


if __name__ == "__main__":
    unittest.main()
