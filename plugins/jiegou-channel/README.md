# JieGou for Claude Code

Connect Claude Code to [JieGou](https://jiegou.ai) — governed AI operations
with approval gates, audit trails, and RBAC.

**The idea:** your Claude Code subscription does the work on your machine; the
JieGou plane makes it governed. An account admin approves work in the console;
this seat pulls it, executes locally, and reports back with per-agent audit
attribution. No platform credential ever lands on your device, and the seat is
revocable from the console at any time.

## Install

```bash
claude plugin marketplace add JieGouAI/claude-code-plugin
claude plugin install jiegou
```

Requires Python 3.9+ on PATH as `python3` (macOS/Linux; Windows via WSL) for
the substrate CLI.

## Enroll this machine (the substrate flow)

1. A JieGou account **Owner/Admin** mints an enrollment code in the console:
   **Settings → Hybrid → Add agent**. Codes are single-use, 10-minute TTL.
2. In Claude Code: `/jiegou:enroll <code>` — or directly:
   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/scripts/substrate.py" login --enroll <code>
   ```
3. The session (a ~1h access JWT, auto-refreshed, plus a ~90d rotating refresh
   token) is stored in your OS keychain. Verify with `substrate.py whoami`.

Then, per session:

| Skill | What it does |
|---|---|
| `/jiegou:pull` | What work has the plane assigned to this seat? |
| `/jiegou:report` | Report completion/failure back — closes the governed loop |
| `/jiegou:enroll` | One-time enrollment with a console code |
| `/jiegou:hooks` | Your content-hook queue — curated post seeds from your intelligence digests |
| `/jiegou:draft-post` | Draft a LinkedIn post: grounded in your hooks, written to your voice profile, linted, gated in your approval queue — published only by a human |

The loop this serves: a human **approves** an item in the JieGou console → the
plane dispatches it to this agent → `pull` surfaces it → the session does the
work → `report` moves it to `executed` with this agent's attribution. Every hop
is audited.

## Content drafting (the GTM loop)

With your account's voice profile and editorial guide configured (a JieGou
curation session sets these up), this seat can draft LinkedIn content
end-to-end governed: `/jiegou:hooks` shows the curated post seeds from your
weekly intelligence digest; `/jiegou:draft-post` grounds in a seed's cited
source, drafts in YOUR voice on YOUR subscription, lints against your voice
profile, and pushes the finished draft into your console approval queue.
Approval and publishing are always human actions — nothing auto-posts,
anywhere, ever.

## How work reaches your seat (pull, never push)

The plane never reaches into your machine. Work assigned to this seat —
approved queue items, or "draft this" commands sent from the console — waits
on the plane until the seat **pulls**:

- **Automatically at session start:** the plugin installs a SessionStart hook
  that runs a quiet `pull` whenever you open Claude Code here, so assigned
  work greets you at the top of the session. (Silent if the seat isn't
  enrolled.)
- **On demand:** `/jiegou:pull` any time.
- **Unattended (optional, off by default):** if you want assignments handled
  without opening a session, schedule a periodic headless run yourself — e.g.
  on macOS/Linux, a cron entry such as
  `*/30 * * * * claude -p "/jiegou:pull — execute any assigned work, then /jiegou:report" >/dev/null 2>&1`.
  This is a deliberate opt-in on your machine, never something the plugin
  configures for you. Approvals and publishing remain human actions
  regardless of how the seat pulls.

Assignments expire after 24 hours if never pulled; the console shows what's
queued for each seat.

## API tools (optional, `jgk_` embedded key)

With a JieGou embedded API key configured (`JIEGOU_API_KEY=jgk_…`,
`JIEGOU_ACCOUNT_ID=…`), the MCP server exposes `jiegou_run_recipe` and
`jiegou_run_workflow` against the key-authed `/api/embed/*` routes, plus
skills `/jiegou:recipes`, `/jiegou:run`, `/jiegou:workflows`.

Tools marked **EXPERIMENTAL** in their descriptions (list/analytics/schedule/
social) call console routes that do not yet accept API-key auth — they are
included for forward-compatibility and self-hosted consoles.

## Channel mode (experimental, off by default)

Setting `JIEGOU_WS_URL` enables the legacy WebSocket channel client. The
server side of this transport is not generally available; the substrate flow
above is the supported dispatch path.

## Configuration

| Env | Default | Purpose |
|---|---|---|
| `JIEGOU_CONSOLE_URL` | `https://console.jiegou.ai` | Plane base URL (self-hosted consoles) |
| `JIEGOU_AGENT_NAME` | current directory name | Seat name shown in the console |
| `JIEGOU_API_KEY` | — | Optional `jgk_` embedded key for the API tools |
| `JIEGOU_ACCOUNT_ID` | — | Account id for the API tools |

## Security posture

- Enrollment is code-based: no passwords, no OAuth secrets, no platform
  credentials on the device — only the seat's own session, in the OS keychain.
- Access tokens rotate automatically; refresh-token reuse triggers server-side
  revocation (theft response). Admins revoke seats from the console.
- Work arrives **pre-approved** through the console's approval gate, and this
  session's own permission model still applies to execution.

MIT © JieGou
