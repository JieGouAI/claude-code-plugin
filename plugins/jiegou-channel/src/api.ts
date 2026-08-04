/**
 * JieGou API client
 *
 * Ported from mcp-jiegou — provides HTTP-based access to the JieGou Console API.
 * 8 tools: list_recipes, run_recipe, list_workflows, run_workflow, get_run_status,
 * get_analytics, create_schedule, publish_social_post.
 *
 * v0.3.0: run_recipe/run_workflow use the /api/embed/* routes (the endpoints
 * with first-class `jgk_` embedded-key Bearer auth + SDK rate limits). The
 * remaining list/analytics/schedule/social tools are marked experimental in
 * their definitions until their routes gain key auth. search_knowledge was
 * removed (its endpoint never shipped). For governed task dispatch, prefer
 * the substrate flow (scripts/substrate.py + the enroll/pull/report skills).
 */

import { loadConfig } from './config.js';

export async function jiegouFetch(
  path: string,
  options: RequestInit = {},
): Promise<unknown> {
  const config = loadConfig();
  const url = path.startsWith('http') ? path : `${config.baseUrl}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${config.apiKey}`,
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    },
  });
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(
      `JieGou API error: ${res.status} ${res.statusText}${errorBody ? ` — ${errorBody}` : ''}`,
    );
  }
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return res.json();
  }
  return res;
}

export async function execute(
  toolName: string,
  args: Record<string, unknown>,
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const config = loadConfig();

  switch (toolName) {
    // ─── Recipes ───────────────────────────────────────────────
    case 'list_recipes': {
      const params = new URLSearchParams();
      params.set('accountId', config.accountId);
      if (args.department) params.set('department', args.department as string);
      if (args.search) params.set('search', args.search as string);
      if (args.limit) params.set('limit', String(args.limit));
      const data = await jiegouFetch(`/api/recipes?${params.toString()}`);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    case 'run_recipe': {
      // /api/embed/* is the key-authed execution surface (jgk_ Bearer).
      const data = await jiegouFetch(`/api/embed/recipes/${args.recipeId}/run`, {
        method: 'POST',
        body: JSON.stringify({ input: args.input }),
      });
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    // ─── Workflows ─────────────────────────────────────────────
    case 'list_workflows': {
      const params = new URLSearchParams();
      params.set('accountId', config.accountId);
      if (args.department) params.set('department', args.department as string);
      if (args.search) params.set('search', args.search as string);
      if (args.limit) params.set('limit', String(args.limit));
      const data = await jiegouFetch(`/api/workflows?${params.toString()}`);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    case 'run_workflow': {
      // /api/embed/* is the key-authed execution surface (jgk_ Bearer).
      const data = await jiegouFetch(`/api/embed/workflows/${args.workflowId}/run`, {
        method: 'POST',
        body: JSON.stringify({ input: args.input }),
      });
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    // ─── Run Status ────────────────────────────────────────────
    case 'get_run_status': {
      const runId = encodeURIComponent(args.runId as string);
      const endpoint =
        args.type === 'workflow'
          ? `/api/workflow-runs/${runId}`
          : `/api/runs/${runId}`;
      const data = await jiegouFetch(endpoint);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    // ─── Knowledge Search ──────────────────────────────────────

    // ─── Analytics ─────────────────────────────────────────────
    case 'get_analytics': {
      const params = new URLSearchParams();
      params.set('accountId', config.accountId);
      params.set('metric', args.metric as string);
      if (args.timeRange) params.set('timeRange', args.timeRange as string);
      const data = await jiegouFetch(`/api/analytics?${params.toString()}`);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    // ─── Scheduling ────────────────────────────────────────────
    case 'create_schedule': {
      const body: Record<string, unknown> = {
        cronExpression: args.cronExpression,
        accountId: config.accountId,
      };
      if (args.recipeId) body.recipeId = args.recipeId;
      if (args.workflowId) body.workflowId = args.workflowId;
      if (args.input) body.input = args.input;
      const data = await jiegouFetch('/api/schedules', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    // ─── Social Publishing ─────────────────────────────────────
    case 'publish_social_post': {
      const body: Record<string, unknown> = {
        platform: args.platform,
        caption: args.caption,
        accountId: config.accountId,
      };
      if (args.mediaUrl) body.mediaUrl = args.mediaUrl;
      if (args.mediaType) body.mediaType = args.mediaType;
      const data = await jiegouFetch('/api/social/publish', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    }

    default:
      throw new Error(`Unknown tool: ${toolName}`);
  }
}
