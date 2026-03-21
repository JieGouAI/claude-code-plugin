# JieGou Channel for Claude Code

Connect your Claude Code session to the [JieGou](https://jiegou.ai) AI workflow automation platform. Receive governed tasks from the JieGou console and send results back — with full audit trails, approval gates, and RBAC.

## What It Does

- **Receive tasks** from the JieGou console as `<channel source="jiegou">` events
- **Send results back** via the `jiegou_reply` tool
- **Check status** with the `jiegou_status` tool or `/jiegou:status` skill
- **WebSocket connection** to `wss://mcp.jiegou.ai` with heartbeat and auto-reconnect
- **HMAC authentication** via API key — no credentials sent to Claude Code

## Install

### From the official marketplace (once approved)

```bash
/plugin install jiegou@claude-plugins-official
```

Then launch with:

```bash
claude --channels plugin:jiegou@claude-plugins-official
```

### For development / testing

```bash
# Clone the repo
git clone https://github.com/JieGouAI/orion.git
cd orion/console/mcp/claude-code-channel/code

# Install dependencies
bun install  # or npm install

# Launch Claude Code with the plugin
claude --plugin-dir . --dangerously-load-development-channels server:jiegou
```

## Configure

Set these environment variables before launching:

| Variable | Required | Description |
|----------|----------|-------------|
| `JIEGOU_API_KEY` | Yes | Your JieGou platform API key (starts with `jgk_`) |
| `JIEGOU_ACCOUNT_ID` | Yes | Your JieGou account ID |
| `JIEGOU_WS_URL` | No | WebSocket URL (default: `wss://mcp.jiegou.ai`) |

### How to get your API key

1. Log in to [console.jiegou.ai](https://console.jiegou.ai)
2. Go to **Settings → Developer**
3. Click **Create Key**
4. Choose the **Channel / MCP** scope (or **Full Access** for all operations)
5. Copy the key immediately — it's only shown once
6. The key looks like `jgk_a1b2c3d4e5f6...`

### How to find your Account ID

1. Go to **Settings → Account**
2. Your Account ID is displayed at the top of the page

You can set them in the `.mcp.json` env block or export them in your shell.

## Skills

| Skill | Description |
|-------|-------------|
| `/jiegou:status` | Check WebSocket connection status and account info |
| `/jiegou:dispatch` | Send task results back to JieGou |

## Tools

| Tool | Description |
|------|-------------|
| `jiegou_reply` | Send task results back (task_id, status, result, files) |
| `jiegou_status` | Report current connection state |

## How It Works

1. Claude Code spawns this plugin as a subprocess
2. The plugin connects to `wss://mcp.jiegou.ai` via WebSocket
3. When a task is created in the JieGou console, it arrives instantly as a channel event
4. Claude Code sees `<channel source="jiegou" task_id="..." task_type="...">` and executes the task
5. Claude Code calls `jiegou_reply` to send results back
6. Results appear in the JieGou console at `/deploy/channels`

## Security

- **Authentication**: Bearer token via API key (never shared with Claude Code)
- **Sender gating**: Only tasks from your own JieGou account are dispatched
- **HMAC verification**: WebSocket messages are authenticated
- **Local-only**: The plugin runs on your machine — no remote code execution
- **Audit trail**: Every task dispatch and result is logged in JieGou's audit system
- **Claude Code permissions**: The existing permission model (tool approval, file access) still applies

## Architecture

```
JieGou Console → JieGou API → wss://mcp.jiegou.ai → This Plugin ←stdio→ Claude Code
```

The plugin bridges the JieGou platform (governance, workflows, audit trails) with Claude Code's local execution capabilities (filesystem, terminal, git, browser).

## License

MIT
