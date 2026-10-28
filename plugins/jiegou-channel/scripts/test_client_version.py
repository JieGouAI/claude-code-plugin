#!/usr/bin/env python3
"""
test_client_version.py: tripwire for the X-Substrate-Client header (0.16.1).

Every plane call substrate.py makes must carry
`X-Substrate-Client: jiegou-plugin/<plugin.json version>`, in the shape the
plane's parser accepts, so the plane can record which client version claimed,
pulled and reported each command. A missing or unreadable plugin.json reads
`jiegou-plugin/unknown` and never blocks the call.

    python3 plugins/jiegou-channel/scripts/test_client_version.py
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import substrate  # noqa: E402

PLANE_PATTERN = re.compile(r"^[a-z0-9-]{1,32}/[0-9A-Za-z.+-]{1,40}$")


class _Resp(io.BytesIO):
    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sent_header(call):
    seen = []
    real = substrate.urllib.request.urlopen
    substrate.urllib.request.urlopen = lambda req, timeout=None: (
        seen.append(dict(req.header_items())) or _Resp(b"{}")
    )
    try:
        call()
    finally:
        substrate.urllib.request.urlopen = real
    if not seen:
        return None, None
    h = seen[0]
    v = next((v for k, v in h.items() if k.lower() == "x-substrate-client"), None)
    return v, h


def main():
    failures = []
    with open(os.path.join(HERE, "..", ".claude-plugin", "plugin.json")) as f:
        want = "jiegou-plugin/" + json.load(f)["version"]

    substrate._CLIENT_VERSION = None
    v, h = sent_header(lambda: substrate._http_json(
        "POST", "https://example.invalid/x", {"a": 1},
        headers={"Content-Type": "application/json", "Authorization": "Bearer t"}))
    if v != want:
        failures.append(f"expected {want!r}, sent {v!r}")
    elif not PLANE_PATTERN.match(v):
        failures.append(f"{v!r} would be rejected by the plane's parser")
    if h is not None and not any(k.lower() == "authorization" for k in h):
        failures.append("the caller's Authorization header must survive")

    substrate._CLIENT_VERSION = None
    real_open = open
    try:
        substrate.open = lambda *a, **k: (_ for _ in ()).throw(OSError("no plugin.json"))
        v, _ = sent_header(lambda: substrate._http_json("GET", "https://example.invalid/y"))
    finally:
        del substrate.open
        substrate._CLIENT_VERSION = None
    if v != "jiegou-plugin/unknown":
        failures.append(f"unreadable plugin.json must read jiegou-plugin/unknown, got {v!r}")

    if failures:
        print("FAIL:\n  " + "\n  ".join(failures))
        return 1
    print(f"ok: X-Substrate-Client {want} on every plane call (unknown when plugin.json is unreadable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
