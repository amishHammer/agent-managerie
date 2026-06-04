#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import os
import sys

plugin_root = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
repo_root = plugin_root.parents[1]
python_dir = repo_root / "python"
if python_dir.exists():
    sys.path.insert(0, str(python_dir))

from menagerie.hook_emitter import main

raise SystemExit(main())
