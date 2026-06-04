<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# Codex Hook Setup

The plugin at `plugins/codex-menagerie-events` contains `hooks/hooks.json` and a small wrapper script.

Hook settings live in `menagerie.env`, copied from `examples/codex/menagerie.env`. Configure `MENAGERIE_HOME`, MQTT host, credentials, and workspace id there before launching Codex.

Enable the plugin through Codex's local plugin flow, or copy the sample hook files:

```sh
mkdir -p .codex
cp /absolute/path/to/menagerie/examples/codex/hooks.json .codex/hooks.json
cp /absolute/path/to/menagerie/examples/codex/menagerie.env .codex/menagerie.env
```

Set `MENAGERIE_HOME=/actual/path/to/menagerie` in `menagerie.env`. For global hooks, copy the same files to `~/.codex/hooks.json` and `~/.codex/menagerie.env`, then set both files to mode `600`.

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

Codex currently uses `Stop` for turn completion rather than a first-class session-end hook. Menagerie publishes timeout metadata with retained state so clients can infer `idle`, `dead`, and `exited` display states when no later hook arrives.

## Friendly Names

Codex shell commands expose `CODEX_THREAD_ID`, so the current session can publish a retained friendly name without manually copying the session id. The deterministic command is:

```sh
./bin/codex-menagerie-name "Bug Hunt"
```

The plugin also includes the `menagerie-session-name` skill. In Codex, invoke it explicitly:

```text
$menagerie-session-name Menagerie-dev
```

Both paths write `menagerie.sessionProfile.v1` to `menagerie/v1/profile/session/{workspaceId}/{sessionId}`. Use `--session-id` when naming a session from outside Codex.

The hooks do not parse ordinary prompt text for naming commands. Use the explicit skill or CLI.

### Skill Installation

Install the plugin to get both hooks and the skill:

```sh
codex plugin marketplace add /absolute/path/to/menagerie
codex plugin add codex-menagerie-events --marketplace menagerie-local
```

Restart Codex after installing. The plugin uses the repo's `marketplace.json`, and Codex loads the skill from `plugins/codex-menagerie-events/skills/`.

For a skill-only personal install, make the CLI available on `PATH` and link the skill directory into `~/.codex/skills`:

```sh
mkdir -p ~/.local/bin ~/.codex/skills
ln -sfn /absolute/path/to/menagerie/bin/codex-menagerie-name ~/.local/bin/codex-menagerie-name
ln -sfn /absolute/path/to/menagerie/plugins/codex-menagerie-events/skills/menagerie-session-name ~/.codex/skills/menagerie-session-name
```

Restart Codex after linking the skill. Use the plugin install when you also want the lifecycle hooks.
