#!/usr/bin/env python3
"""substrate.py — JieGou substrate worker CLI (plugin edition, standalone).

Connects THIS machine's Claude Code seat to the JieGou management plane as a
governed "substrate worker": the console dispatches approved work, the local
session executes it at your flat subscription rate, and results report back
with per-agent audit attribution. Your subscription does the work; the plane
makes it governed.

  enroll:   substrate.py login --enroll <code>   # redeem a console code → keychain session
  inspect:  substrate.py whoami                  # identity, account, scopes, expiry
  work:     substrate.py pull                    # what does the plane want from me?
            substrate.py push '<items-json>'     # send drafts/items to the approval queue
            substrate.py start --command <cmdId>       # mark a command as picked up
            substrate.py progress --command <cmdId> "phase message" \
                [--step K --total N]             # mid-run beat (L1 progress-streaming)
            substrate.py report [--item <id>] [--command <id>] [--note "…"]  (one of --item/--command required) \
                [--artifact <path>] [--failed]
  daemon:   substrate.py wake --on-wake "<cmd>"  # hold the SSE doorbell; run <cmd>
                                                 # on connect/wake/10-min heartbeat
                                                 # (installed by setup_pull.py --wake)
  session:  substrate.py refresh                 # force a token rotation (else automatic)
            substrate.py logout                  # forget the session on this device

Enrollment codes are minted by an account Owner/Admin in the JieGou console
(Settings → Hybrid → Add agent) — single-use, 10-minute TTL. The exchange
yields a short-lived access JWT (~1h, auto-refreshed) plus a rotating refresh
token (~90d) stored in the OS keychain (macOS Security / libsecret; 0600 file
fallback). No platform credential ever lands on this device, and an admin can
revoke the seat from the console at any time.

Config (all optional): JIEGOU_CONSOLE_URL (default https://console.jiegou.ai),
JIEGOU_AGENT_NAME (default: current directory name), SUBSTRATE_TIMEOUT (s).
Requires Python 3.9+ (macOS/Linux; Windows via WSL).
"""

import base64
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

KEYCHAIN_SERVICE = "jiegou-substrate"
_SESSION = None
_SESSION_LOADED = False


def _seat_name():
    return os.environ.get("JIEGOU_AGENT_NAME") or os.path.basename(os.getcwd())


def _console_base():
    return (os.environ.get("JIEGOU_CONSOLE_URL") or "https://console.jiegou.ai").rstrip("/")


# ── Keychain-held session ────────────────────────────────────────────────────


def _keychain_account():
    return f"session:{_seat_name()}"


def _fallback_path():
    return os.path.expanduser(f"~/.jiegou/substrate-session-{_seat_name()}.json")


def _store_backend():
    if sys.platform == "darwin" and shutil.which("security"):
        return "macos-keychain"
    if shutil.which("secret-tool"):
        return "libsecret"
    return "file(0600)"


def keychain_set(blob):
    acct, backend = _keychain_account(), _store_backend()
    if backend == "macos-keychain":
        subprocess.run(
            ["security", "add-generic-password", "-U", "-a", acct, "-s", KEYCHAIN_SERVICE, "-w", blob],
            check=True, capture_output=True,
        )
    elif backend == "libsecret":
        subprocess.run(
            ["secret-tool", "store", "--label", KEYCHAIN_SERVICE, "service", KEYCHAIN_SERVICE, "account", acct],
            input=blob.encode(), check=True, capture_output=True,
        )
    else:
        p = _fallback_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, blob.encode())
        finally:
            os.close(fd)
    return backend


def keychain_get():
    acct, backend = _keychain_account(), _store_backend()
    if backend == "macos-keychain":
        r = subprocess.run(
            ["security", "find-generic-password", "-a", acct, "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True,
        )
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    if backend == "libsecret":
        r = subprocess.run(
            ["secret-tool", "lookup", "service", KEYCHAIN_SERVICE, "account", acct],
            capture_output=True, text=True,
        )
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    p = _fallback_path()
    if os.path.exists(p):
        with open(p) as f:
            return f.read().strip()
    return None


def keychain_clear():
    acct, backend = _keychain_account(), _store_backend()
    if backend == "macos-keychain":
        subprocess.run(
            ["security", "delete-generic-password", "-a", acct, "-s", KEYCHAIN_SERVICE],
            capture_output=True,
        )
    elif backend == "libsecret":
        subprocess.run(
            ["secret-tool", "clear", "service", KEYCHAIN_SERVICE, "account", acct],
            capture_output=True,
        )
    p = _fallback_path()
    if os.path.exists(p):
        os.remove(p)


def load_session(force=False):
    global _SESSION, _SESSION_LOADED
    if _SESSION_LOADED and not force:
        return _SESSION
    raw = keychain_get()
    try:
        _SESSION = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        _SESSION = None
    _SESSION_LOADED = True
    return _SESSION


def save_session(pair):
    global _SESSION, _SESSION_LOADED
    keychain_set(json.dumps(pair))
    _SESSION, _SESSION_LOADED = pair, True


def clear_session():
    global _SESSION, _SESSION_LOADED
    keychain_clear()
    _SESSION, _SESSION_LOADED = None, True


# ── HTTP + session refresh ───────────────────────────────────────────────────


def _jwt_claims(token):
    """Decode (NOT verify) a JWT payload for local display — scopes/role/exp."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _http_json(method, url, body=None, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers or {"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(
            req, timeout=float(os.environ.get("SUBSTRATE_TIMEOUT", "60"))
        ) as resp:
            return resp.getcode(), json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": f"http_{e.code}"}
    except urllib.error.URLError as e:
        sys.exit(f"substrate: cannot reach the plane — {e.reason}")


def _do_refresh(sess):
    rt = sess.get("refreshToken")
    if not rt:
        sys.exit("substrate: session has no refresh token — re-enroll with `login --enroll <code>`")
    status, out = _http_json("POST", f"{_console_base()}/api/agent/token", {"refreshToken": rt})
    if status != 200:
        sys.exit(
            f"substrate: session refresh failed ({out.get('error', '?')}) — "
            "re-enroll: `substrate.py login --enroll <code>`"
        )
    save_session(out)
    return out


def _expires_in(iso):
    if not iso:
        return None
    try:
        from datetime import datetime

        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.timestamp() - time.time()
    except Exception:
        return None


def _session_bearer():
    sess = load_session()
    if not sess:
        return None
    left = _expires_in(sess.get("accessExpiresAt"))
    if left is None or left < 60:
        sess = _do_refresh(sess)
    return sess["accessToken"], sess["agentId"], _console_base()


def api(method, path, body=None):
    """Call a per-agent hybrid route with the keychain JWT session (auto-refresh,
    one reactive retry on 401)."""
    sess = _session_bearer()
    if not sess:
        sys.exit(
            "substrate: not enrolled on this device.\n"
            "  Ask an account Owner/Admin to mint a code (console → Settings → Hybrid → Add agent), then:\n"
            "    substrate.py login --enroll <code>"
        )
    token, agent_id, base = sess

    def _call(tok, aid):
        return _http_json(
            method,
            f"{base}/api/hybrid-agents/{aid}/{path}",
            body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
        )

    status, data = _call(token, agent_id)
    if status == 401:
        s = load_session(force=True)
        if s and s.get("refreshToken"):
            ns = _do_refresh(s)
            status, data = _call(ns["accessToken"], ns["agentId"])
    if status >= 400:
        sys.exit(f"substrate: HTTP {status} on {path}\n{json.dumps(data)}")
    return data


# ── Commands ─────────────────────────────────────────────────────────────────


def _device_info():
    return {"host": socket.gethostname(), "os": platform.platform(), "clone": _seat_name()}


def cmd_whoami():
    sess = load_session()
    if not sess:
        sys.exit("substrate: not enrolled — `substrate.py login --enroll <code>`")
    c = _jwt_claims(sess.get("accessToken", ""))
    left = _expires_in(sess.get("accessExpiresAt"))
    left_s = f"{int(left)}s" if left is not None and left > 0 else "expired (auto-refreshes)"
    print(
        f"agent:   {sess.get('agentId')}\n"
        f"plane:   {_console_base()}\n"
        f"seat:    {_seat_name()}\n"
        f"auth:    session (enrollment JWT, {_store_backend()})\n"
        f"user:    {c.get('act', {}).get('sub', '?')}\n"
        f"account: {c.get('accountId', '?')}\n"
        f"role:    {c.get('role', '?')}\n"
        f"scopes:  {', '.join(c.get('scopes', [])) or '—'}\n"
        f"access:  expires in {left_s}"
    )


def cmd_login(argv):
    if "--enroll" in argv:
        i = argv.index("--enroll")
        code = argv[i + 1] if i + 1 < len(argv) else None
        if not code:
            sys.exit("substrate login: --enroll requires a <code>")
        status, out = _http_json(
            "POST", f"{_console_base()}/api/agent/enroll",
            {"code": code, "deviceInfo": _device_info()},
        )
        if status != 201:
            err = out.get("error", "?")
            hint = {
                "code_expired": " — codes live 10 min; mint a fresh one",
                "code_used": " — that code was already redeemed; mint a new one",
                "invalid_code": " — check the code, or mint a new one in the console",
            }.get(err, "")
            sys.exit(f"substrate login: enrollment rejected ({err}, HTTP {status}){hint}")
        backend = keychain_set(json.dumps(out))
        save_session(out)
        c = _jwt_claims(out.get("accessToken", ""))
        print(
            f"substrate: enrolled as {out['agentId']} ({backend}).\n"
            f"  account: {c.get('accountId', '?')}   role: {c.get('role', '?')}\n"
            f"  scopes:  {', '.join(c.get('scopes', [])) or '—'}\n"
            f"  session: access ~1h (auto-refreshed), refresh ~90d. `substrate.py whoami` to inspect."
        )
        return
    sess = load_session()
    if not sess:
        sys.exit(
            "substrate login: no active session.\n"
            "  Mint a code in the console (Settings → Hybrid → Add agent), then:\n"
            "    substrate.py login --enroll <code>"
        )
    cmd_whoami()


def cmd_refresh():
    sess = load_session()
    if not sess:
        sys.exit("substrate refresh: not logged in — `substrate.py login --enroll <code>`")
    out = _do_refresh(sess)
    left = _expires_in(out.get("accessExpiresAt"))
    print(
        f"substrate: session refreshed — new access expires in "
        f"{int(left) if left else '?'}s; refresh valid to {out.get('refreshExpiresAt', 'n/a')}."
    )


def cmd_logout():
    had = load_session() is not None
    clear_session()
    print("substrate: session cleared from this device." if had else "substrate: no session to clear.")


def cmd_pull(argv=None):
    # --if-enrolled: silent no-op when this seat has no session (used by the
    # plugin's SessionStart hook so un-enrolled installs stay quiet).
    if argv and "--if-enrolled" in argv and load_session() is None:
        return
    out = api("GET", "work")
    cmds, items = out.get("commands", []), out.get("items", [])
    print(f"substrate work for {out['agent']['name']} ({out['agent']['id']}):")
    if not cmds and not items:
        print("  (nothing assigned — the plane has no work for this agent)")
        return
    for c in cmds:
        p = c.get("payload", {})
        print(f"  COMMAND {c['id']}  item={p.get('itemId')}  {p.get('title', '')[:70]}")
    for i in items:
        print(f"  ITEM    {i['id']}  [{i.get('bundle')}/{i.get('kind')}]  {i.get('title', '')[:70]}")
        msg = (i.get("payload") or {}).get("message")
        if msg:
            print(f"          ↳ {str(msg)[:100]}")
    print(
        f"\n{len(cmds)} command(s), {len(items)} item(s). "
        "Complete with: substrate.py report --item <itemId> [--command <cmdId>] (item=None -> report --command <cmdId> alone)"
    )


def cmd_push(argv):
    """Send draft items into the account's governed approval queue (cockpit).
    Items are drafts — a human approves before anything executes."""
    if not argv:
        sys.exit('substrate push: usage — substrate.py push \'{"items":[…]}\' (or \'[…]\')')
    try:
        payload = json.loads(argv[0])
    except ValueError as e:
        sys.exit(f"substrate push: bad JSON — {e}")
    if isinstance(payload, list):
        payload = {"items": payload}
    out = api("POST", "cockpit-ingest", payload)
    results = out.get("results", [])
    print(f"substrate: pushed {len(results)} item(s) to the approval queue.")
    for r in results:
        print(f"  {r.get('externalId', '?')}: {r.get('action', '?')}")


def cmd_report(args):
    item = args.get("--item")
    cmd = args.get("--command")
    if not item and not cmd:
        sys.exit("substrate report: --item <itemId> (or --command <cmdId> for an item-less command) required")
    result = {}
    if args.get("--note"):
        result["note"] = args["--note"]
    if args.get("--artifact"):
        result["artifactFile"] = args["--artifact"]
    if not item:
        # Item-less plane command (pull showed item=None — e.g. a hook dispatch whose
        # deliverable is a gated draft, pushed separately): complete it directly.
        # 0.10.2 fix — before this, item-less commands had NO close path from the seat
        # (first unattended run delivered its drafts, then left 3 commands dangling).
        api("PUT", f"commands/{cmd}", {
            "action": "complete",
            "success": "--failed" not in args,
            "result": result,
        })
        print(f"substrate: reported {'FAILURE' if '--failed' in args else 'completion'} — command {cmd} closed (no item)")
        return
    body = {"itemId": item, "success": "--failed" not in args, "result": result}
    if cmd:
        body["commandId"] = cmd
    out = api("POST", "report", body)
    state = (out.get("item") or {}).get("state")
    print(f"substrate: reported {'FAILURE' if '--failed' in args else 'completion'} — item state: {state}")


def _parse_flags(argv):
    args = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                args[a] = argv[i + 1]
                i += 2
            else:
                args[a] = True
                i += 1
        else:
            i += 1
    return args


def _positionals(argv):
    """Leftover positional args, using _parse_flags's consumption rule
    (a --flag eats the next non--- token)."""
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                i += 2
            else:
                i += 1
        else:
            pos.append(a)
            i += 1
    return pos


def cmd_start(args):
    """Mark a command as picked up ("seat started"). Fire-and-forget — a failed
    ping never stops the run (the first progress beat also acknowledges)."""
    cmd_id = args.get("--command")
    if not cmd_id:
        sys.exit("substrate start: --command <cmdId> required")
    try:
        api("PUT", f"commands/{cmd_id}", {"action": "acknowledge"})
        print(f"substrate: started — command {cmd_id} acknowledged")
    except (Exception, SystemExit):
        print("substrate: start ping failed (ignored — run continues)")


def cmd_progress(argv):
    """Post one mid-run progress beat (L1 progress-streaming). NEVER fails the
    run: progress is best-effort and advisory — it does not replace the
    exactly-once final report."""
    args = _parse_flags(argv)
    pos = _positionals(argv)
    cmd_id = args.get("--command")
    msg = pos[0] if pos else args.get("--message")
    if not cmd_id or not isinstance(msg, str) or not msg.strip():
        sys.exit(
            'substrate progress: usage — substrate.py progress --command <cmdId> "message" '
            "[--step K --total N] [--phase slug]"
        )
    body = {"action": "progress", "message": msg.strip()[:500]}
    if isinstance(args.get("--phase"), str):
        body["phase"] = args["--phase"][:60]
    try:
        if args.get("--step"):
            body["step"] = int(args["--step"])
        if args.get("--total"):
            body["totalSteps"] = int(args["--total"])
    except (TypeError, ValueError):
        sys.exit("substrate progress: --step/--total must be integers")
    try:
        api("PUT", f"commands/{cmd_id}", body)
        print(f"substrate: progress — {body['message'][:70]}")
    except (Exception, SystemExit):
        print("substrate: progress post failed (ignored — run continues)")


# ── SSE-wake daemon (0.11.0 — spec 2026-08-13) ──────────────────────────────
#
# `substrate.py wake --on-wake "<command>"` holds the per-seat SSE doorbell
# (GET /api/hybrid-agents/<id>/wake) and runs <command> — the seat's existing
# lockfile-guarded pull wrapper — on connect, on every `wake` frame, and on a
# 10-minute internal heartbeat. The stream is a doorbell, never a delivery
# truck: frames carry a count, the pull path is unchanged and authoritative.
#
# Resilience: 45s socket read timeout (3 missed server keepalives) detects
# dead connections (slept laptop); capped exponential backoff on reconnect
# (1s→30s, reset after a healthy connect); server `event: bye` (~50 min
# lifetime recycle) reconnects immediately; 401 forces a session refresh.
# The heartbeat floor means total SSE failure degrades to slow-but-correct.

WAKE_READ_TIMEOUT = 45  # 3 missed 15s server keepalives = dead connection
WAKE_HEARTBEAT = 600  # safety-net pull cadence while connected
WAKE_BACKOFF_MAX = 30


def _wake_log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} wake: {msg}"
    print(line, flush=True)


def _run_on_wake(command):
    try:
        subprocess.run(["/bin/bash", "-c", command], check=False)
    except Exception as e:  # never let the pull body kill the daemon
        _wake_log(f"on-wake failed: {e}")


def cmd_wake(args):
    on_wake = args.get("--on-wake")
    if not on_wake:
        sys.exit('substrate wake: --on-wake "<command>" required (the seat pull wrapper)')
    backoff = 1
    last_run = 0.0

    def run_now(reason):
        nonlocal last_run
        _wake_log(f"pull ({reason})")
        _run_on_wake(on_wake)
        last_run = time.time()

    while True:
        sess = _session_bearer()
        if not sess:
            _wake_log("not enrolled — retrying in 60s")
            time.sleep(60)
            continue
        token, agent_id, base = sess
        req = urllib.request.Request(
            f"{base}/api/hybrid-agents/{agent_id}/wake",
            headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
        )
        try:
            with urllib.request.urlopen(req, timeout=WAKE_READ_TIMEOUT) as resp:
                _wake_log(f"connected ({resp.getcode()})")
                backoff = 1
                # Belt-and-suspenders catch-up: server emits-on-connect too,
                # but a client-side pull on every (re)connect closes any gap.
                run_now("connect")
                event = None
                while True:
                    if time.time() - last_run > WAKE_HEARTBEAT:
                        run_now("heartbeat")
                    raw = resp.readline()  # blocks ≤ WAKE_READ_TIMEOUT
                    if not raw:
                        _wake_log("stream ended")
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                    elif line == "" and event:
                        if event == "wake":
                            run_now("wake")
                        elif event == "bye":
                            _wake_log("server recycle (bye)")
                            event = None
                            break
                        event = None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                _wake_log("401 — refreshing session")
                s = load_session(force=True)
                if s:
                    try:
                        _do_refresh(s)
                    except SystemExit:
                        pass
            else:
                _wake_log(f"http {e.code}")
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            # Read timeout here means no keepalive for 45s — dead connection
            # (slept laptop, dropped proxy). Heartbeat semantics survive via
            # the immediate run-on-reconnect above.
            _wake_log(f"disconnected: {getattr(e, 'reason', e)}")
        except Exception as e:
            _wake_log(f"unexpected: {e}")
        time.sleep(backoff)
        backoff = min(backoff * 2, WAKE_BACKOFF_MAX)


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__.strip())
    cmd = argv[0]
    if cmd == "whoami":
        cmd_whoami()
    elif cmd == "login":
        cmd_login(argv[1:])
    elif cmd == "refresh":
        cmd_refresh()
    elif cmd == "logout":
        cmd_logout()
    elif cmd == "pull":
        cmd_pull(argv[1:])
    elif cmd == "push":
        cmd_push(argv[1:])
    elif cmd == "start":
        cmd_start(_parse_flags(argv[1:]))
    elif cmd == "progress":
        cmd_progress(argv[1:])
    elif cmd == "report":
        cmd_report(_parse_flags(argv[1:]))
    elif cmd == "wake":
        cmd_wake(_parse_flags(argv[1:]))
    else:
        sys.exit(f"substrate: unknown command '{cmd}'\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
