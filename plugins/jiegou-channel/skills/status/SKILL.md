---
name: status
description: Check JieGou connectivity — the substrate enrollment session (whoami) and, when channel mode is enabled, the WebSocket status. Use when the user asks about JieGou connectivity.
---

First check the substrate session: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/substrate.py" whoami`
(reports agent id, account, role, scopes, token expiry — or "not enrolled", in which
case point the user to /jiegou:enroll).

If channel mode is enabled (JIEGOU_WS_URL set), also call the `jiegou_status` tool and report:
- Whether the WebSocket connection to JieGou is active
- The connected account ID
- The WebSocket URL being used

If the connection is down, suggest the user check their JIEGOU_API_KEY and JIEGOU_ACCOUNT_ID environment variables.
