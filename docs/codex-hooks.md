# Codex Hook Setup

The plugin at `plugins/codex-menagerie-events` contains `hooks/hooks.json` and a small wrapper script.

Before launching Codex, configure MQTT:

```sh
export MENAGERIE_MQTT_HOST=localhost
export MENAGERIE_MQTT_PORT=1883
export MENAGERIE_MQTT_TLS=false
export MENAGERIE_MQTT_USERNAME=codex-hook
export MENAGERIE_MQTT_PASSWORD=dev-hook-password
export MENAGERIE_WORKSPACE_ID=my-workspace
```

Enable the plugin through Codex's local plugin flow, or copy the hook definitions into `~/.codex/hooks.json` and update the `command` fields to point at `bin/codex-menagerie-hook`.

Codex requires non-managed command hooks to be reviewed and trusted. Use `/hooks` in Codex to review the hook definitions after installing or changing the plugin.

## Supported Events

- `SessionStart`: moves the session to `starting`.
- `UserPromptSubmit`: moves the session to `thinking`.
- `PreToolUse`: moves the session to `runningTool`.
- `PermissionRequest`: moves the session to `waitingForPermission`.
- `PostToolUse`: moves the session back to `thinking`.
- `PreCompact`: moves the session to `compacting`.
- `PostCompact`: moves the session back to `thinking`.
- `Stop`: moves the session to `readyForReview`.

The hook process exits successfully even when MQTT is unavailable, so Codex work is not blocked by Menagerie infrastructure.
