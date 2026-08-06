#!/usr/bin/env python3
"""calendar_sync.py — publish-slot reminders for THIS seat's owner.

The plane never touches a calendar and never publishes anything. Reminders
go on the calendar the user ACTUALLY LOOKS AT — which is normally their
connected calendar (Google/Outlook via the session's calendar MCP tools),
handled by the model per /jiegou:calendar-sync. This script's mechanical
Calendar.app path (osascript, macOS-only) is the FALLBACK for seats with no
calendar MCP — useful headless, but it only helps if Calendar.app is signed
into an account the user checks. Publishing remains a human act at the
reminder's time; this is bookkeeping, not automation.

  calendar_sync.py enable --mode mcp             # opt in; session MCP tools do the CRUD
  calendar_sync.py enable --mode local [--calendar "Name"]
                                                 # opt in to the Calendar.app fallback
  calendar_sync.py sync                          # reconcile (local mode) / print MCP work list
  calendar_sync.py desired                       # JSON of desired reminders (for MCP mode)
  calendar_sync.py record <externalId> <slot> <eventRef>   # track an MCP-created event
  calendar_sync.py status | disable

Reconciliation per approved post with a scheduledSlot (YYYY-MM-DD, 09:00
local, 30 min, 15-min alarm): create event if missing, move it if the slot
changed. Tracked events whose post is no longer approved+unshipped (shipped,
rejected, slot cleared) are deleted. Event map: ~/.jiegou/calendar-events-
<seat>.json (shared by both modes so syncs stay idempotent).

Opt-in is explicit: local mode's first osascript call triggers a macOS
Automation permission prompt — never from a hook, always from the user
running /jiegou:calendar-sync.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import substrate  # noqa: E402
import gtm  # noqa: E402

SEAT = substrate._seat_name()
MARKER = os.path.expanduser(f"~/.jiegou/calendar-sync-enabled-{SEAT}.json")
EVENT_MAP = os.path.expanduser(f"~/.jiegou/calendar-events-{SEAT}.json")
DEFAULT_CALENDAR = "Home"
EVENT_HOUR = 9  # slot dates get a 09:00 local reminder


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _osascript(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "osascript failed")
    return r.stdout.strip()


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _calendar_name() -> str:
    return _load(MARKER, {}).get("calendar", DEFAULT_CALENDAR)


def _event_dates(slot: str):
    d = datetime.strptime(slot, "%Y-%m-%d")
    return d.replace(hour=EVENT_HOUR), d.replace(hour=EVENT_HOUR, minute=30)


def create_event(title: str, slot: str, description: str) -> str:
    start, end = _event_dates(slot)
    cal = _esc(_calendar_name())
    script = f'''
    set startDate to current date
    set year of startDate to {start.year}
    set month of startDate to {start.month}
    set day of startDate to {start.day}
    set time of startDate to {start.hour * 3600 + start.minute * 60}
    set endDate to startDate + (30 * minutes)
    tell application "Calendar"
        tell calendar "{cal}"
            set ev to make new event with properties {{summary:"{_esc(title)}", start date:startDate, end date:endDate, description:"{_esc(description)}"}}
            tell ev to make new display alarm at end with properties {{trigger interval:-15}}
            return uid of ev
        end tell
    end tell'''
    return _osascript(script)


def delete_event(uid: str) -> bool:
    cal = _esc(_calendar_name())
    script = f'''
    tell application "Calendar"
        tell calendar "{cal}"
            try
                delete (first event whose uid is "{_esc(uid)}")
                return "ok"
            on error
                return "gone"
            end try
        end tell
    end tell'''
    return _osascript(script) in ("ok", "gone")


def desired_reminders():
    """Approved + unshipped posts with a scheduledSlot, from the plane."""
    status, data = gtm._request("GET", "/api/gtm/li-posts?gateState=1")
    if status != 200 or not data.get("success"):
        sys.exit(f"calendar_sync: plane read failed (HTTP {status}) — {data.get('error', '?')}")
    out = {}
    for p in data.get("posts", []):
        if (
            p.get("status") == "gated"
            and p.get("gateState") == "approved"
            and p.get("scheduledSlot")
        ):
            out[p["externalId"]] = {
                "slot": p["scheduledSlot"],
                "title": p.get("title") or p["externalId"],
            }
    return out


def report_receipt(external_id: str, current_status: str, uid: str):
    """Best-effort receipt to the plane — never a gate."""
    try:
        gtm._request(
            "POST",
            "/api/gtm/li-posts",
            {
                "externalId": external_id,
                "status": current_status,
                "calendarSyncedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "calendarEventRef": uid,
            },
        )
    except SystemExit:
        pass


def _mode() -> str:
    return _load(MARKER, {}).get("mode", "local")


def print_mcp_worklist() -> None:
    """MCP-mode 'sync': emit the reconcile plan for the session model to
    execute with its calendar tools (create/move/delete), then `record`."""
    desired = desired_reminders()
    events = _load(EVENT_MAP, {})
    plan = {
        "mode": "mcp",
        "create": [
            {"externalId": k, **v}
            for k, v in desired.items()
            if k not in events or events[k]["slot"] != v["slot"]
        ],
        "delete": [
            {"externalId": k, "eventRef": events[k]["uid"]} for k in events if k not in desired
        ],
        "note": (
            "Execute with the session's calendar MCP tools. After each create/move: "
            "`calendar_sync.py record <externalId> <slot> <eventRef>` (records + sends the "
            "plane receipt). After each delete: `calendar_sync.py forget <externalId>`."
        ),
    }
    print(json.dumps(plan, indent=2))


def sync() -> None:
    if not os.path.exists(MARKER):
        sys.exit("calendar_sync: not enabled on this seat — run `calendar_sync.py enable` first.")
    if _mode() == "mcp":
        print_mcp_worklist()
        return
    if sys.platform != "darwin":
        sys.exit(
            "calendar_sync: local Calendar.app fallback is macOS-only.\n"
            "  Re-enable in MCP mode (`enable --mode mcp`) and use the session's calendar tools."
        )
    desired = desired_reminders()
    events = _load(EVENT_MAP, {})
    created = moved = removed = 0

    # Remove reminders whose post left the approved+planned set.
    for ext_id in [k for k in events if k not in desired]:
        if delete_event(events[ext_id]["uid"]):
            del events[ext_id]
            removed += 1

    for ext_id, want in desired.items():
        have = events.get(ext_id)
        desc = f"Edit/publish from your JieGou cockpit, then tap Executed. Post: {ext_id}. Publishing is yours — nothing auto-posts."
        title = f"Publish LI post: {want['title'][:70]}"
        was_move = bool(have and have["slot"] != want["slot"])
        if was_move:
            delete_event(have["uid"])
            have = None
        if not have:
            uid = create_event(title, want["slot"], desc)
            events[ext_id] = {"uid": uid, "slot": want["slot"]}
            if was_move:
                moved += 1
            else:
                created += 1
            report_receipt(ext_id, "gated", uid)

    _save(EVENT_MAP, events)
    print(
        f"calendar_sync: {created} created, {moved} moved, {removed} removed "
        f"({len(events)} tracked) on calendar \"{_calendar_name()}\"."
    )


def enable(argv) -> None:
    mode = "mcp"
    if "--mode" in argv:
        mode = argv[argv.index("--mode") + 1]
    if mode not in ("mcp", "local"):
        sys.exit("calendar_sync: --mode must be 'mcp' (connected calendar) or 'local' (Calendar.app fallback)")
    cal = DEFAULT_CALENDAR
    if "--calendar" in argv:
        cal = argv[argv.index("--calendar") + 1]
    _save(
        MARKER,
        {"mode": mode, "calendar": cal, "enabledAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    where = "connected calendar via session MCP tools" if mode == "mcp" else f'Calendar.app "{cal}"'
    print(f"calendar_sync: enabled for seat {SEAT} (mode: {mode} — {where}). Running first sync…")
    sync()


def record(argv) -> None:
    """MCP mode: track an event the session created + send the plane receipt."""
    if len(argv) < 3:
        sys.exit("calendar_sync: usage — record <externalId> <slot YYYY-MM-DD> <eventRef>")
    ext_id, slot, ref = argv[0], argv[1], argv[2]
    events = _load(EVENT_MAP, {})
    events[ext_id] = {"uid": ref, "slot": slot}
    _save(EVENT_MAP, events)
    report_receipt(ext_id, "gated", ref)
    print(f"calendar_sync: recorded {ext_id} → {slot} ({ref[:24]}…); plane receipt sent.")


def forget(argv) -> None:
    """MCP mode: drop a tracked event after the session deleted it."""
    if not argv:
        sys.exit("calendar_sync: usage — forget <externalId>")
    events = _load(EVENT_MAP, {})
    if argv[0] in events:
        del events[argv[0]]
        _save(EVENT_MAP, events)
        print(f"calendar_sync: forgot {argv[0]}.")
    else:
        print(f"calendar_sync: {argv[0]} was not tracked.")


def disable() -> None:
    events = _load(EVENT_MAP, {})
    if _mode() == "local":
        for ext_id, ev in list(events.items()):
            delete_event(ev["uid"])
        note = f"{len(events)} reminder(s) removed"
    else:
        note = (
            f"{len(events)} tracked reminder(s) — delete them via the session's calendar tools"
            if events
            else "no tracked reminders"
        )
    for p in (EVENT_MAP, MARKER):
        if os.path.exists(p):
            os.remove(p)
    print(f"calendar_sync: disabled — {note}, marker cleared.")


def status() -> None:
    enabled = os.path.exists(MARKER)
    events = _load(EVENT_MAP, {})
    detail = f" (mode: {_mode()}" + (f", calendar \"{_calendar_name()}\")" if _mode() == "local" else ")")
    print(f"seat: {SEAT}\nenabled: {enabled}" + (detail if enabled else ""))
    for ext_id, ev in events.items():
        print(f"  {ext_id}: {ev['slot']} (uid {ev['uid'][:12]}…)")
    if not events:
        print("  no tracked reminders")


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__.strip())
    cmd = argv[0]
    if cmd == "enable":
        enable(argv[1:])
    elif cmd == "sync":
        sync()
    elif cmd == "desired":
        print(json.dumps(desired_reminders(), indent=2))
    elif cmd == "record":
        record(argv[1:])
    elif cmd == "forget":
        forget(argv[1:])
    elif cmd == "status":
        status()
    elif cmd == "disable":
        disable()
    else:
        sys.exit(f"calendar_sync: unknown command '{cmd}'\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
