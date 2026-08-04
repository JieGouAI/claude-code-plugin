---
name: jiegou:trigger
description: Trigger a JieGou workflow
allowed-tools: jiegou_list_workflows, jiegou_run_workflow, jiegou_get_run_status
---

Trigger a JieGou workflow. The user's arguments specify the workflow name/ID and optional input.

Steps:
1. If the user provided a workflow name (not ID), use jiegou_list_workflows to find the matching workflow ID
2. Use jiegou_run_workflow with the workflow ID and input
3. Report the workflow run ID and initial status
4. Optionally poll jiegou_get_run_status if the user wants to wait for completion
