---
name: jiegou:recipes
description: List available JieGou recipes, optionally filtered by department
allowed-tools: jiegou_list_recipes
---

List the available recipes on the connected JieGou account.
If the user provides arguments, use them as filters:
- Department name (e.g., "marketing", "sales") → pass as department filter
- Search terms → pass as search filter

Use the jiegou_list_recipes tool to fetch recipes, then display them in a clean table format showing name, department, and description.
