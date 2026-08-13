#!/usr/bin/env python3
"""
build-i18n.py — generate the localized copies of the SimplShot site.

The English HTML files are the single source of truth. You keep editing
index.html and compare.html exactly as before; this script re-renders the
translated copies from them.

    python3 build-i18n.py            # regenerate fr/ ja/ ru/ zh/
    python3 build-i18n.py --extract  # dump every translatable English string
    python3 build-i18n.py --check    # report missing/stale strings, write nothing

How it works
------------
Translations live in i18n/<locale>.json and are keyed by the *English source
string* — no data-i18n attributes are added to the markup. The script parses the
HTML, finds every block of translatable text (including inline markup such as
links, so word order can change freely), looks the English up, and substitutes
the translation. Everything it has no translation for is left in English and
reported, so adding a new paragraph to index.html simply shows up as a missing
string on the next run instead of silently breaking.

It also rewrites, per locale: <html lang>, the canonical URL, og:url/og:locale,
hreflang alternates, the JSON-LD graph (including FAQPage, so schema stays in
parity with the visible FAQ), the language picker's current-language marker,
and every relative asset/page link (generated pages live one directory down).
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
I18N_DIR = ROOT / "i18n"
SITE = "https://simplshot.com"

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

LOCALES = {
    "fr": {"name": "Français", "html_lang": "fr", "og_locale": "fr_FR", "hreflang": "fr"},
    "ja": {"name": "日本語", "html_lang": "ja", "og_locale": "ja_JP", "hreflang": "ja"},
    "ru": {"name": "Русский", "html_lang": "ru", "og_locale": "ru_RU", "hreflang": "ru"},
    "zh": {"name": "简体中文", "html_lang": "zh-Hans", "og_locale": "zh_CN", "hreflang": "zh-Hans"},
}

# source file -> (english path component, localized path component)
PAGES = {
    "index.html": {"en_path": "/", "loc_path": "/{loc}/", "out": "index.html"},
    "compare.html": {"en_path": "/compare", "loc_path": "/{loc}/compare", "out": "compare.html"},
}

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# Elements that may appear *inside* a single translatable block.
INLINE = {
    "a", "abbr", "b", "bdi", "bdo", "br", "cite", "code", "data", "del", "dfn",
    "em", "i", "img", "ins", "kbd", "mark", "picture", "q", "s", "samp",
    "small", "source", "span", "strong", "sub", "sup", "time", "u", "var",
    "wbr", "svg", "path", "circle", "rect", "line", "polyline", "polygon", "g",
}

SKIP_TAGS = {"script", "style", "svg", "noscript"}

# Attributes translated in place (on elements that are not inside a text block).
ATTR_KEYS = ("alt", "title", "aria-label", "placeholder")

# <meta> tags whose content is prose.
META_NAME_TRANSLATE = {
    "description", "twitter:title", "twitter:description", "twitter:image:alt",
}
META_PROP_TRANSLATE = {"og:title", "og:description", "og:image:alt"}


# --------------------------------------------------------------------------
# Minimal offset-preserving HTML tokenizer / tree
# --------------------------------------------------------------------------

class _Tokenizer(HTMLParser):
    """Collects tokens with absolute source offsets so we can do surgical edits."""

    def __init__(self, raw: str):
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self.line_starts = [0]
        for i, ch in enumerate(raw):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.tokens: list[tuple[int, str, object]] = []

    def _pos(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        self.tokens.append((self._pos(), "start", (tag, attrs)))

    def handle_startendtag(self, tag, attrs):
        self.tokens.append((self._pos(), "startend", (tag, attrs)))

    def handle_endtag(self, tag):
        self.tokens.append((self._pos(), "end", tag))

    def handle_data(self, data):
        self.tokens.append((self._pos(), "text", data))

    def handle_entityref(self, name):
        self.tokens.append((self._pos(), "text", f"&{name};"))

    def handle_charref(self, name):
        self.tokens.append((self._pos(), "text", f"&#{name};"))

    def handle_comment(self, data):
        self.tokens.append((self._pos(), "comment", data))

    def handle_decl(self, decl):
        self.tokens.append((self._pos(), "decl", decl))

    def unknown_decl(self, data):
        self.tokens.append((self._pos(), "decl", data))

    def handle_pi(self, data):
        self.tokens.append((self._pos(), "pi", data))


def parse(raw: str) -> dict:
    tk = _Tokenizer(raw)
    tk.feed(raw)
    tk.close()
    tokens = tk.tokens
    ends = [tokens[i + 1][0] for i in range(len(tokens) - 1)] + [len(raw)]

    root = {
        "tag": "#root", "attrs": [], "children": [], "parent": None,
        "tag_start": 0, "tag_end": len(raw),
        "content_start": 0, "content_end": len(raw),
    }
    stack = [root]

    for (start, kind, payload), end in zip(tokens, ends):
        parent = stack[-1]
        if kind in ("start", "startend"):
            tag, attrs = payload  # type: ignore[misc]
            node = {
                "tag": tag, "attrs": attrs, "children": [], "parent": parent,
                "tag_start": start, "content_start": end,
                "content_end": None, "tag_end": None,
            }
            parent["children"].append(node)
            if kind == "startend" or tag in VOID:
                node["content_end"] = end
                node["tag_end"] = end
            else:
                stack.append(node)
        elif kind == "end":
            tag = payload
            for i in range(len(stack) - 1, 0, -1):
                if stack[i]["tag"] == tag:
                    while len(stack) > i:
                        n = stack.pop()
                        n["content_end"] = start
                        n["tag_end"] = end
                    break
        else:
            parent["children"].append({
                "tag": "#" + kind, "attrs": [], "children": [], "parent": parent,
                "tag_start": start, "tag_end": end,
                "content_start": start, "content_end": end,
            })

    while len(stack) > 1:
        n = stack.pop()
        n["content_end"] = len(raw)
        n["tag_end"] = len(raw)
    return root


def is_element(node: dict) -> bool:
    return not node["tag"].startswith("#")


def is_text(node: dict) -> bool:
    return node["tag"] == "#text"


# --------------------------------------------------------------------------
# Translation-unit discovery
# --------------------------------------------------------------------------

WS_RE = re.compile(r"\s+")


def collapse(s: str) -> str:
    return WS_RE.sub(" ", s)


def node_text(raw: str, node: dict) -> str:
    """Visible text of a subtree, entities resolved."""
    if is_text(node):
        return html_mod.unescape(raw[node["tag_start"]:node["tag_end"]])
    if node["tag"].startswith("#"):
        return ""
    if node["tag"] in SKIP_TAGS:
        return ""
    return "".join(node_text(raw, c) for c in node["children"])


def subtree_all_inline(node: dict) -> bool:
    for child in node["children"]:
        if not is_element(child):
            continue
        if child["tag"] in SKIP_TAGS or child["tag"] not in INLINE:
            return False
        if not subtree_all_inline(child):
            return False
    return True


def has_direct_text(raw: str, node: dict) -> bool:
    return any(
        is_text(c) and raw[c["tag_start"]:c["tag_end"]].strip()
        for c in node["children"]
    )


def is_no_translate(node: dict) -> bool:
    """Honour the standard HTML `translate="no"` opt-out."""
    return dict(node.get("attrs") or []).get("translate", "").lower() == "no"


def find_units(raw: str, node: dict, out: list[dict]) -> None:
    for child in node["children"]:
        if not is_element(child) or child["tag"] in SKIP_TAGS or is_no_translate(child):
            continue
        if (
            subtree_all_inline(child)
            and node_text(raw, child).strip()
            and (has_direct_text(raw, child) or not any(is_element(c) for c in child["children"]))
        ):
            out.append(child)
        else:
            find_units(raw, child, out)


def unit_parts(raw: str, unit: dict) -> tuple[str, str, str, int, int]:
    """Split a unit into (prefix_html, key, suffix_html, content_start, content_end).

    Leading/trailing children that carry no text (decorative icons, <br/>) are
    peeled off so the translatable key stays clean.
    """
    kids = list(unit["children"])

    def carries_text(n: dict) -> bool:
        return bool(node_text(raw, n).strip())

    lo, hi = 0, len(kids)
    while lo < hi and not carries_text(kids[lo]):
        lo += 1
    while hi > lo and not carries_text(kids[hi - 1]):
        hi -= 1

    cs, ce = unit["content_start"], unit["content_end"]
    if lo >= hi:
        return "", "", "", cs, ce

    mid_start = kids[lo]["tag_start"]
    mid_end = kids[hi - 1]["tag_end"]
    prefix = collapse(raw[cs:mid_start])
    suffix = collapse(raw[mid_end:ce])
    key = collapse(raw[mid_start:mid_end]).strip()
    return prefix, key, suffix, cs, ce


# Strings that look like text but must never be translated.
SKIP_KEY_RE = re.compile(
    r"^(?:[\s\W\d]*|SimplShot|Atle Mo|GitHub|Liberapay|macOS|PDF|SVG|PNG|"
    r"CleanShot X|Shottr|Xnapper|Snagit|logo\.svg|dashboard-v2\.png|Auto|"
    r"\d+\s*[×x]\s*\d+|\$[\d.,]+|\d+\s*px|\d+%|[A-Z])$"
)


def is_skippable(key: str) -> bool:
    return not key or bool(SKIP_KEY_RE.match(key))


# --------------------------------------------------------------------------
# String collection
# --------------------------------------------------------------------------

def collect(raw: str) -> tuple[list[str], list[dict]]:
    """Return (ordered unique english strings, replacement descriptors)."""
    root = parse(raw)
    units: list[dict] = []
    find_units(raw, root, units)

    unit_nodes = set(id(u) for u in units)
    edits: list[dict] = []
    strings: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        if s not in seen and not is_skippable(s):
            seen.add(s)
            strings.append(s)

    for unit in units:
        prefix, key, suffix, cs, ce = unit_parts(raw, unit)
        if is_skippable(key):
            continue
        add(key)
        edits.append({
            "kind": "unit", "start": cs, "end": ce,
            "key": key, "prefix": prefix, "suffix": suffix,
        })

    # Attributes on elements that are not inside a translated block.
    def inside_unit(node: dict) -> bool:
        p = node["parent"]
        while p is not None:
            if id(p) in unit_nodes:
                return True
            p = p["parent"]
        return False

    def walk_attrs(node: dict) -> None:
        for child in node["children"]:
            if not is_element(child):
                continue
            if child["tag"] in SKIP_TAGS or is_no_translate(child):
                continue
            if not inside_unit(child):
                attrs = dict(child["attrs"])
                targets: list[tuple[str, str]] = []
                for a in ATTR_KEYS:
                    if attrs.get(a):
                        targets.append((a, attrs[a]))
                # Opt-in convention: any data-i18n-* attribute holds prose that
                # scripts read back out (e.g. live-region announcements).
                for a, v in attrs.items():
                    if a.startswith("data-i18n-") and v:
                        targets.append((a, v))
                if child["tag"] == "meta":
                    name = (attrs.get("name") or "").lower()
                    prop = (attrs.get("property") or "").lower()
                    if (name in META_NAME_TRANSLATE or prop in META_PROP_TRANSLATE) and attrs.get("content"):
                        targets.append(("content", attrs["content"]))
                for attr, value in targets:
                    value = collapse(value).strip()
                    if is_skippable(value):
                        continue
                    add(value)
                    edits.append({
                        "kind": "attr", "start": child["tag_start"], "end": child["tag_end"],
                        "attr": attr, "key": value,
                    })
            walk_attrs(child)

    walk_attrs(root)

    # JSON-LD prose
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        raw, re.S | re.I,
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"JSON-LD block is not valid JSON: {exc}")
        for s in _jsonld_strings(data):
            add(s)
        edits.append({"kind": "jsonld", "start": m.start(1), "end": m.end(1), "data": data})

    return strings, edits


JSONLD_TEXT_KEYS = {"name", "description", "text", "headline", "caption", "abstract"}


def _jsonld_strings(node, key=None, out=None):
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            _jsonld_strings(v, k, out)
    elif isinstance(node, list):
        for v in node:
            _jsonld_strings(v, key, out)
    elif isinstance(node, str):
        if key in JSONLD_TEXT_KEYS or key == "featureList":
            s = collapse(node).strip()
            if not is_skippable(s):
                out.append(s)
    return out


def _jsonld_translate(node, table, key=None):
    if isinstance(node, dict):
        return {k: _jsonld_translate(v, table, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_jsonld_translate(v, table, key) for v in node]
    if isinstance(node, str) and (key in JSONLD_TEXT_KEYS or key == "featureList"):
        return table.get(collapse(node).strip(), node)
    return node


# --------------------------------------------------------------------------
# Rendering a localized page
# --------------------------------------------------------------------------

LANG_PICKER_RE = re.compile(
    r"(<!--\s*LANG-PICKER\s*-->)(.*?)(<!--\s*/LANG-PICKER\s*-->)", re.S
)

# The picker's own label, in each language. Language *names* stay in their own
# language and are never translated.
LABELS = {
    "en": "Language",
    "fr": "Langue",
    "ja": "言語",
    "ru": "Язык",
    "zh": "语言",
}


def picker_html(current: str, page: str, indent: str = "      ") -> str:
    """Build the footer language picker for `current` locale on `page`."""
    cfg = PAGES[page]
    entries = [("en", "English", "en", cfg["en_path"])]
    for loc, meta in LOCALES.items():
        entries.append((loc, meta["name"], meta["hreflang"], cfg["loc_path"].format(loc=loc)))

    label = LABELS.get(current, LABELS["en"])
    lines = [
        f'{indent}<div class="lang-picker" translate="no">',
        f'{indent}  <span class="lang-picker-label" id="lang-picker-label">',
        f'{indent}    <i data-lucide="globe" class="lang-icon"></i>{label}',
        f'{indent}  </span>',
        f'{indent}  <ul class="lang-list" aria-labelledby="lang-picker-label">',
    ]
    for loc, label, hreflang, href in entries:
        current_attr = ' aria-current="true"' if loc == current else ""
        lines.append(
            f'{indent}    <li><a href="{href}" hreflang="{hreflang}" lang="{hreflang}" '
            f'data-lang="{loc}"{current_attr}>{label}</a></li>'
        )
    lines += [f"{indent}  </ul>", f"{indent}</div>"]
    return "\n".join(lines)


def alternates_html(page: str, indent: str = "  ") -> str:
    cfg = PAGES[page]
    rows = [
        f'{indent}<link rel="alternate" hreflang="en" href="{SITE}{cfg["en_path"]}" />'
    ]
    for loc, meta in LOCALES.items():
        rows.append(
            f'{indent}<link rel="alternate" hreflang="{meta["hreflang"]}" '
            f'href="{SITE}{cfg["loc_path"].format(loc=loc)}" />'
        )
    rows.append(f'{indent}<link rel="alternate" hreflang="x-default" href="{SITE}{cfg["en_path"]}" />')
    return "\n".join(rows)


ALTERNATES_RE = re.compile(r"(<!--\s*HREFLANG\s*-->)(.*?)(<!--\s*/HREFLANG\s*-->)", re.S)


def set_attr(tag_src: str, attr: str, value: str) -> str:
    """Replace attr's value inside a raw start-tag string."""
    pattern = re.compile(rf'(\b{re.escape(attr)}\s*=\s*)(".*?"|\'.*?\')', re.S)
    if not pattern.search(tag_src):
        return tag_src
    return pattern.sub(lambda m: m.group(1) + '"' + html_mod.escape(value, quote=True) + '"', tag_src, count=1)


LINK_ATTR_RE = re.compile(r'\b(href|src)\s*=\s*"([^"]*)"')


def rewrite_links(raw: str, loc: str) -> str:
    """Generated pages live in /<loc>/, so relative paths must be re-rooted."""
    def repl(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|/|#|data:|mailto:)", url, re.I):
            return m.group(0)
        if url in ("index.html", "./index.html", ""):
            new = f"/{loc}/"
        elif url in ("compare", "compare.html"):
            new = f"/{loc}/compare"
        elif url.startswith("#"):
            new = url
        else:
            new = "/" + url.lstrip("./")
        return f'{attr}="{new}"'

    return LINK_ATTR_RE.sub(repl, raw)


def render(page: str, raw: str, loc: str, table: dict[str, str], missing: set[str]) -> str:
    meta = LOCALES[loc]
    cfg = PAGES[page]
    loc_url = SITE + cfg["loc_path"].format(loc=loc)

    strings, edits = collect(raw)
    for s in strings:
        if s not in table or not table[s]:
            missing.add(s)

    # Apply text/attr/json-ld edits back-to-front so offsets stay valid.
    out = raw
    for edit in sorted(edits, key=lambda e: e["start"], reverse=True):
        if edit["kind"] == "unit":
            tr = table.get(edit["key"])
            if not tr:
                continue
            out = out[:edit["start"]] + edit["prefix"] + tr + edit["suffix"] + out[edit["end"]:]
        elif edit["kind"] == "attr":
            tr = table.get(edit["key"])
            if not tr:
                continue
            tag_src = out[edit["start"]:edit["end"]]
            out = out[:edit["start"]] + set_attr(tag_src, edit["attr"], tr) + out[edit["end"]:]
        elif edit["kind"] == "jsonld":
            data = _jsonld_translate(edit["data"], table)
            data = _localize_jsonld(data, page, loc, meta)
            body = "\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n  "
            out = out[:edit["start"]] + body + out[edit["end"]:]

    # <html lang="en">
    out = re.sub(r'(<html\b[^>]*\blang\s*=\s*)"[^"]*"', rf'\1"{meta["html_lang"]}"', out, count=1)

    # Canonical + og:url + og:locale
    out = re.sub(
        r'(<link\s+rel="canonical"\s+href=)"[^"]*"',
        rf'\1"{loc_url}"', out, count=1,
    )
    out = re.sub(
        r'(<meta\s+property="og:url"\s+content=)"[^"]*"',
        rf'\1"{loc_url}"', out, count=1,
    )
    if 'property="og:locale"' in out:
        out = re.sub(
            r'(<meta\s+property="og:locale"\s+content=)"[^"]*"',
            rf'\1"{meta["og_locale"]}"', out, count=1,
        )
    else:
        out = re.sub(
            r'(<meta\s+property="og:url"[^>]*/>)',
            rf'\1\n  <meta property="og:locale" content="{meta["og_locale"]}" />',
            out, count=1,
        )

    # Language picker + hreflang block
    out = LANG_PICKER_RE.sub(
        lambda m: m.group(1) + "\n" + picker_html(loc, page) + "\n      " + m.group(3),
        out, count=1,
    )
    out = ALTERNATES_RE.sub(
        lambda m: m.group(1) + "\n" + alternates_html(page) + "\n  " + m.group(3),
        out, count=1,
    )

    # The auto-detect bootstrap must know which locale it is running on.
    out = out.replace("var SS_PAGE_LANG = 'en';", f"var SS_PAGE_LANG = '{loc}';")

    out = rewrite_links(out, loc)

    banner = (
        f"<!-- Generated by build-i18n.py from {page} — do not edit by hand.\n"
        f"     Edit the English source and run: python3 build-i18n.py -->\n"
    )
    return out.replace("<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + banner, 1)


# Entities that describe the project as a whole rather than one page. Their
# @id and url are shared across every language and must not be re-pointed.
GLOBAL_ANCHORS = {"#organization", "#creator", "#website", "#software", "#video"}


def _localize_jsonld(data, page: str, loc: str, meta: dict):
    """Point page-scoped @ids/urls at the localized page and set inLanguage."""
    cfg = PAGES[page]
    en_url = SITE + cfg["en_path"]
    loc_url = SITE + cfg["loc_path"].format(loc=loc)
    en_root = SITE + "/"
    loc_root = f"{SITE}/{loc}/"

    def localize_id(value: str) -> str | None:
        """Return the localized @id, or None if the entity is site-global."""
        if not isinstance(value, str) or "#" not in value:
            return None
        base, anchor = value.split("#", 1)
        if "#" + anchor in GLOBAL_ANCHORS:
            return None
        if base.rstrip("/") != en_url.rstrip("/"):
            return None
        return f"{loc_url}#{anchor}"

    def fix(node):
        if isinstance(node, list):
            return [fix(v) for v in node]
        if not isinstance(node, dict):
            return node

        out = {k: fix(v) for k, v in node.items()}

        # Breadcrumbs point at real pages, so they follow the language.
        if out.get("@type") == "ListItem" and isinstance(out.get("item"), str):
            if out["item"] == en_root:
                out["item"] = loc_root
            elif out["item"].rstrip("/") == en_url.rstrip("/"):
                out["item"] = loc_url

        new_id = localize_id(out.get("@id", ""))
        if new_id is None:
            return out

        # This entity belongs to *this* page: re-point it at the localized URL.
        out["@id"] = new_id
        if isinstance(out.get("url"), str) and out["url"].rstrip("/") == en_url.rstrip("/"):
            out["url"] = loc_url
        if "inLanguage" in out:
            out["inLanguage"] = meta["hreflang"]
        elif out.get("@type") == "WebPage":
            out["inLanguage"] = meta["hreflang"]
        for ref_key in ("isPartOf", "about", "publisher"):
            ref = out.get(ref_key)
            if isinstance(ref, dict) and isinstance(ref.get("@id"), str):
                localized_ref = localize_id(ref["@id"])
                if localized_ref:
                    out[ref_key] = {"@id": localized_ref}
        return out

    return fix(data)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_table(loc: str) -> dict[str, str]:
    path = I18N_DIR / f"{loc}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", action="store_true", help="print every translatable English string and exit")
    ap.add_argument("--check", action="store_true", help="report coverage without writing files")
    args = ap.parse_args()

    sources = {p: (ROOT / p).read_text(encoding="utf-8") for p in PAGES}

    if args.extract:
        payload = {}
        for page, raw in sources.items():
            strings, _ = collect(raw)
            payload[page] = strings
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    all_english: dict[str, list[str]] = {}
    for page, raw in sources.items():
        for s in collect(raw)[0]:
            all_english.setdefault(s, []).append(page)

    failed = False
    for loc in LOCALES:
        table = load_table(loc)
        missing: set[str] = set()
        outputs: dict[Path, str] = {}
        for page, raw in sources.items():
            html_out = render(page, raw, loc, table, missing)
            outputs[ROOT / loc / PAGES[page]["out"]] = html_out

        stale = [k for k in table if k not in all_english]
        done = len(all_english) - len(missing)
        status = f"{loc}: {done}/{len(all_english)} strings"

        if missing:
            failed = True
            status += f" — {len(missing)} MISSING"
        if stale:
            status += f" — {len(stale)} unused"
        print(status)

        for s in sorted(missing):
            print(f"    missing [{loc}]: {s[:110]}")
        for s in sorted(stale):
            print(f"    unused  [{loc}]: {s[:110]}")

        if not args.check:
            for path, content in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            print(f"    wrote {', '.join(str(p.relative_to(ROOT)) for p in outputs)}")

    if args.check and failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
