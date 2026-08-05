#!/usr/bin/env python3
"""setup_pull.py — install/inspect/remove the OPTIONAL unattended pull for this seat.

Explicitly user-invoked (via /jiegou:setup-pull) — the plugin never installs
persistence on its own. What gets installed, transparently:

  1. A wrapper at ~/.jiegou/bin/jiegou-pull-<seat>.sh that:
     • runs a FREE check (`substrate.py pull --if-enrolled`, plain python);
     • ONLY IF work is assigned, launches one headless Claude session
       (`claude -p …`) to execute it and report. No work → no session → no
       subscription usage.
  2. A per-user schedule: macOS → launchd agent ~/Library/LaunchAgents/
     ai.jiegou.pull.<seat>.plist; Linux → a marked crontab line.

  setup_pull.py install [--interval 30]   # minutes between checks (default 30)
  setup_pull.py status
  setup_pull.py uninstall

Approvals and publishing remain human actions regardless — unattended runs
only execute plane-assigned work and stop at the same gates.
Logs: ~/.jiegou/logs/pull-<seat>.log
"""
import os
import plistlib
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import substrate  # noqa: E402

SEAT = substrate._seat_name()
WORKDIR = os.getcwd()
BIN_DIR = os.path.expanduser("~/.jiegou/bin")
LOG_DIR = os.path.expanduser("~/.jiegou/logs")
WRAPPER = os.path.join(BIN_DIR, f"jiegou-pull-{SEAT}.sh")
PLIST_LABEL = f"ai.jiegou.pull.{SEAT}"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_LABEL}.plist")
CRON_MARK = f"# jiegou-pull:{SEAT}"

HEADLESS_PROMPT = (
    "Run /jiegou:pull. For each assigned COMMAND or queue item, execute it by "
    "following the matching /jiegou skills (e.g. draft-post), then close it with "
    "/jiegou:report. Do nothing beyond the assigned work. If a step needs "
    "interactive input or permissions, stop and leave the work unreported for a "
    "human session. Never publish anything anywhere."
)


def write_wrapper(claude_path: str) -> None:
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    log = os.path.join(LOG_DIR, f"pull-{SEAT}.log")
    script = f"""#!/bin/bash
# jiegou unattended pull — seat "{SEAT}" (installed by /jiegou:setup-pull; remove with `setup_pull.py uninstall`)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export JIEGOU_AGENT_NAME="{SEAT}"
cd "{WORKDIR}" || exit 0
CHECK=$(SUBSTRATE_TIMEOUT=15 python3 "{HERE}/substrate.py" pull --if-enrolled 2>/dev/null)
echo "$(date -u +%FT%TZ) check: $(echo "$CHECK" | grep -c 'COMMAND\\|ITEM') item(s)" >> "{log}"
if echo "$CHECK" | grep -q "COMMAND\\|ITEM"; then
  echo "$(date -u +%FT%TZ) work found — launching headless session" >> "{log}"
  "{claude_path}" -p {HEADLESS_PROMPT!r} >> "{log}" 2>&1
fi
"""
    fd = os.open(WRAPPER, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o755)
    try:
        os.write(fd, script.encode())
    finally:
        os.close(fd)


def install(interval_min: int) -> None:
    claude_path = shutil.which("claude")
    if not claude_path:
        sys.exit("setup_pull: `claude` CLI not found on PATH — install Claude Code first.")
    if substrate.load_session() is None:
        sys.exit("setup_pull: this seat isn't enrolled — run /jiegou:enroll first.")
    write_wrapper(claude_path)
    if sys.platform == "darwin":
        os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
        plist = {
            "Label": PLIST_LABEL,
            "ProgramArguments": ["/bin/bash", WRAPPER],
            "StartInterval": interval_min * 60,
            "RunAtLoad": True,
        }
        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
        subprocess.run(["launchctl", "load", PLIST_PATH], check=True, capture_output=True)
        print(f"setup_pull: installed launchd agent {PLIST_LABEL} (every {interval_min} min).")
    else:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [l for l in (r.stdout.splitlines() if r.returncode == 0 else []) if CRON_MARK not in l]
        lines.append(f"*/{interval_min} * * * * /bin/bash {WRAPPER} {CRON_MARK}")
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
        print(f"setup_pull: installed crontab entry (every {interval_min} min).")
    print(f"  wrapper: {WRAPPER}\n  log:     {LOG_DIR}/pull-{SEAT}.log\n  remove:  setup_pull.py uninstall")


def status() -> None:
    print(f"seat: {SEAT}\nwrapper: {WRAPPER} {'(present)' if os.path.exists(WRAPPER) else '(absent)'}")
    if sys.platform == "darwin":
        r = subprocess.run(["launchctl", "list", PLIST_LABEL], capture_output=True, text=True)
        print(f"launchd: {'LOADED' if r.returncode == 0 else 'not loaded'} ({PLIST_PATH})")
    else:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        hit = [l for l in r.stdout.splitlines() if CRON_MARK in l] if r.returncode == 0 else []
        print(f"cron: {hit[0] if hit else 'not installed'}")
    log = os.path.join(LOG_DIR, f"pull-{SEAT}.log")
    if os.path.exists(log):
        with open(log) as f:
            tail = f.readlines()[-3:]
        print("recent log:")
        for l in tail:
            print("  " + l.rstrip())


def uninstall() -> None:
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
        if os.path.exists(PLIST_PATH):
            os.remove(PLIST_PATH)
        print(f"setup_pull: launchd agent removed ({PLIST_LABEL}).")
    else:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if r.returncode == 0:
            lines = [l for l in r.stdout.splitlines() if CRON_MARK not in l]
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
        print("setup_pull: crontab entry removed.")
    if os.path.exists(WRAPPER):
        os.remove(WRAPPER)
        print("setup_pull: wrapper removed.")


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__.strip())
    if argv[0] == "install":
        interval = 30
        if "--interval" in argv:
            interval = max(5, int(argv[argv.index("--interval") + 1]))
        install(interval)
    elif argv[0] == "status":
        status()
    elif argv[0] == "uninstall":
        uninstall()
    else:
        sys.exit(f"setup_pull: unknown command '{argv[0]}'\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
