---
name: enroll
description: Enroll this machine as a governed JieGou substrate worker using an enrollment code from the console. Use when the user says "enroll in JieGou", "connect this seat to JieGou", "/jiegou:enroll <code>", or pastes a JieGou enrollment code.
---

Enroll this Claude Code seat with the JieGou management plane.

1. If the user has not provided an enrollment code, tell them how to get one:
   an account **Owner/Admin** mints it in the JieGou console under
   **Settings → Hybrid → Add agent**. Codes are single-use with a 10-minute TTL.
   Never ask the user for passwords or platform credentials — the code is the
   only thing needed.

2. With the code, run:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/substrate.py" login --enroll <code>`

3. On success, show the user the printed identity (agent id, account, role,
   scopes) and confirm: the session (an auto-refreshing access JWT + rotating
   refresh token) is stored in the OS keychain; no platform credential lives on
   this device; an admin can revoke this seat from the console at any time.

4. On failure, relay the CLI's hint (expired/used/invalid code → mint a fresh
   one) — do not retry a code more than once; codes are single-use.

5. Suggest the natural next step: `/jiegou:pull` to see what work the plane has
   for this seat.

Notes: set `JIEGOU_CONSOLE_URL` for self-hosted consoles; `JIEGOU_AGENT_NAME`
names the seat (defaults to the current directory name).
