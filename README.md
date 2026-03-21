# JieGou Plugins for Claude Code

Official [JieGou](https://jiegou.ai) plugins for Claude Code — governed AI workflow automation with approval gates, audit trails, and RBAC.

## Available Plugins

### jiegou (Channel)

Connect your Claude Code session to the JieGou platform. Receive governed tasks from the JieGou console and send results back — with full audit trails, approval gates, and enterprise governance.

**Features:**
- Receive tasks from JieGou console as channel events
- Send results back via the `jiegou_reply` tool
- Check connection status with `/jiegou:status`
- WebSocket connection with heartbeat and auto-reconnect
- HMAC authentication via API key

## Quick Start

### 1. Add the marketplace

```bash
/plugin marketplace add JieGouAI/claude-code-plugin
```

### 2. Install the plugin

```bash
/plugin install jiegou@jiegou-plugins
```

### 3. Configure

Set your JieGou API key and account ID. Get your API key from [console.jiegou.ai](https://console.jiegou.ai) → Settings → Developer → Create Key.

### 4. Launch

```bash
claude --channels plugin:jiegou@jiegou-plugins
```

## Requirements

- Claude Code v2.1.80 or later
- [Bun](https://bun.sh) runtime (for the channel server)
- A JieGou account ([sign up free](https://console.jiegou.ai))

## Documentation

- [JieGou + Claude Code Integration](https://jiegou.ai/solutions/openclaw-integration)
- [Channel Server README](plugins/jiegou-channel/README.md)
- [Claude Code Channels Reference](https://code.claude.com/docs/en/channels-reference)

## Security

- API key authentication (never shared with Claude Code)
- Sender gating — only tasks from your own account
- HMAC-SHA256 verification on WebSocket messages
- Local-only execution — Claude Code's permission model applies
- Full audit trail in JieGou console

## License

MIT
