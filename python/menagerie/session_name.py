# SPDX-License-Identifier: AGPL-3.0-only
"""Set a retained friendly name for a Menagerie session."""

from __future__ import annotations

import argparse
import os
import sys

from .events import (
    cwd_hash,
    dumps,
    session_id_from,
    session_profile_document,
    workspace_id_for,
)
from .publisher import publish_session_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-menagerie-name",
        description="Publish a retained friendly name for a Menagerie session.",
    )
    parser.add_argument("name", nargs="?", help="friendly name to show for this session")
    parser.add_argument("--clear", action="store_true", help="clear the friendly name")
    parser.add_argument("--workspace-id", help="workspace id; defaults to MENAGERIE_WORKSPACE_ID or cwd")
    parser.add_argument("--session-id", help="session id; defaults to MENAGERIE_SESSION_ID or CODEX_THREAD_ID")
    parser.add_argument("--cwd", default=os.getcwd(), help=argparse.SUPPRESS)
    parser.add_argument("--print-json", action="store_true", help="print the retained profile document")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.clear and args.name:
        parser.error("pass either a name or --clear, not both")
    if not args.clear and not args.name:
        parser.error("a name is required unless --clear is passed")
    if args.name is not None and not args.name.strip():
        parser.error("name cannot be empty")

    raw = {"session_id": args.session_id, "cwd": args.cwd}
    workspace_id = args.workspace_id or workspace_id_for(args.cwd)
    session_id = session_id_from(raw, fallback=cwd_hash(args.cwd))
    display_name = None if args.clear else args.name
    profile = session_profile_document(
        workspace_id=workspace_id,
        session_id=session_id,
        display_name=display_name,
        source="menagerie-session-name",
    )

    try:
        publish_session_profile(profile)
    except Exception as exc:
        print(f"codex-menagerie-name could not publish session profile: {exc}", file=sys.stderr)
        return 1

    if args.print_json:
        print(dumps(profile))
    elif args.clear:
        print(f"Cleared friendly name for session {profile['sessionId']}")
    else:
        print(f"Set friendly name for session {profile['sessionId']}: {profile['displayName']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
