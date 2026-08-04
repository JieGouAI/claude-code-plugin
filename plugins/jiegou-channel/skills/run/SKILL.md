---
name: jiegou:run
description: Run a JieGou recipe with input
allowed-tools: jiegou_list_recipes, jiegou_run_recipe, jiegou_get_run_status
---

Run a JieGou recipe. The user's arguments specify the recipe name/ID and optional input.

Steps:
1. If the user provided a recipe name (not ID), use jiegou_list_recipes to find the matching recipe ID
2. Use jiegou_run_recipe with the recipe ID and input
3. Use jiegou_get_run_status to poll for completion (wait up to 60 seconds)
4. Display the result
