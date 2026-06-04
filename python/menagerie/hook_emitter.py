# SPDX-License-Identifier: AGPL-3.0-only
"""Codex command hook entry point."""

from __future__ import annotations

import json
import sys

from .events import canonical_hook_event, env_bool, normalize_hook_event
from .publisher import publish_event


def main() -> int:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raw = {"value": raw}
    except json.JSONDecodeError as exc:
        print(f"menagerie hook received invalid JSON: {exc}", file=sys.stderr)
        raw = {"hook_event_name": "unknown"}

    event_name = canonical_hook_event(raw)
    try:
        publish_event(normalize_hook_event(raw))
    except Exception as exc:  # Hooks must never interrupt Codex.
        print(f"menagerie hook publish failed: {exc}", file=sys.stderr)
        if env_bool("MENAGERIE_STRICT", "CODEX_PET_STRICT"):
            return 1

    if event_name in {"stop", "subagentStop"}:
        sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
