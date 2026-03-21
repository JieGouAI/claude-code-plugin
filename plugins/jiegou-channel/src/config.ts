export interface ChannelConfig {
  wsUrl: string;
  apiKey: string;
  accountId: string;
  heartbeatInterval: number;
  reconnectDelay: number;
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
 *   JIEGOU_WS_URL     — WebSocket URL (default: wss://mcp.jiegou.ai)
 */
export function loadConfig(): ChannelConfig {
  const apiKey = process.env.JIEGOU_API_KEY;
  if (!apiKey) {
    console.error(
      'Error: JIEGOU_API_KEY is required.\n' +
        'Get one at: console.jiegou.ai → Settings → Developer → Create Key\n' +
        'The key starts with jgk_',
    );
    process.exit(1);
  }
  const accountId = process.env.JIEGOU_ACCOUNT_ID;
  if (!accountId) {
    console.error(
      'Error: JIEGOU_ACCOUNT_ID is required.\n' +
        'Find it at: console.jiegou.ai → Settings → Account',
    );
    process.exit(1);
  }
  return {
    wsUrl: process.env.JIEGOU_WS_URL || 'wss://mcp.jiegou.ai',
    apiKey,
    accountId,
    heartbeatInterval: 30_000,
    reconnectDelay: 5_000,
  };
}
