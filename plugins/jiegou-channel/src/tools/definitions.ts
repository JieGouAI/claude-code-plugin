/**
 * API tool definitions for JieGou Claude Code plugin
 *
 * 8 tools: jiegou_list_recipes, jiegou_run_recipe, jiegou_list_workflows,
 * jiegou_run_workflow, jiegou_get_run_status,
 * jiegou_get_analytics, jiegou_create_schedule, jiegou_publish_social_post.
 *
 * All tool names are prefixed with `jiegou_` to avoid collisions with other
 * MCP servers in the same Claude Code session.
 */

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: 'object';
    properties: Record<string, unknown>;
    required?: string[];
  };
}

// ─── Recipe tools ─────────────────────────────────────────────────────

const jiegouListRecipes: ToolDefinition = {
  name: 'jiegou_list_recipes',
  description:
    'List available recipes in the JieGou platform. Optionally filter by department or search query. EXPERIMENTAL: this endpoint does not yet accept API-key auth; works only against consoles with key auth enabled.',
  inputSchema: {
    type: 'object',
    properties: {
      department: {
        type: 'string',
        description:
          'Filter recipes by department (e.g., "marketing", "sales", "support")',
      },
      search: {
        type: 'string',
        description: 'Search query to filter recipes by name or description',
      },
      limit: {
        type: 'number',
        description: 'Maximum number of recipes to return (default 50)',
      },
    },
  },
};

const jiegouRunRecipe: ToolDefinition = {
  name: 'jiegou_run_recipe',
  description:
    'Execute a recipe with structured input. Returns the run result including generated output.',
  inputSchema: {
    type: 'object',
    properties: {
      recipeId: {
        type: 'string',
        description: 'The ID of the recipe to execute',
      },
      input: {
        type: 'object',
        description:
          'Structured input data for the recipe (key-value pairs matching recipe input schema)',
      },
    },
    required: ['recipeId', 'input'],
  },
};

// ─── Workflow tools ───────────────────────────────────────────────────

const jiegouListWorkflows: ToolDefinition = {
  name: 'jiegou_list_workflows',
  description:
    'List available workflows in the JieGou platform. Optionally filter by department or search query. EXPERIMENTAL: this endpoint does not yet accept API-key auth; works only against consoles with key auth enabled.',
  inputSchema: {
    type: 'object',
    properties: {
      department: {
        type: 'string',
        description:
          'Filter workflows by department (e.g., "marketing", "sales", "support")',
      },
      search: {
        type: 'string',
        description: 'Search query to filter workflows by name or description',
      },
      limit: {
        type: 'number',
        description: 'Maximum number of workflows to return (default 50)',
      },
    },
  },
};

const jiegouRunWorkflow: ToolDefinition = {
  name: 'jiegou_run_workflow',
  description:
    'Trigger a workflow execution. Returns the workflow run ID and initial status for polling.',
  inputSchema: {
    type: 'object',
    properties: {
      workflowId: {
        type: 'string',
        description: 'The ID of the workflow to trigger',
      },
      input: {
        type: 'object',
        description: 'Structured input data for the workflow',
      },
    },
    required: ['workflowId', 'input'],
  },
};

const jiegouGetRunStatus: ToolDefinition = {
  name: 'jiegou_get_run_status',
  description:
    'Check the status of a recipe or workflow run. Returns current status and output if completed. EXPERIMENTAL: this endpoint does not yet accept API-key auth; works only against consoles with key auth enabled.',
  inputSchema: {
    type: 'object',
    properties: {
      runId: {
        type: 'string',
        description: 'The ID of the run to check',
      },
      type: {
        type: 'string',
        enum: ['recipe', 'workflow'],
        description: 'Whether this is a recipe run or workflow run',
      },
    },
    required: ['runId', 'type'],
  },
};

// ─── Analytics tools ──────────────────────────────────────────────────

const jiegouGetAnalytics: ToolDefinition = {
  name: 'jiegou_get_analytics',
  description:
    'Pull usage analytics from the JieGou platform (e.g., recipe runs, token usage, active users). EXPERIMENTAL: this endpoint does not yet accept API-key auth; works only against consoles with key auth enabled.',
  inputSchema: {
    type: 'object',
    properties: {
      metric: {
        type: 'string',
        description:
          'Metric to retrieve (e.g., "recipe_runs", "token_usage", "active_users", "workflow_runs")',
      },
      timeRange: {
        type: 'string',
        description:
          'Time range for the metric (e.g., "24h", "7d", "30d"). Defaults to "7d".',
      },
    },
    required: ['metric'],
  },
};

// ─── Scheduling tools ─────────────────────────────────────────────────

const jiegouCreateSchedule: ToolDefinition = {
  name: 'jiegou_create_schedule',
  description:
    'Create a scheduled run for a recipe or workflow. Uses cron expressions for recurring execution. EXPERIMENTAL: this endpoint does not yet accept API-key auth; works only against consoles with key auth enabled.',
  inputSchema: {
    type: 'object',
    properties: {
      recipeId: {
        type: 'string',
        description:
          'The ID of the recipe to schedule (provide either recipeId or workflowId)',
      },
      workflowId: {
        type: 'string',
        description:
          'The ID of the workflow to schedule (provide either recipeId or workflowId)',
      },
      cronExpression: {
        type: 'string',
        description:
          'Cron expression for the schedule (e.g., "0 9 * * 1-5" for weekdays at 9 AM)',
      },
      input: {
        type: 'object',
        description: 'Optional input data to pass on each scheduled run',
      },
    },
    required: ['cronExpression'],
  },
};

// ─── Social publishing tools ──────────────────────────────────────────

const jiegouPublishSocialPost: ToolDefinition = {
  name: 'jiegou_publish_social_post',
  description:
    'Publish content to a social media platform via the JieGou content pipeline. Supports text posts and media attachments. EXPERIMENTAL: this endpoint does not yet accept API-key auth; works only against consoles with key auth enabled.',
  inputSchema: {
    type: 'object',
    properties: {
      platform: {
        type: 'string',
        description:
          'Target platform (e.g., "facebook", "instagram", "line", "twitter")',
      },
      caption: {
        type: 'string',
        description: 'Text content of the post',
      },
      mediaUrl: {
        type: 'string',
        description: 'Optional URL of media to attach (image or video)',
      },
      mediaType: {
        type: 'string',
        enum: ['image', 'video'],
        description:
          'Type of media attachment (required if mediaUrl is provided)',
      },
    },
    required: ['platform', 'caption'],
  },
};

// ─── Combined API tool list ───────────────────────────────────────────

export const apiTools: ToolDefinition[] = [
  jiegouListRecipes,
  jiegouRunRecipe,
  jiegouListWorkflows,
  jiegouRunWorkflow,
  jiegouGetRunStatus,
  jiegouGetAnalytics,
  jiegouCreateSchedule,
  jiegouPublishSocialPost,
];

export const apiToolNames = new Set(apiTools.map((t) => t.name));
