#!/usr/bin/env python3
"""li_lint.py — voice-floor linter for tenant drafting seats (plugin edition).

Lints a post body (+ optional first comment) against the account's VOICE
PROFILE pulled by `gtm.py pull`. Deterministic — the floor under every draft;
the model provides the ceiling, this guards the floor.

  li_lint.py <textfile>                  # lint a plain-text post body
  li_lint.py <textfile> --first-comment <file>

HARD fails (exit 1): banned patterns, '--' instead of an em-dash, body over
the hard char cap. Warnings: over the norm length, em-dash density per
paragraph, poll/CTA phrasing, verb-only words, no hashtags.
Requires a pulled voice profile (run `gtm.py pull` first) — there is no
built-in fallback on tenant seats; the profile IS the voice.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import substrate  # noqa: E402


def load_profile():
    p = os.path.expanduser(f"~/.jiegou/gtm-grounding-{substrate._seat_name()}.json")
    if not os.path.exists(p):
        sys.exit("li_lint: no grounding cache — run `gtm.py pull` first.")
    with open(p) as f:
        data = json.load(f)
    prof = data.get("voiceProfile")
    if not prof:
        sys.exit(
            "li_lint: no voice profile for this account — ask your JieGou operator "
            "to run the voice-curation session."
        )
    return prof


def lint_body(body, label, prof, hard, warn):
    n = len(body)
    caps = prof.get("charCaps") or {}
    hard_cap = caps.get("hard", 3000)
    warn_over = caps.get("warnOver", 2200)
    if n > hard_cap:
        hard.append(f"{label}: {n} chars > {hard_cap} (hard cap)")
    elif n > warn_over:
        warn.append(f"{label}: {n} chars (longer than the norm)")
    for pat in prof.get("bannedPatterns", []):
        m = re.search(pat, body, re.I)
        if m:
            hard.append(f"{label}: banned '{m.group(0)}'")
    if "--" in body:
        hard.append(f"{label}: '--' found — use an em-dash (—)")
    cap = prof.get("emDashPerParagraphCap", 1)
    for i, para in enumerate(re.split(r"\n\s*\n", body)):
        if para.count("—") > cap:
            warn.append(f"{label}: paragraph {i+1} has {para.count('—')} em-dashes (cap {cap})")
    for pat in prof.get("verbOnlyWarnWords", []):
        if re.search(pat, body, re.I):
            warn.append(f"{label}: '{pat}' — banned as a verb")
    for pat in prof.get("pollCtaPatterns", []):
        if re.search(pat, body, re.I):
            warn.append(f"{label}: poll/CTA phrasing — off-register")
    if label == "post" and prof.get("warnIfNoHashtags") and not re.search(r"#\w", body):
        warn.append(f"{label}: no hashtags")
    return body.strip().replace("\n", " ")[: prof.get("hookChars", 210)]


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__.strip())
    prof = load_profile()
    hard, warn = [], []
    with open(argv[0]) as f:
        hook = lint_body(f.read(), "post", prof, hard, warn)
    if "--first-comment" in argv:
        fc = argv[argv.index("--first-comment") + 1]
        with open(fc) as f:
            lint_body(f.read(), "first-comment", prof, hard, warn)
    print(f"hook[:{prof.get('hookChars',210)}]: {hook!r}")
    for h in hard:
        print(f"  X HARD  {h}")
    for w in warn:
        print(f"  ! warn  {w}")
    if not hard and not warn:
        print("  v clean")
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
