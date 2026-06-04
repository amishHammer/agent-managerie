---
name: menagerie-session-name
description: Set or clear the friendly display name for the current Menagerie/Codex session by publishing a retained session profile to the Menagerie MQTT broker. Use when the user invokes this skill directly or asks to name, rename, label, or clear the current Menagerie session or gremlin.
metadata:
  short-description: Name the current Menagerie session
---

# Menagerie Session Name

Use this skill only to set or clear the friendly display name for the current Menagerie session. Do not edit repository files for this operation.

## Set a name

Run the first available command shape:

```sh
python3 plugins/codex-menagerie-events/scripts/codex_menagerie_name.py "Menagerie-dev"
```

If the skill is loaded from an installed plugin outside this repository, resolve `../../scripts/codex_menagerie_name.py` relative to this `SKILL.md` file and run that script instead. If the skill was installed manually without the plugin, run `codex-menagerie-name "Menagerie-dev"` from `PATH`.

## Clear a name

```sh
python3 plugins/codex-menagerie-events/scripts/codex_menagerie_name.py --clear
```

For plugin installs outside this repository, resolve `../../scripts/codex_menagerie_name.py` relative to this `SKILL.md`. For manual skill installs, run `codex-menagerie-name --clear` from `PATH`.

## Behavior

- The command uses `CODEX_THREAD_ID` for the current session id when Codex exposes it.
- The command uses `MENAGERIE_WORKSPACE_ID`, or derives a workspace id from the current working directory when unset.
- MQTT settings come from the existing `MENAGERIE_MQTT_*` environment variables.
- After running the command, briefly report whether the name was set or cleared.
