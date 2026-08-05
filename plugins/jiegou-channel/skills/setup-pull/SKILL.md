---
name: setup-pull
description: Set up (or inspect/remove) optional unattended pulling for this JieGou seat — a scheduled check that executes console-assigned work without an open session. Use when the user says "/jiegou:setup-pull", "handle JieGou work automatically", "set up background pull", "stop the automatic pull", or asks how assignments can run while they're away.
---

Configure unattended pull for this seat. This installs a PERSISTENT schedule
on the user's machine — only ever at their explicit request, with the shape
spelled out before anything is written.

1. **Explain before installing** (plainly, all four points):
   - A scheduled job (macOS launchd / Linux cron) will run every N minutes
     (default 30). Each run does a FREE local check first; a headless Claude
     session launches ONLY when the console has actually assigned work — so
     idle periods consume nothing.
   - Runs that do work use their Claude subscription usage.
   - Approvals and publishing stay human regardless — unattended runs stop at
     the same gates; anything needing interactive input is left for a real
     session.
   - It's fully inspectable and reversible: `status` shows the schedule and
     recent log; `uninstall` removes everything.

2. **Confirm the interval** (default 30 min; minimum 5) and that they want it
   installed. Do not proceed on ambiguity.

3. **Install:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_pull.py" install [--interval N]`
   — requires an enrolled seat (route to `/jiegou:enroll` if not) and the
   `claude` CLI on PATH. Relay the printed wrapper/log/removal paths.

4. **Verify:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_pull.py" status`
   and show the user the result.

5. **Removal, any time:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_pull.py" uninstall`
   — mention this unprompted at the end of setup.

For "is it running / what has it done": run `status` and read the last lines
of the log at `~/.jiegou/logs/pull-<seat>.log`.
