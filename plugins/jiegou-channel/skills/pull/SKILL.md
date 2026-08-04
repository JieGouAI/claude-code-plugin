---
name: pull
description: Pull assigned work from the JieGou management plane — approved cockpit items and commands dispatched to this substrate seat. Use at session start, or when the user says "check JieGou work", "/jiegou:pull", "what does the plane want", or "any JieGou tasks?".
---

Ask the plane what work is assigned to this seat:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/substrate.py" pull`

Interpret the output for the user:
- **COMMAND** lines are plane-dispatched work orders (e.g. an approved cockpit
  item routed to this agent). Each shows the command id and the item it serves.
- **ITEM** lines are queue items assigned to this seat, with bundle/kind and a
  message when present.
- "nothing assigned" means the plane has no work for this agent right now.

For each piece of work: do it in this session with the user (the work
instructions live in the item/command payload), then close the loop with
`/jiegou:report` — completion moves the item to `executed` in the console with
this agent's attribution. Work you pull is HUMAN-APPROVED upstream (the
console's approval gate) — but anything with side effects beyond this machine
still follows this session's own permission rules.

If the CLI says "not enrolled", route the user to `/jiegou:enroll`.
