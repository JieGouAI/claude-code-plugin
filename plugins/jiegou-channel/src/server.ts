#!/usr/bin/env bun

/**
 * JieGou Claude Code Channel Server
 *
 * An MCP server that bridges Claude Code to the JieGou platform.
 * Connects to Claude Code over stdio (MCP protocol) and to the
 * JieGou WebSocket service for receiving tasks and sending results.
 *
 * Tools:
 *   jiegou_reply  — Send a task result back to JieGou
 *   jiegou_status — Report current WebSocket connection status
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { WebSocket } from 'ws';
import { loadConfig, type ChannelConfig } from './config.js';

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

// ─── MCP Server Setup ──────────────────────────────────────────────────────

const server = new McpServer(
  {
    name: 'jiegou-channel',
    version: '1.0.0',
  },
  {
    instructions: [
      'You are connected to the JieGou platform via a WebSocket channel.',
      'When you receive a task notification, work on it using your available tools and context.',
      'Use jiegou_reply to send results back when done.',
      'Use jiegou_status to check the current connection state.',
    ].join(' '),
  },
);

// ─── Tool: jiegou_reply ─────────────────────────────────────────────────────

server.tool(
  'jiegou_reply',
  'Send a task result back to the JieGou platform',
  {
    task_id: z.string().describe('The ID of the task being responded to'),
    status: z
      .enum(['in_progress', 'completed', 'error'])
      .describe('Current status of the task'),
    result: z.string().describe('The result or output of the task'),
    files: z
      .array(z.string())
      .optional()
      .describe('Optional list of file paths that were created or modified'),
  },
  async ({ task_id, status, result, files }) => {
    if (!ws || !wsConnected || !wsAuthenticated) {
      return {
        content: [
          {
            type: 'text' as const,
            text: 'Error: Not connected to JieGou WebSocket. Use jiegou_status to check connection.',
          },
        ],
      };
    }

    const message = JSON.stringify({
      type: 'task_result',
      taskId: task_id,
      status,
      result,
      files,
    });

    try {
      ws.send(message);
      return {
        content: [
          {
            type: 'text' as const,
            text: `Task result sent successfully. task_id=${task_id}, status=${status}`,
          },
        ],
      };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      return {
        content: [
          {
            type: 'text' as const,
            text: `Error sending task result: ${errorMsg}`,
          },
        ],
      };
    }
  },
);

// ─── Tool: jiegou_status ────────────────────────────────────────────────────

server.tool(
  'jiegou_status',
  'Report the current JieGou WebSocket connection status',
  {},
  async () => {
    const status = {
      connected: wsConnected,
      authenticated: wsAuthenticated,
      wsUrl: config.wsUrl,
      accountId: config.accountId,
    };
    return {
      content: [
        {
          type: 'text' as const,
          text: JSON.stringify(status, null, 2),
        },
      ],
    };
  },
);

// ─── WebSocket Connection ───────────────────────────────────────────────────

function connectWebSocket(config: ChannelConfig): void {
  if (ws) {
    cleanupWebSocket();
  }

  log(`Connecting to ${config.wsUrl}...`);

  ws = new WebSocket(config.wsUrl, {
    headers: { Authorization: `Bearer ${config.apiKey}` },
  });

  ws.onopen = () => {
    log('WebSocket connected');
    wsConnected = true;

    // Authenticate
    ws!.send(
      JSON.stringify({
        type: 'authenticate',
        apiKey: config.apiKey,
        clientType: 'claude_code_channel',
        accountId: config.accountId,
      }),
    );

    startHeartbeat(config);
  };

  ws.onmessage = (event: WebSocket.MessageEvent) => {
    const raw = typeof event.data === 'string' ? event.data : event.data.toString();

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

    if (type === 'auth_status') {
      if (data.success) {
        log('Authentication successful');
        wsAuthenticated = true;
      } else {
        log('Authentication failed:', data.message || 'unknown reason');
        wsAuthenticated = false;
      }
      return;
    }

    if (type === 'task') {
      log(`Received task: ${data.taskId}`);
      // Push task as a channel notification to Claude Code.
      // The MCP SDK will deliver this as a notification the client can act on.
      server.server.notification({
        method: 'notifications/message',
        params: {
          level: 'info',
          data: {
            type: 'task',
            taskId: data.taskId,
            title: data.title,
            description: data.description,
            context: data.context,
          },
        },
      });
      return;
    }

    log('Received message type:', type);
  };

  ws.onclose = (event: WebSocket.CloseEvent) => {
    log(`WebSocket closed: code=${event.code} reason=${event.reason || 'none'}`);
    wsConnected = false;
    wsAuthenticated = false;
    stopHeartbeat();
    scheduleReconnect(config);
  };

  ws.onerror = (event: WebSocket.ErrorEvent) => {
    log('WebSocket error:', event.message || 'unknown');
  };
}

// ─── Heartbeat ──────────────────────────────────────────────────────────────

function startHeartbeat(config: ChannelConfig): void {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    ws.send(JSON.stringify({ type: 'ping' }));

    // If no pong within 5 seconds, consider connection dead
    pongTimer = setTimeout(() => {
      log('Heartbeat timeout — no pong received, closing connection');
      ws?.close();
    }, 5_000);
  }, config.heartbeatInterval);
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

function scheduleReconnect(config: ChannelConfig): void {
  if (reconnectTimer) return;
  log(`Reconnecting in ${config.reconnectDelay / 1000}s...`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket(config);
  }, config.reconnectDelay);
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
  log('Starting JieGou Claude Code channel server');

  // Connect to Claude Code over stdio
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log('MCP stdio transport connected');

  // Connect to JieGou WebSocket
  connectWebSocket(config);

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
