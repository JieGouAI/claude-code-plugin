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
  3. (0.10.1) Headless permission bootstrap: writes <seat>/.claude/settings.json
     (Bash allowlist for the plugin scripts + WebFetch/WebSearch + ~/.jiegou) if
     absent, and marks the seat workspace trusted in ~/.claude.json — without
     both, every headless run auto-denies the first substrate.py call and no
     work executes. Existing settings.json is never modified.

  setup_pull.py install [--interval 30]   # minutes between checks (default 30)
  setup_pull.py install --wake            # 0.11.0: SSE-wake daemon instead of polling —
                                          # a launchd KeepAlive process holds the per-seat
                                          # wake stream (substrate.py wake) and pulls within
                                          # ~2s of dispatch; 10-min internal heartbeat floor
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
    "You are running UNATTENDED (scheduled headless pull). Run /jiegou:pull. For "
    "each assigned COMMAND or queue item, execute it by following the matching "
    "/jiegou skills (draft-post for hook dispatches, reply-draft for "
    "reply-sweep-draft commands), then close it with /jiegou:report. Do "
    "nothing beyond the assigned work. "
    "HEADLESS SAFETY (2026-08-08): you may do the mechanical and REVERSIBLE parts "
    "of a job, but NEVER make a human-judgment call unattended and NEVER do an "
    "irreversible one. Concretely: do NOT choose which content hooks to queue, do "
    "NOT approve/execute a cockpit item, do NOT commit to main or publish "
    "anywhere. For research/content skills (reddit-research, competitive-intel-"
    "weekly, draft-post): prepare the reversible artifacts (fetch, synthesise, "
    "write the draft/brief, register the plane receipt, update matrix/state, file "
    "review-gated requests), then LEAVE the judgment gate for a human by pushing a "
    "cockpit review-handoff item and reporting the command complete with the "
    "prepared artifact paths. If any step truly needs interactive input or "
    "permissions you cannot satisfy this way, stop and leave the work unreported "
    "for a human session. "
    "SCOPE (2026-08-16): act ONLY on work this pull listed for THIS seat. Do not "
    "run a job because it looks due, and do not act on a command id you learned "
    "anywhere other than this pull's output. If closing a command returns 403 "
    "'Command belongs to another agent', that is the plane refusing another seat's "
    "work — stop, report nothing, and do not record it as a platform bug."
)


# Repetition budget (0.13.1): how many headless sessions may be spent on the
# SAME unchanged pulled work before the wrapper holds off, and how long it holds.
MAX_SAME_WORK_SESSIONS = 3
SAME_WORK_COOLDOWN_S = 6 * 3600


def write_wrapper(claude_path: str) -> None:
    max_attempts = MAX_SAME_WORK_SESSIONS
    cooldown_s = SAME_WORK_COOLDOWN_S
    cooldown_h = SAME_WORK_COOLDOWN_S // 3600
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(os.path.expanduser("~/.jiegou/locks"), exist_ok=True)
    log = os.path.join(LOG_DIR, f"pull-{SEAT}.log")
    lock = os.path.expanduser(f"~/.jiegou/locks/pull-{SEAT}.pid")
    state = os.path.expanduser(f"~/.jiegou/locks/pull-{SEAT}.attempts")
    script = f"""#!/bin/bash
# jiegou unattended pull — seat "{SEAT}" (installed by /jiegou:setup-pull; remove with `setup_pull.py uninstall`)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export JIEGOU_AGENT_NAME="{SEAT}"
cd "{WORKDIR}" || exit 0
# Concurrency guard (0.10.1): a draft session can outlast the pull interval — without
# this, the next tick launches a SECOND session racing the same commands (observed
# 2026-08-13). PID lockfile; a dead PID (crash) never wedges the seat.
LOCK="{lock}"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) skip: prior work session still running (pid $(cat "$LOCK"))" >> "{log}"
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
CHECK=$(SUBSTRATE_TIMEOUT=15 python3 "{HERE}/substrate.py" pull --if-enrolled 2>/dev/null)
echo "$(date -u +%FT%TZ) check: $(echo "$CHECK" | grep -c 'COMMAND\\|ITEM') item(s)" >> "{log}"
if echo "$CHECK" | grep -q "COMMAND\\|ITEM"; then
  # Repetition budget (0.13.1): the PID lock above stops CONCURRENT sessions but
  # nothing stopped SEQUENTIAL ones — a work item that cannot be closed from this
  # seat reappears on every tick, and each tick spent a full headless session
  # reaching the same conclusion (observed 2026-08-15: ~12 sessions in 35 minutes
  # on one command, zero state change). Fingerprint the pulled ids; after
  # {max_attempts} sessions leave the SAME work unchanged, hold for {cooldown_h}h or until the
  # work actually changes. The seat stays live for genuinely new work throughout.
  FP=$(echo "$CHECK" | grep -oE '(COMMAND|ITEM)[[:space:]]+[A-Za-z0-9_-]+' \\
       | awk '{{print $2}}' | sort | tr '\\n' ',')
  STATE="{state}"
  NOW=$(date +%s)
  PREV_FP=""; PREV_N=0; PREV_T=0
  if [ -f "$STATE" ]; then IFS=$'\\t' read -r PREV_FP PREV_N PREV_T < "$STATE" || true; fi
  if [ "$FP" = "$PREV_FP" ]; then
    N=$((PREV_N + 1)); T=$PREV_T
    if [ "$N" -gt {max_attempts} ] && [ $((NOW - PREV_T)) -lt {cooldown_s} ]; then
      printf '%s\\t%s\\t%s\\n' "$FP" "$N" "$T" > "$STATE"
      echo "$(date -u +%FT%TZ) budget: same work after {max_attempts} sessions, no change — holding (attempt $N, next in $(( ({cooldown_s} - (NOW - PREV_T)) / 60 ))m). fp=$FP" >> "{log}"
      exit 0
    fi
    if [ "$N" -gt {max_attempts} ]; then N=1; T=$NOW; fi
  else
    N=1; T=$NOW
  fi
  printf '%s\\t%s\\t%s\\n' "$FP" "$N" "$T" > "$STATE"
  echo "$(date -u +%FT%TZ) work found — launching headless session (attempt $N)" >> "{log}"
  "{claude_path}" -p {HEADLESS_PROMPT!r} >> "{log}" 2>&1
else
  rm -f "{state}"
fi
"""
    fd = os.open(WRAPPER, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o755)
    try:
        os.write(fd, script.encode())
    finally:
        os.close(fd)


# Headless permission bootstrap (0.10.1). Observed 2026-08-13: a seat with no
# .claude/settings.json has NO Bash allowlist, so every plugin-script call in a
# `claude -p` run is auto-denied ("This command requires approval") — and even
# with settings present, an untrusted workspace IGNORES them. Both must hold or
# every scheduled run walls at the first substrate.py call.
SEAT_SETTINGS = {
    "permissions": {
        "allow": [
            # Command-level prefixes on purpose: sessions quote script paths
            # (python3 "/Users/…/substrate.py"), which defeats path-prefix rules.
            "Bash(python3:*)",
            "Bash(python3.14:*)",
            "Bash(SUBSTRATE_TIMEOUT=15 python3:*)",
            "WebFetch",
            "WebSearch",
        ],
        "additionalDirectories": ["~/.jiegou"],
    }
}


def bootstrap_headless_permissions() -> None:
    import json

    settings_dir = os.path.join(WORKDIR, ".claude")
    settings_path = os.path.join(settings_dir, "settings.json")
    if os.path.exists(settings_path):
        print(f"setup_pull: {settings_path} already exists — left untouched; verify it "
              f"allowlists the plugin scripts (e.g. \"Bash(python3:*)\") or headless runs will block.")
    else:
        os.makedirs(settings_dir, exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(SEAT_SETTINGS, f, indent=2)
            f.write("\n")
        print(f"setup_pull: wrote headless permission allowlist → {settings_path}")

    # Trust: untrusted workspaces silently ignore settings.json permissions.
    claude_json = os.path.expanduser("~/.claude.json")
    try:
        with open(claude_json) as f:
            cfg = json.load(f)
        proj = cfg.setdefault("projects", {}).setdefault(WORKDIR, {})
        if not proj.get("hasTrustDialogAccepted"):
            proj["hasTrustDialogAccepted"] = True
            with open(claude_json, "w") as f:
                json.dump(cfg, f, indent=2)
            print(f"setup_pull: marked workspace trusted in ~/.claude.json (settings.json is honored in headless runs)")
    except (OSError, ValueError) as e:
        print(f"setup_pull: WARNING — could not set workspace trust in ~/.claude.json ({e}); "
              f"run claude interactively here once and accept the trust dialog, or headless runs will ignore the allowlist.")


def install(interval_min: int, wake: bool = False) -> None:
    claude_path = shutil.which("claude")
    if not claude_path:
        sys.exit("setup_pull: `claude` CLI not found on PATH — install Claude Code first.")
    if substrate.load_session() is None:
        sys.exit("setup_pull: this seat isn't enrolled — run /jiegou:enroll first.")
    bootstrap_headless_permissions()
    write_wrapper(claude_path)
    if wake and sys.platform != "darwin":
        sys.exit("setup_pull: --wake needs launchd KeepAlive (macOS); use interval polling on Linux for now.")
    if sys.platform == "darwin":
        os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
        log = os.path.join(LOG_DIR, f"pull-{SEAT}.log")
        if wake:
            # SSE-wake daemon (0.11.0): launchd supervises a persistent
            # `substrate.py wake` process holding the per-seat doorbell stream;
            # it runs the SAME wrapper (check → lockfile → headless draft) on
            # connect, on every wake frame, and on a 10-min heartbeat floor.
            plist = {
                "Label": PLIST_LABEL,
                "ProgramArguments": [
                    sys.executable or "python3",
                    os.path.join(HERE, "substrate.py"),
                    "wake",
                    "--on-wake",
                    f"/bin/bash {WRAPPER}",
                ],
                "EnvironmentVariables": {"JIEGOU_AGENT_NAME": SEAT},
                "KeepAlive": True,
                "RunAtLoad": True,
                "StandardOutPath": log,
                "StandardErrorPath": log,
            }
        else:
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
        mode = "SSE-wake daemon (KeepAlive)" if wake else f"every {interval_min} min"
        print(f"setup_pull: installed launchd agent {PLIST_LABEL} ({mode}).")
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
        install(interval, wake="--wake" in argv)
    elif argv[0] == "status":
        status()
    elif argv[0] == "uninstall":
        uninstall()
    else:
        sys.exit(f"setup_pull: unknown command '{argv[0]}'\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
