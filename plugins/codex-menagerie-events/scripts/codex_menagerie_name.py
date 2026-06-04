#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import os
import subprocess
import sys

plugin_root = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
for base in [plugin_root, *plugin_root.parents]:
    python_dir = base / "python"
    if (python_dir / "menagerie" / "session_name.py").exists():
        sys.path.insert(0, str(python_dir))
        break

try:
    from menagerie.session_name import main
except ModuleNotFoundError:
    raise SystemExit(subprocess.call(["codex-menagerie-name", *sys.argv[1:]]))

raise SystemExit(main())
