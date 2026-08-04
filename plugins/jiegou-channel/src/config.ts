export interface ChannelConfig {
  wsUrl?: string;       // Optional — only for channel mode
  baseUrl: string;      // API base URL
  apiKey: string;
  accountId: string;
  heartbeatInterval: number;
  reconnectDelay: number;
  channelEnabled: boolean; // Whether to connect WebSocket
}

/**
 * Load configuration from environment variables.
 *
 * Required:
 *   JIEGOU_API_KEY    — JieGou platform API key (starts with jgk_).
 *                       Get one at: console.jiegou.ai → Settings → Developer → Create Key
 *   JIEGOU_ACCOUNT_ID — Your JieGou account ID.
 *                       Find it at: console.jiegou.ai → Settings → Account
 *
 * Optional:
 *   JIEGOU_WS_URL     — WebSocket URL (default: wss://mcp.jiegou.ai).
 *                        If set, the plugin connects a WebSocket for real-time task dispatch.
 *   JIEGOU_BASE_URL   — Console API base URL (default: https://console.jiegou.ai)
 */
export function loadConfig(): ChannelConfig {
  const apiKey = process.env.JIEGOU_API_KEY;
  if (!apiKey) {
    console.error(
      'Warning: JIEGOU_API_KEY is not set.\n' +
        'Get one at: console.jiegou.ai → Settings → Developer → Create Key\n' +
        'The key starts with jgk_',
    );
  }
  const accountId = process.env.JIEGOU_ACCOUNT_ID;
  if (!accountId) {
    console.error(
      'Warning: JIEGOU_ACCOUNT_ID is not set.\n' +
        'Find it at: console.jiegou.ai → Settings → Account',
    );
  }
  return {
    wsUrl: process.env.JIEGOU_WS_URL || undefined,
    baseUrl: process.env.JIEGOU_BASE_URL || 'https://console.jiegou.ai',
    apiKey: apiKey || '',
    accountId: accountId || '',
    heartbeatInterval: 30_000,
    reconnectDelay: 5_000,
    channelEnabled: !!process.env.JIEGOU_WS_URL,
  };
}
