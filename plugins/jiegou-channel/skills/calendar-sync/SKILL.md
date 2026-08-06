---
name: calendar-sync
description: Put publish reminders for approved JieGou posts on the user's calendar — their connected calendar (Google/Outlook via MCP) first — and keep them reconciled (moved slots, rejected/shipped posts). Use when the user says "/jiegou:calendar-sync", "remind me to publish", "put my post slots on my calendar", or asks how they'll keep track of approved drafts. Reminders only — publishing is always the human's act; nothing ever auto-posts.
---

Reconcile approved, human-publish-pending posts to reminders on the calendar
the user ACTUALLY LOOKS AT. The plane never touches a calendar; the seat uses
a capability only this machine/session has. Nothing here — or anywhere in
JieGou — publishes to LinkedIn.

**Calendar priority — connected calendar first:**
1. **Session calendar MCP tools** (Google Calendar, Outlook, …) — the user's
   real calendar. DEFAULT whenever such tools exist in the session.
2. **macOS Calendar.app** (osascript, `--mode local`) — fallback for seats
   with no calendar MCP. Warn: it only helps if Calendar.app is signed into
   an account the user checks; events in a stray local "Home" calendar are
   invisible reminders.
3. Neither available → degrade loudly: report "N publish slots have no
   reminder" and suggest connecting a calendar.

Steps:

1. **First run on a seat — explain, then opt in.** Tell the user plainly:
   a 30-minute event ("Publish LI post: …", 15-min alarm, cockpit pointer in
   the notes) is created at each approved post's planned slot (09:00 local),
   moved when the slot changes, removed when the post ships or is rejected.
   Then enable in the right mode:
   - MCP tools present: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/calendar_sync.py" enable --mode mcp`
   - No MCP (macOS): confirm the Calendar.app calendar name and warn about
     the one-time Automation permission prompt, then
     `… calendar_sync.py enable --mode local [--calendar "Name"]`

2. **Sync (any later run):** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/calendar_sync.py" sync`
   - **local mode:** the script does everything mechanically.
   - **mcp mode:** the script prints a JSON reconcile plan (`create` /
     `delete` lists). Execute it with the session's calendar tools —
     create/move events per the convention above — then close the loop:
     `… calendar_sync.py record <externalId> <slot> <eventRef>` per
     create/move (tracks it + sends the plane receipt so the console shows
     📅✓), and `… calendar_sync.py forget <externalId>` per delete.
   Run a sync after pulls that change post state — a good habit at the end
   of /jiegou:pull or /jiegou:draft-post sessions on opted-in seats.
   Headless caveat: MCP connectors can be absent in unattended sessions; in
   mcp mode, leave the printed plan unexecuted for the next interactive
   session rather than guessing — never fabricate an event receipt.

3. **Status / removal any time:** `… calendar_sync.py status` ·
   `… calendar_sync.py disable` (local mode also deletes every tracked
   event; mcp mode lists what to delete with your calendar tools). Mention
   `disable` unprompted at the end of setup.

Never install scheduled/automatic calendar syncing from a hook — opt-in must
be interactive.
