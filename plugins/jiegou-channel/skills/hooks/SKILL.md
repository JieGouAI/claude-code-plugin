---
name: hooks
description: Show this JieGou account's content-hook queue — the idea-stage post seeds curated from its intelligence digests. Use when the user says "/jiegou:hooks", "what's in my content queue", "any post ideas from JieGou", or before picking what to draft.
---

Show the account's drafting queue:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gtm.py" pull`

Present the printed idea hooks as a numbered list: category letter, the hook
text, and the source URL when present. Explain briefly: hooks are curated,
human-approved seeds from the account's weekly intelligence digest — each one
traces to a real cited source. Natural next step: pick one and run
`/jiegou:draft-post`. If the list is empty, the next digest cycle will refill
it (or the operator can queue hooks manually in the console).
