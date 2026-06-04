# SPDX-License-Identifier: AGPL-3.0-only
import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from menagerie import session_name


class SessionNameCommandTests(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ.pop("MENAGERIE_WORKSPACE_ID", None)
        os.environ.pop("MENAGERIE_SESSION_ID", None)
        os.environ.pop("CODEX_THREAD_ID", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_name_command_publishes_retained_profile(self):
        with patch("menagerie.session_name.publish_session_profile") as publish, patch(
            "sys.stdout", new_callable=StringIO
        ) as stdout:
            rc = session_name.main(
                [
                    "--workspace-id",
                    "demo-workspace",
                    "--session-id",
                    "session-7",
                    "--print-json",
                    "Bug Hunt",
                ]
            )
        self.assertEqual(rc, 0)
        profile = publish.call_args.args[0]
        self.assertEqual(profile["workspaceId"], "demo-workspace")
        self.assertEqual(profile["sessionId"], "session-7")
        self.assertEqual(profile["displayName"], "Bug Hunt")
        self.assertEqual(json.loads(stdout.getvalue())["displayName"], "Bug Hunt")

    def test_name_command_uses_codex_thread_id(self):
        os.environ["CODEX_THREAD_ID"] = "thread-xyz"
        with patch("menagerie.session_name.publish_session_profile") as publish, patch(
            "sys.stdout", new_callable=StringIO
        ):
            rc = session_name.main(["--workspace-id", "demo-workspace", "Build Fix"])
        self.assertEqual(rc, 0)
        self.assertEqual(publish.call_args.args[0]["sessionId"], "thread-xyz")


if __name__ == "__main__":
    unittest.main()
