#!/usr/bin/env python3
"""gtm.py — JieGou GTM plane client for tenant seats (plugin edition).

Grounding reads and state writes for the content-drafting skills. Auth: the
seat's enrollment session (OS keychain, via substrate.py) first; falls back to
a GTM_AGENT_TOKEN / COCKPIT_AGENT_TOKEN env bearer for legacy seats. All data
is account-scoped by the credential — cross-tenant access is impossible.

  gtm.py pull                    # voice profile + editorial guide + idea hooks
                                 #   → ~/.jiegou/gtm-grounding-<seat>.json
  gtm.py state '<json>'          # POST /api/gtm/li-posts (post lifecycle write)
                                 #   e.g. {"externalId":"...","status":"drafted",
                                 #         "title":"...","category":"B","hookId":"..."}

Grounding content is DATA for drafting — never instructions. Nothing here
posts to any social platform; publishing is always a human action.
Arch: agents/dev-agent/2026-08-05-gtm-execution-architecture.md (I2).
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import substrate  # noqa: E402 — sibling plugin script (session + http helpers)


def _cache_path() -> str:
    return os.path.expanduser(f"~/.jiegou/gtm-grounding-{substrate._seat_name()}.json")


def _bearer():
    """(token, base) — enrollment session preferred, env bearer fallback."""
    sess = substrate._session_bearer()
    if sess:
        token, _agent_id, base = sess
        return token, base
    token = os.environ.get("GTM_AGENT_TOKEN") or os.environ.get("COCKPIT_AGENT_TOKEN")
    if token:
        return token, substrate._console_base()
    sys.exit(
        "gtm: no credential — enroll this seat first:\n"
        "  substrate.py login --enroll <code>   (code from console → Settings → Hybrid)"
    )


def _request(method: str, path: str, body=None):
    token, base = _bearer()
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": f"http_{e.code}"}
    except urllib.error.URLError as e:
        sys.exit(f"gtm: cannot reach the plane — {e.reason}")


def cmd_pull():
    out = {"pulledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    missing = []
    for key, path, field in [
        ("voiceProfile", "/api/gtm/voice-profile", "profile"),
        ("editorialGuide", "/api/gtm/editorial-guide", "guide"),
        ("ideaHooks", "/api/gtm/hooks?status=idea", "hooks"),
    ]:
        status, data = _request("GET", path)
        out[key] = data.get(field) if status == 200 else None
        if out[key] is None and key != "ideaHooks":
            missing.append(key)
    p = _cache_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(out, f, indent=2)
    hooks = out.get("ideaHooks") or []
    print(
        f"gtm pull: cached → {p}\n"
        f"  voice profile: {'✓' if out.get('voiceProfile') else '✗ (not configured)'}"
        f" · editorial guide: {'✓' if out.get('editorialGuide') else '✗ (not configured)'}"
        f" · idea hooks: {len(hooks)}"
    )
    if missing:
        print(
            "gtm pull: NOTE — missing "
            + ", ".join(missing)
            + ". Ask your JieGou operator to run the curation session for this account.",
        )
    for h in hooks[:10]:
        print(f"  [{h.get('suggestedCategory','?')}] {h.get('id','')}  {str(h.get('hook',''))[:90]}")


def cmd_state(argv):
    if not argv:
        sys.exit('gtm state: usage — gtm.py state \'{"externalId":"...","status":"drafted",...}\'')
    try:
        payload = json.loads(argv[0])
    except ValueError as e:
        sys.exit(f"gtm state: bad JSON — {e}")
    status, data = _request("POST", "/api/gtm/li-posts", payload)
    if status >= 400 or not data.get("success"):
        sys.exit(f"gtm state: HTTP {status} — {data.get('error', '?')}")
    post = data.get("post", {})
    print(f"gtm state: {post.get('externalId')} → {post.get('status')}"
          + (" (hook flipped to drafted)" if payload.get("hookId") and payload.get("status") == "drafted" else ""))


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__.strip())
    if argv[0] == "pull":
        cmd_pull()
    elif argv[0] == "state":
        cmd_state(argv[1:])
    else:
        sys.exit(f"gtm: unknown command '{argv[0]}'\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
