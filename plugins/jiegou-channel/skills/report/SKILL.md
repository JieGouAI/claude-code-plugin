---
name: report
description: Report completion (or failure) of JieGou-dispatched work back to the management plane, closing the governed loop with agent attribution. Use after finishing work surfaced by /jiegou:pull, or when the user says "report this to JieGou", "/jiegou:report", "mark the JieGou task done".
---

Close the loop on plane-dispatched work:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/substrate.py" report --item <itemId> [--command <commandId>] [--note "…"] [--artifact <path>] [--failed]`

Rules:
- `--item` is required — it's the id shown by `/jiegou:pull`. Include
  `--command` when the work arrived as a COMMAND (pairs the completion to the
  dispatch).
- Add a concise `--note` describing what was done, and `--artifact` with the
  primary output's path when there is one — these become part of the item's
  audit record in the console.
- **Never report success for unfinished or failed work.** If the work could
  not be completed, report honestly with `--failed` and a note explaining why —
  a failed report releases the item; a false success corrupts the audit trail.
- Confirm the printed item state back to the user (normally `executed`).

Do not end a session holding pulled work unreported: either report success
with the artifact, or `--failed` to release it.
