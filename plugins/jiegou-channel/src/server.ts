#!/usr/bin/env bun

/**
 * JieGou Claude Code Channel Server
 *
 * An MCP channel server that bridges Claude Code to the JieGou platform.
 * Uses the low-level Server API to declare the experimental claude/channel
 * capability, enabling task events to arrive in Claude Code's context as
 * <channel source="jiegou" ...> tags.
 *
 * Tools:
 *   jiegou_reply  — Send a task result back to JieGou
 *   jiegou_status — Report current WebSocket connection status
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { WebSocket } from 'ws';
import { loadConfig, type ChannelConfig } from './config.js';
import { apiTools, apiToolNames } from './tools/definitions.js';
import { execute } from './api.js';

// ─── Logging ────────────────────────────────────────────────────────────────
// All logs go to stderr so stdout remains clean for MCP stdio transport.

function log(...args: unknown[]): void {
  console.error(`${new Date().toISOString()} [jiegou-channel]`, ...args);
}

// ─── WebSocket Connection State ─────────────────────────────────────────────

let ws: WebSocket | null = null;
let wsConnected = false;
let wsAuthenticated = false;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let pongTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

// ─── MCP Channel Server Setup ───────────────────────────────────────────────
// Uses the low-level Server API (not McpServer) to declare the experimental
// claude/channel capability. This is what makes Claude Code register a
// notification listener and render incoming events as:
//   <channel source="jiegou" task_id="..." task_type="..." priority="...">

const mcp = new Server(
  { name: 'jiegou', version: '0.2.0' },
  {
    capabilities: {
      experimental: { 'claude/channel': {} },
      tools: {},
    },
    instructions: [
      'You are connected to the JieGou AI workflow automation platform.',
      'You can use API tools (prefixed with jiegou_) to list recipes/workflows, run them, search knowledge, get analytics, create schedules, and publish social posts.',
      'If WebSocket channel mode is enabled, tasks also arrive as <channel source="jiegou" task_id="..." task_type="..." priority="...">.',
      'Execute the task using your local tools and context.',
      'When done, use the jiegou_reply tool to send results back, passing the task_id.',
      'For multi-step tasks, send progress updates with status="in_progress".',
      'Send status="completed" when done or status="error" if something fails.',
    ].join(' '),
  },
);

// ─── Tool Definitions ───────────────────────────────────────────────────────

const TOOLS = [
  {
    name: 'jiegou_reply',
    description: 'Send a task result back to the JieGou platform',
    inputSchema: {
      type: 'object' as const,
      properties: {
        task_id: {
          type: 'string',
          description: 'The ID of the task being responded to',
        },
        status: {
          type: 'string',
          enum: ['in_progress', 'completed', 'error'],
          description: 'Current status of the task',
        },
        result: {
          type: 'string',
          description: 'The result or output of the task',
        },
        files: {
          type: 'array',
          items: { type: 'string' },
          description:
            'Optional list of file paths that were created or modified',
        },
      },
      required: ['task_id', 'status', 'result'],
    },
  },
  {
    name: 'jiegou_status',
    description: 'Report the current JieGou WebSocket connection status',
    inputSchema: {
      type: 'object' as const,
      properties: {},
      required: [],
    },
  },
  ...apiTools,
];

export { TOOLS };

// ─── Tool Handlers ──────────────────────────────────────────────────────────

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS,
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;

  if (name === 'jiegou_reply') {
    const { task_id, status, result, files } = args as {
      task_id: string;
      status: string;
      result: string;
      files?: string[];
    };

    if (!ws || !wsConnected || !wsAuthenticated) {
      return {
        content: [
          {
            type: 'text' as const,
            text: 'Error: Not connected to JieGou. Use jiegou_status to check.',
          },
        ],
      };
    }

    try {
      ws.send(
        JSON.stringify({
          type: 'task_result',
          taskId: task_id,
          status,
          result,
          files,
        }),
      );
      return {
        content: [
          {
            type: 'text' as const,
            text: `Task result sent. task_id=${task_id}, status=${status}`,
          },
        ],
      };
    } catch (err) {
      return {
        content: [
          {
            type: 'text' as const,
            text: `Error sending result: ${err instanceof Error ? err.message : String(err)}`,
          },
        ],
      };
    }
  }

  if (name === 'jiegou_status') {
    return {
      content: [
        {
          type: 'text' as const,
          text: JSON.stringify(
            {
              connected: wsConnected,
              authenticated: wsAuthenticated,
              channelEnabled: config.channelEnabled,
              wsUrl: config.wsUrl,
              baseUrl: config.baseUrl,
              accountId: config.accountId,
            },
            null,
            2,
          ),
        },
      ],
    };
  }

  // ─── API tools (prefixed with jiegou_) ──────────────────────────────
  if (apiToolNames.has(name)) {
    const strippedName = name.replace(/^jiegou_/, '');
    try {
      return (await execute(strippedName, (args || {}) as Record<string, unknown>)) as {
        content: Array<{ type: 'text'; text: string }>;
      };
    } catch (err) {
      return {
        content: [
          {
            type: 'text' as const,
            text: `Error: ${err instanceof Error ? err.message : String(err)}`,
          },
        ],
      };
    }
  }

  throw new Error(`Unknown tool: ${name}`);
});

// ─── WebSocket Connection ───────────────────────────────────────────────────

function connectWebSocket(cfg: ChannelConfig): void {
  if (!cfg.wsUrl) {
    log('No WebSocket URL configured, skipping connection');
    return;
  }

  if (ws) {
    cleanupWebSocket();
  }

  log(`Connecting to ${cfg.wsUrl}...`);

  ws = new WebSocket(cfg.wsUrl, {
    headers: { Authorization: `Bearer ${cfg.apiKey}` },
  });

  ws.onopen = () => {
    log('WebSocket connected');
    wsConnected = true;

    // Register as a claude_code_channel client.
    // Auth is via the Bearer header already sent on connect — this message
    // just tells the proxy what type of client we are and which account.
    ws!.send(
      JSON.stringify({
        type: 'register',
        clientType: 'claude_code_channel',
        accountId: cfg.accountId,
      }),
    );

    wsAuthenticated = true;
    startHeartbeat(cfg);
  };

  ws.onmessage = (event: WebSocket.MessageEvent) => {
    const raw =
      typeof event.data === 'string' ? event.data : event.data.toString();

    // Silently handle pong
    if (raw === '{"type":"pong"}') {
      if (pongTimer) {
        clearTimeout(pongTimer);
        pongTimer = null;
      }
      return;
    }

    let data: Record<string, unknown>;
    try {
      data = JSON.parse(raw);
    } catch {
      log('Received non-JSON message, ignoring');
      return;
    }

    const { type } = data;

    if (type === 'task') {
      const taskId = String(data.id || data.taskId || '');
      const taskType = String(data.taskType || 'freeform');
      const priority = String(data.priority || 'normal');
      const createdBy = String(data.createdBy || '');
      const instructions = String(data.instructions || '');

      log(`Received task: ${taskId} (${taskType}, ${priority})`);

      // Push task as a channel notification.
      // This uses the claude/channel notification method so Claude Code
      // renders it as: <channel source="jiegou" task_id="..." ...>content</channel>
      mcp.notification({
        method: 'notifications/claude/channel',
        params: {
          content: instructions,
          meta: {
            task_id: taskId,
            task_type: taskType,
            priority,
            created_by: createdBy,
          },
        },
      });
      return;
    }

    if (type === 'error') {
      log('Server error:', data.message || 'unknown');
      return;
    }

    // Other message types
    if (type !== 'pong') {
      log('Received message type:', type);
    }
  };

  ws.onclose = (event: WebSocket.CloseEvent) => {
    log(
      `WebSocket closed: code=${event.code} reason=${event.reason || 'none'}`,
    );
    wsConnected = false;
    wsAuthenticated = false;
    stopHeartbeat();
    scheduleReconnect(cfg);
  };

  ws.onerror = (event: WebSocket.ErrorEvent) => {
    log('WebSocket error:', event.message || 'unknown');
  };
}

// ─── Heartbeat ──────────────────────────────────────────────────────────────

function startHeartbeat(cfg: ChannelConfig): void {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    ws.send(JSON.stringify({ type: 'ping' }));

    // If no pong within 5 seconds, consider connection dead
    pongTimer = setTimeout(() => {
      log('Heartbeat timeout — no pong received, closing connection');
      ws?.close();
    }, 5_000);
  }, cfg.heartbeatInterval);
}

function stopHeartbeat(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  if (pongTimer) {
    clearTimeout(pongTimer);
    pongTimer = null;
  }
}

// ─── Reconnect ──────────────────────────────────────────────────────────────

function scheduleReconnect(cfg: ChannelConfig): void {
  if (reconnectTimer) return;
  log(`Reconnecting in ${cfg.reconnectDelay / 1000}s...`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket(cfg);
  }, cfg.reconnectDelay);
}

function cleanupWebSocket(): void {
  stopHeartbeat();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.onopen = null;
    ws.onmessage = null;
    ws.onclose = null;
    ws.onerror = null;
    try {
      ws.close();
    } catch {
      // ignore
    }
    ws = null;
  }
  wsConnected = false;
  wsAuthenticated = false;
}

// ─── Main ───────────────────────────────────────────────────────────────────

const config = loadConfig();

async function main(): Promise<void> {
  log('Starting JieGou Claude Code channel server v0.2.0');

  // Connect to Claude Code over stdio
  const transport = new StdioServerTransport();
  await mcp.connect(transport);
  log('MCP stdio transport connected');

  // Connect to JieGou WebSocket (only if channel mode is enabled)
  if (config.channelEnabled) {
    connectWebSocket(config);
  } else {
    log('WebSocket channel mode disabled (set JIEGOU_WS_URL to enable)');
  }

  // Graceful shutdown
  const shutdown = () => {
    log('Shutting down...');
    cleanupWebSocket();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((err) => {
  log('Fatal error:', err);
  process.exit(1);
});
