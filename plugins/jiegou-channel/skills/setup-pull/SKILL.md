---
name: setup-pull
description: Set up (or inspect/remove) optional unattended pulling for this JieGou seat — a scheduled check that executes console-assigned work without an open session. Use when the user says "/jiegou:setup-pull", "handle JieGou work automatically", "set up background pull", "stop the automatic pull", or asks how assignments can run while they're away.
---

Configure unattended pull for this seat. This installs a PERSISTENT schedule
on the user's machine — only ever at their explicit request, with the shape
spelled out before anything is written.

1. **Explain before installing** (plainly, all four points):
   - A background job will check for assigned work. Each check is a FREE local
     pull first; a headless Claude session launches ONLY when the console has
     actually assigned work — so idle periods consume nothing. Two modes:
     - **Wake (recommended on macOS, `--wake`):** a launchd KeepAlive daemon
       holds the seat's wake stream and pulls within seconds of a dispatch,
       on every reconnect, and on a 10-minute heartbeat. The server recycles
       the stream about every 10 minutes, so expect a pull roughly that often.
     - **Interval (`--interval N`, default 30 min; the only mode on Linux):**
       a launchd/cron job checks every N minutes, so dispatched work can wait
       up to N minutes.
   - Runs that do work use their Claude subscription usage.
   - Approvals and publishing stay human regardless — unattended runs stop at
     the same gates; anything needing interactive input is left for a real
     session.
   - It's fully inspectable and reversible: `status` shows the schedule and
     recent log; `uninstall` removes everything.

2. **Confirm the mode** (wake, or interval with N ≥ 5 min) and that they want
   it installed. Do not proceed on ambiguity.

3. **Install:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_pull.py" install --wake`
   or `... install [--interval N]` — requires an enrolled seat (route to
   `/jiegou:enroll` if not) and the `claude` CLI on PATH. On a machine with
   more than one enrolled seat, set `JIEGOU_AGENT_NAME=<seat>` on the command
   (seat identity is never guessed). Relay the printed wrapper/log/removal paths.

4. **Verify:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_pull.py" status`
   and show the user the result.

5. **Removal, any time:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_pull.py" uninstall`
   — mention this unprompted at the end of setup.

6. **After every plugin update, re-run `install` with the same mode** — say so
   unprompted. The installed job names this plugin version's directory, so it
   keeps running the old version until reinstalled, and stops working once
   the old directory is cleaned up. `status` shows which path it runs.

For "is it running / what has it done": run `status` and read the last lines
of the log at `~/.jiegou/logs/pull-<seat>.log`.
