#!/usr/bin/env python3
"""li_lint.py — voice-floor linter for tenant drafting seats (plugin edition).

Lints a post body (+ optional first comment) against the account's VOICE
PROFILE pulled by `gtm.py pull`. Deterministic — the floor under every draft;
the model provides the ceiling, this guards the floor.

  li_lint.py <textfile>                  # lint a plain-text post body
  li_lint.py <textfile> --first-comment <file>
  li_lint.py <textfile> --meta <meta.json>   # draft checks (0.14.0)

HARD fails (exit 1): banned patterns, '--' instead of an em-dash, body over
the hard char cap. Warnings: over the norm length, em-dash density per
paragraph, poll/CTA phrasing, verb-only words, no hashtags.
Draft checks (0.14.0): when the account's editorial guide sets `draftChecks`,
`--meta` is REQUIRED and checked as HARD fails. meta.json:
  {"hookVariants": ["...", "...", "..."], "onlyMe": "<the detail only the author could write>"}
- hookVariants: at least draftChecks.hookVariants entries, at least one first-person.
- onlyMe: non-empty. "ONLY-ME NEEDED: <suggested angle>" passes with a warning:
  it is the honest form when the seat cannot ground a detail from the author's own
  operation (never invent one), and the approver supplies it at the gate.
Accounts without draftChecks are unaffected.
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


def load_grounding():
    p = os.path.expanduser(f"~/.jiegou/gtm-grounding-{substrate._seat_name()}.json")
    if not os.path.exists(p):
        sys.exit("li_lint: no grounding cache — run `gtm.py pull` first.")
    with open(p) as f:
        return json.load(f)


def load_profile(data=None):
    data = data if data is not None else load_grounding()
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


FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|me|my|we|we're|we've|us|our)\b", re.I)


def check_draft_meta(checks, meta, hard, warn):
    """The guide's structured draft checks. `checks` falsy = nothing to enforce."""
    if not checks:
        return
    if meta is None:
        hard.append("draft checks: this account's guide requires --meta (hook variants + only-me)")
        return
    want = checks.get("hookVariants")
    if want:
        hv = [v for v in (meta.get("hookVariants") or []) if isinstance(v, str) and v.strip()]
        if len(hv) < want:
            hard.append(f"hook variants: {len(hv)} found, the guide requires {want}")
        if hv and not any(FIRST_PERSON.search(v) for v in hv):
            hard.append("hook variants: none is first-person (the guide requires at least one)")
    if checks.get("onlyMe"):
        om = (meta.get("onlyMe") or "").strip()
        if not om:
            hard.append("only-me: empty — name the detail only the author could write, or write 'ONLY-ME NEEDED: <angle>'")
        elif om.upper().startswith("ONLY-ME NEEDED"):
            warn.append("only-me: flagged ONLY-ME NEEDED — put it first in approverNotes so the approver supplies it")


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__.strip())
    data = load_grounding()
    prof = load_profile(data)
    hard, warn = [], []
    meta = None
    if "--meta" in argv:
        with open(argv[argv.index("--meta") + 1]) as f:
            meta = json.load(f)
    check_draft_meta(((data.get("editorialGuide") or {}).get("draftChecks")), meta, hard, warn)
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
