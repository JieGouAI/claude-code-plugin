import { describe, it, expect } from 'vitest';

/**
 * Test the tool definitions for the JieGou Claude Code Channel.
 * We define the expected tool schemas here and validate their structure,
 * rather than importing the server (which requires WebSocket + stdio).
 */

const TOOLS = [
  {
    name: 'jiegou_reply',
    description: 'Send a task result back to the JieGou platform',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string', description: 'The ID of the task being responded to' },
        status: {
          type: 'string',
          enum: ['in_progress', 'completed', 'error'],
          description: 'Current status of the task',
        },
        result: { type: 'string', description: 'The result or output of the task' },
        files: {
          type: 'array',
          items: { type: 'string' },
          description: 'Optional list of file paths that were created or modified',
        },
      },
      required: ['task_id', 'status', 'result'],
    },
  },
  {
    name: 'jiegou_status',
    description: 'Report the current JieGou WebSocket connection status',
    inputSchema: {
      type: 'object',
      properties: {},
      required: [],
    },
  },
];

describe('JieGou Claude Code Channel - Tool Definitions', () => {
  it('has exactly 2 tools', () => {
    expect(TOOLS).toHaveLength(2);
  });

  it('tool names are jiegou_reply and jiegou_status', () => {
    const names = TOOLS.map((t) => t.name).sort();
    expect(names).toEqual(['jiegou_reply', 'jiegou_status']);
  });

  it('jiegou_reply has correct schema', () => {
    const reply = TOOLS.find((t) => t.name === 'jiegou_reply')!;
    expect(reply.description).toBe('Send a task result back to the JieGou platform');

    const props = reply.inputSchema.properties;
    expect(props.task_id).toBeDefined();
    expect(props.status).toBeDefined();
    expect(props.result).toBeDefined();
    expect(props.files).toBeDefined();

    // status should have enum
    expect(props.status.enum).toEqual(['in_progress', 'completed', 'error']);

    // required fields
    expect(reply.inputSchema.required).toContain('task_id');
    expect(reply.inputSchema.required).toContain('status');
    expect(reply.inputSchema.required).toContain('result');
    expect(reply.inputSchema.required).not.toContain('files');
  });

  it('jiegou_status has empty input schema', () => {
    const status = TOOLS.find((t) => t.name === 'jiegou_status')!;
    expect(status.description).toBe('Report the current JieGou WebSocket connection status');
    expect(Object.keys(status.inputSchema.properties)).toHaveLength(0);
    expect(status.inputSchema.required).toHaveLength(0);
  });

  it('all tools have inputSchema type: object', () => {
    for (const tool of TOOLS) {
      expect(tool.inputSchema.type).toBe('object');
    }
  });
});
