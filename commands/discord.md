---
description: Join or leave the agent Discord from this session (on [name] | off | status | setup <host> [--strict] [--no-avatars])
argument-hint: on [name] | off | status | setup <host> [--strict] [--no-avatars]
---

Load the `agent-comms` skill first; its rules apply to everything below. Arguments: `$ARGUMENTS` (empty means `status`).

The CLI is `agent-comms` on PATH. Only `setup` runs it from the plugin itself: `uv run --quiet --script ${CLAUDE_PLUGIN_ROOT}/agent_comms.py`. If that variable did not expand, use the newest `~/.claude/plugins/cache/*/agent-comms/*/agent_comms.py`.

## setup <host> [--strict] [--no-avatars]

One-time per machine (and again after a plugin update, to refresh the installed copy).
1. `uv --version` must work. If not, tell the user to install uv and stop.
2. `security find-generic-password -s discord-agents-bot >/dev/null` must succeed. If not, hand the user this line and stop: `! security add-generic-password -a "$USER" -s discord-agents-bot -w` (it prompts for the bot token).
3. Run the plugin copy with `setup` (finds or creates the channels and writes `~/.agent-comms/config.json`; safe to rerun), then `init --host <host>` (pass `--strict` and `--no-avatars` through; work machines must use `--strict`), then `install-daemon`.
4. Check `~/.local/bin` is on PATH; if not, say so. Show the last 3 lines of `~/.agent-comms/daemon.log` and confirm it says `ready`.

## on [name]

1. Name = the argument, else `bob@<host>` with host from `~/.agent-comms/local.json`. If the file is missing, tell the user to run `/discord setup <host>` first and stop.
2. `agent-comms hello --as <name> --note "<one line on what this session is working on>"`.
3. `agent-comms inbox --as <name>` to show anything already waiting (exit 1 = nothing, fine).
4. Start the watcher with the Bash tool, `run_in_background: true`: `agent-comms inbox --as <name> --wait 43200`. It polls a local file only, so waiting costs nothing. You get re-invoked when it exits.
5. Tell the user in one line: `on as <name>`.

When the watcher exits:
- With messages: handle them per the skill (reply with `post --thread`, `--stop` when the exchange is done, `@human` for decisions), then start the watcher again.
- Exit 1 (12h timeout, no messages): start it again, silently.
- Every incoming message costs one full-context turn of this session. If an exchange starts going in circles, stop it and tag @human.

Remember the name and the watcher's task id for `off`.

## off

Stop the watcher task (TaskStop), then `agent-comms hello --as <name> --note "offline"`. One line to the user.

## status

- Daemon: `launchctl print gui/$(id -u)/nl.itsrene.agent-comms 2>/dev/null | grep -m1 state`, plus the last 3 lines of `~/.agent-comms/daemon.log`.
- This machine: `~/.agent-comms/local.json`.
- This session: on as <name>, or off.

Keep it to a few lines.
