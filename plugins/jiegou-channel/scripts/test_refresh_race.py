#!/usr/bin/env python3
"""
test_refresh_race.py: tripwire for the refresh-token race (0.16.3).

The wake daemon and the pull it fires are two processes on one seat. Rotation
kills the old refresh token at once, so the one that refreshes second presents
a dead token. _do_refresh must then adopt the pair the winner saved instead of
exiting (the daemon used to die here). A genuinely dead session still exits.

    python3 plugins/jiegou-channel/scripts/test_refresh_race.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import substrate  # noqa: E402

FUTURE = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
fails = []

saved = (substrate._http_json, substrate.load_session)
substrate._http_json = lambda *a, **k: (401, {"error": "invalid_refresh"})
try:
    winner = {"refreshToken": "rt-new", "accessToken": "at-new", "agentId": "a", "accessExpiresAt": FUTURE}
    substrate.load_session = lambda force=False: winner
    got = substrate._do_refresh({"refreshToken": "rt-old"})
    if got is not winner:
        fails.append("lost race did not adopt the winner's saved pair")

    substrate.load_session = lambda force=False: {"refreshToken": "rt-old", "accessExpiresAt": FUTURE}
    try:
        substrate._do_refresh({"refreshToken": "rt-old"})
        fails.append("dead session (keychain unchanged) did not exit")
    except SystemExit:
        pass
finally:
    substrate._http_json, substrate.load_session = saved

if fails:
    print("FAIL: " + "; ".join(fails))
    sys.exit(1)
print("ok: a lost refresh race adopts the winner's pair; a dead session still exits")
