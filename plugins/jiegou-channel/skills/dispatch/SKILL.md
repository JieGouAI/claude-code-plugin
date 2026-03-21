---
name: dispatch
description: Send a task result or progress update back to JieGou. Use when you've completed work from a JieGou task and need to report the outcome.
---

When the user asks to send results back to JieGou, or when you've completed a task that arrived via the JieGou channel, use the `jiegou_reply` tool to report the outcome.

Required information:
- **task_id**: The ID from the `<channel source="jiegou" task_id="...">` tag
- **status**: One of `in_progress`, `completed`, or `error`
- **result**: A summary of what was accomplished or what went wrong

Optional:
- **files**: List of file paths that were created or modified

If "$ARGUMENTS" contains a task ID and result, extract them and call `jiegou_reply` directly.
