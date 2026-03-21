---
name: status
description: Check the JieGou channel connection status and show account info. Use when the user asks about JieGou connectivity or wants to verify the channel is working.
---

Check the JieGou channel connection status by calling the `jiegou_status` tool. Report:
- Whether the WebSocket connection to JieGou is active
- The connected account ID
- The WebSocket URL being used

If the connection is down, suggest the user check their JIEGOU_API_KEY and JIEGOU_ACCOUNT_ID environment variables.
