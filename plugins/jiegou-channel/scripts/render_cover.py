#!/usr/bin/env python3.14
"""render_cover.py — render an operator-grade LinkedIn cover PNG from a li-post artifact.

Two archetypes (auto-selected by the post's Category):
  • hook      — the hook's first sentence as a big typographic card. Default for A/B/F.
  • artifact  — the post's framework (grouped FUND/CUT or a numbered list) rendered as a
                clean save-bait card. Default for Category C (lists/frameworks).

Engine: headless Chromium (Playwright python). Brand tokens are the REAL JieGou palette
from console/marketing/src/styles/global.css; the type is the real brand font (Figtree),
inlined as base64 so it renders regardless of working directory. Code-rendered by
construction → cannot drift into the banned marketing-grade visuals (stock photos,
glowing AI brains, hero gradients). The content is the asset; the card makes it legible.

Usage:
  render_cover.py <post.md> [--archetype auto|hook|artifact] [--theme light|dark]
                  [--size 1200x627|1200x1200] [--full-hook] [-o out.png] [--html]
"""
import argparse
import base64
import html as _html
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Font lookup works in BOTH layouts: the plugin (scripts/ + assets/ siblings)
# and the Customer Zero repo (.claude/scripts/li -> repo root). Absent font is
# not fatal — font_face() returns "" and FONT_STACK falls back to system sans.
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[2]  # .claude/scripts/li -> repo root (repo layout)
LOGO_COLOR = ROOT / "console/marketing/public/logo.svg"
LOGO_WHITE = ROOT / "console/marketing/public/logo-white.svg"
_FONT_CANDIDATES = [
    _HERE.parent / "assets" / "figtree-latin.woff2",          # plugin layout
    ROOT / "console/marketing/public/fonts/figtree-latin.woff2",  # repo layout
]
FONT_SANS = next((p for p in _FONT_CANDIDATES if p.exists()), _FONT_CANDIDATES[0])

# --- real JieGou brand tokens (console/marketing/src/styles/global.css) ---
BRAND = {
    "ink": "#0f172a",        # brand-900
    "ink_soft": "#475569",   # brand-600
    "muted": "#64748b",      # brand-500
    "bg_light": "#f8fafc",   # brand-50
    "panel": "#f1f5f9",      # brand-100
    "primary": "#137dc5",    # primary-500
    "primary_dk": "#0b5a90", # primary-700
    "accent": "#62b3a0",     # accent-400
    "accent_dk": "#0f6baa",  # primary-600 (group label)
    "bg_dark": "#020617",    # brand-950
}

SIZES = {"1200x627": (1200, 627), "1200x1200": (1200, 1200)}

CATEGORY_LABEL = {
    "A": "FIELD REPORT", "B": "CONCEPT", "C": "FRAMEWORK", "D": "ESSAY",
    "E": "REACTION", "F": "TACTICAL", "G": "BUILD LOG", "V": "VIDEO", "—": "",
}

MAX_ITEMS_PER_GROUP = 5  # cap to keep the card legible; overflow is logged, never silent


def font_face() -> str:
    """Inline the real brand sans (Figtree) as a base64 @font-face so it always renders."""
    if not FONT_SANS.exists():
        return ""
    b64 = base64.b64encode(FONT_SANS.read_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'Figtree';font-style:normal;font-weight:400 800;"
        f"font-display:block;src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
    )


FONT_STACK = "'Figtree','Helvetica Neue',system-ui,-apple-system,Arial,sans-serif"


# ---------- artifact extraction ----------

def extract_hook(md: str) -> str:
    m = re.search(r"##\s*Full post.*?\n```[\w-]*\n(.*?)\n```", md, re.S | re.I)
    block = m.group(1) if m else md
    for line in block.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def extract_full_post(md: str) -> str:
    m = re.search(r"##\s*Full post.*?\n```[\w-]*\n(.*?)\n```", md, re.S | re.I)
    return m.group(1) if m else ""


def extract_category(md: str) -> str:
    m = re.search(r"^\*\*Category:\*\*\s*([A-GV])", md, re.M)
    return m.group(1) if m else "—"


def extract_title(md: str) -> str:
    m = re.search(r'^#\s+LI Post\s+\S+\s*[—-]\s*"?(.+?)"?\s*$', md, re.M)
    return m.group(1).strip() if m else ""


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut + "…"


def item_title(s: str) -> str:
    """Lead phrase of a framework item — up to the first sentence terminator, clipped.
    If a trailing parenthetical would force truncation, drop it for the clean label."""
    s = re.sub(r"\s+", " ", s).strip()
    first = re.split(r"(?<=[.?!])\s", s, maxsplit=1)[0].strip().rstrip(".")
    if len(first) > 58 and " (" in first:
        lead = first.split(" (", 1)[0].strip()
        if 12 <= len(lead) <= 58:
            first = lead
    return _clip(first, 58)


BULLET_RE = re.compile(r"^[·•‣◦▪►▸\*]\s+(.*)$")
NUM_RE = re.compile(r"^(\d+)\.\s+(.*)$")
HDR_RE = re.compile(r"^([A-Z][A-Z0-9 &/\-]{1,20})\s*[\(:]")


def parse_framework(body: str):
    """Return ([{label, items, ordered}], overflow). Grouped (ALL-CAPS headers like
    FUND:/CUT:) → columns; else one unlabeled list. Items may be numbered (rendered
    1,2,3…) or bulleted (rendered as ✓ ticks). Prose intro/close is ignored."""
    groups = []
    flat = {"label": None, "items": [], "ordered": None}
    current = None
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        m_num, m_bul = NUM_RE.match(s), BULLET_RE.match(s)
        if m_num or m_bul:
            text = m_num.group(2) if m_num else m_bul.group(1)
            bucket = current if current is not None else flat
            if bucket["ordered"] is None:
                bucket["ordered"] = bool(m_num)
            bucket["items"].append(item_title(text))
            continue
        m_hdr = HDR_RE.match(s)
        if m_hdr:
            current = {"label": m_hdr.group(1).strip(), "items": [], "ordered": None}
            groups.append(current)
    chosen = [g for g in groups if g["items"]] or ([flat] if flat["items"] else [])
    # single-column lists have room for more; multi-column stay dense-capped
    cap = 8 if len(chosen) == 1 else MAX_ITEMS_PER_GROUP
    overflow = 0
    for g in chosen:
        if len(g["items"]) > cap:
            overflow += len(g["items"]) - cap
            g["items"] = g["items"][:cap]
    return chosen, overflow


# ---------- font sizing ----------

def hook_font_size(text: str) -> int:
    n = len(text)
    for lim, fs in ((60, 76), (95, 64), (130, 54), (170, 46)):
        if n <= lim:
            return fs
    return 40


# ---------- HTML builders ----------

def _shell(inner: str, theme: str, w: int, h: int, logo_svg: str, pad: int) -> str:
    dark = theme == "dark"
    bg = BRAND["bg_dark"] if dark else BRAND["bg_light"]
    sub = "#94a3b8" if dark else BRAND["muted"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  {font_face()}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body{{width:{w}px;height:{h}px;}}
  .card{{width:{w}px;height:{h}px;background:{bg};padding:{pad}px {pad+8}px;
    position:relative;overflow:hidden;display:flex;flex-direction:column;
    justify-content:space-between;font-family:{FONT_STACK};}}
  .card::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:12px;background:{BRAND['primary']};}}
  .foot{{display:flex;align-items:flex-end;justify-content:space-between;}}
  .logo{{height:42px;}} .logo svg{{height:42px;width:auto;}}
  .rule{{height:6px;width:104px;background:{BRAND['accent']};border-radius:3px;}}
  .dom{{font-size:22px;font-weight:600;color:{sub};}}
</style></head><body><div class="card">
  {inner}
  <div class="foot"><div class="logo">{logo_svg}</div><div class="dom">jiegou.ai</div></div>
</div></body></html>"""


def build_hook(text: str, cat: str, theme: str, w: int, h: int, logo_svg: str) -> str:
    dark = theme == "dark"
    ink = "#ffffff" if dark else BRAND["ink"]
    fs = hook_font_size(text)
    chip = CATEGORY_LABEL.get(cat, "")
    chip_html = (f'<span style="font-size:20px;font-weight:700;letter-spacing:.14em;'
                 f'color:#fff;background:{BRAND["primary"]};padding:9px 18px;border-radius:7px;">'
                 f'{_html.escape(chip)}</span>') if chip else ""
    inner = f"""
  <div>{chip_html}</div>
  <div><div class="rule" style="margin-bottom:14px;"></div>
    <div style="font-size:{fs}px;font-weight:800;line-height:1.12;letter-spacing:-0.02em;
      color:{ink};max-width:94%;">{_html.escape(text)}</div></div>"""
    return _shell(inner, theme, w, h, logo_svg, pad=88 if w >= h else 80)


def build_artifact(title: str, groups, cat: str, theme: str, w: int, h: int, logo_svg: str) -> str:
    dark = theme == "dark"
    ink = "#ffffff" if dark else BRAND["ink"]
    item_col = "#e2e8f0" if dark else BRAND["ink"]
    glabel_bg = [BRAND["accent_dk"], BRAND["muted"]]  # group 0 / group 1+
    chip = CATEGORY_LABEL.get(cat, "")
    chip_html = (f'<span style="font-size:18px;font-weight:700;letter-spacing:.14em;'
                 f'color:#fff;background:{BRAND["primary"]};padding:7px 15px;border-radius:6px;">'
                 f'{_html.escape(chip)}</span>') if chip else ""

    single = len(groups) == 1
    n_items = max((len(g["items"]) for g in groups), default=0)
    if single:
        item_fs = 30 if n_items <= 6 else 26
    else:
        item_fs = 27 if n_items <= 4 else 24
    head_fs = 46 if len(title) <= 52 else 38

    cols = []
    for i, g in enumerate(groups):
        lbl = ""
        if g["label"]:
            bg = glabel_bg[min(i, 1)]
            lbl = (f'<div style="font-size:19px;font-weight:800;letter-spacing:.12em;color:#fff;'
                   f'background:{bg};padding:7px 15px;border-radius:6px;align-self:flex-start;'
                   f'margin-bottom:20px;">{_html.escape(g["label"])}</div>')
        rows = ""
        for j, it in enumerate(g["items"]):
            if g["label"]:
                bullet = "▸"
            else:
                bullet = (str(j + 1) if g["ordered"] else "✓")
            rows += (f'<div style="display:flex;gap:14px;margin-bottom:15px;font-size:{item_fs}px;'
                     f'font-weight:600;line-height:1.25;color:{item_col};">'
                     f'<span style="color:{BRAND["accent"]};font-weight:800;flex:none;">{bullet}</span>'
                     f'<span>{_html.escape(it)}</span></div>')
        cols.append(f'<div style="flex:1;display:flex;flex-direction:column;">{lbl}{rows}</div>')

    cols_html = (f'<div style="display:flex;gap:52px;flex:1;align-content:flex-start;">'
                 f'{"".join(cols)}</div>')
    inner = f"""
  <div style="display:flex;align-items:center;justify-content:space-between;">
    {chip_html}<div class="rule"></div></div>
  <div style="font-size:{head_fs}px;font-weight:800;line-height:1.1;letter-spacing:-0.02em;
    color:{ink};margin:22px 0 26px;max-width:96%;">{_html.escape(title)}</div>
  {cols_html}"""
    return _shell(inner, theme, w, h, logo_svg, pad=64)


# ---------- orchestration ----------

def card_line(hook: str, full: bool) -> str:
    if full or not hook:
        return hook
    parts = re.split(r"(?<=[.!?])\s+", hook)
    first = parts[0].strip()
    if len(first) < 28 and len(parts) > 1:
        first = (first + " " + parts[1]).strip()
    return first


def fmt_rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def render(post_path: Path, archetype: str, theme: str, size: str, full_hook: bool,
           out: Path, keep_html: bool, title_override: str = "", text_override: str = ""):
    md = post_path.read_text(encoding="utf-8")
    cat = extract_category(md)
    if archetype == "auto":
        archetype = "artifact" if cat == "C" else "hook"

    w, h = SIZES[size]
    logo_path = LOGO_WHITE if theme == "dark" else LOGO_COLOR
    logo_svg = re.sub(r"<\?xml.*?\?>", "", logo_path.read_text(encoding="utf-8"), flags=re.S).strip() if logo_path.exists() else ""

    if archetype == "artifact":
        body = extract_full_post(md)
        title = title_override or extract_title(md) or card_line(extract_hook(md), False)
        groups, overflow = parse_framework(body)
        if not groups:
            print("  (no parseable framework — falling back to hook archetype)")
            archetype = "hook"
        else:
            doc = build_artifact(title, groups, cat, theme, w, h, logo_svg)
            note = f" · {sum(len(g['items']) for g in groups)} items / {len(groups)} group(s)"
            if overflow:
                note += f" · ⚠ {overflow} item(s) over the {MAX_ITEMS_PER_GROUP}/group cap not shown"

    if archetype == "hook":
        hook = extract_hook(md)
        if not hook and not text_override:
            sys.exit(f"render_cover: no hook found in {post_path}")
        text = text_override or card_line(hook, full_hook)
        doc = build_hook(text, cat, theme, w, h, logo_svg)
        note = f" · {len(text)} chars"

    if keep_html:
        out.with_suffix(".html").write_text(doc, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        page.set_content(doc, wait_until="load")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()

    print(f"  {archetype} · category {cat} · {theme} · {size}{note} → {fmt_rel(out)}")


def main():
    ap = argparse.ArgumentParser(description="Render a branded LinkedIn cover PNG from a li-post artifact.")
    ap.add_argument("post")
    ap.add_argument("--archetype", choices=["auto", "hook", "artifact"], default="auto")
    ap.add_argument("--theme", choices=["light", "dark"], default="light")
    ap.add_argument("--size", choices=list(SIZES), default="1200x627")
    ap.add_argument("--full-hook", action="store_true", help="hook archetype: use the whole hook line (default: first sentence)")
    ap.add_argument("--title", default="", help="artifact archetype: override the card heading (when the H1 isn't a clean framework name)")
    ap.add_argument("--text", default="", help="hook archetype: override the card text (when the auto first-sentence drops the payoff)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--html", action="store_true", help="also write the .html source next to the PNG")
    a = ap.parse_args()

    post = Path(a.post)
    if not post.exists():
        sys.exit(f"render_cover: post not found: {post}")
    out = Path(a.out) if a.out else post.with_name(post.stem + "-cover.png")
    print(f"=== render_cover: {post.name} ===")
    render(post, a.archetype, a.theme, a.size, a.full_hook, out, a.html, a.title, a.text)


if __name__ == "__main__":
    main()
