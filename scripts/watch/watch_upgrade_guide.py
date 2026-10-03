#!/usr/bin/env python3
"""Diff the Gradle upgrade guide against the gradle10-ready rule table.

Reads the "Deprecations" sections of https://docs.gradle.org/current/userguide/upgrading_version_9.html
(the headings that announce an API or behaviour that a later major version removes) and reports every
deprecation anchor that is neither cited by a rule in `rules.py` nor listed in `scripts/watch/triaged.txt`.
It also reports whether a Gradle 10 release or an `upgrading_version_10` page exists yet.

Standard library only. Exit codes: 0 nothing new, 3 new deprecations or Gradle 10 signals found, 2 usage/network error.
Heading titles are a proxy: the guide does not tag items "removed in 10" in a machine-readable way.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

GUIDE_URL = "https://docs.gradle.org/current/userguide/upgrading_version_9.html"
GUIDE10_URL = "https://docs.gradle.org/current/userguide/upgrading_version_10.html"
VERSIONS_URL = "https://services.gradle.org/versions/all"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TRIAGED = os.path.join(HERE, "triaged.txt")
LABEL = "gradle-watch"

_DEPRECATIONS_ID = re.compile(r"^(v9_)?deprecations(_\d+|_9_\d+)?$")
_SECTION_ID = re.compile(r"^changes_(\d+(\.\d+)*)$")


class _Headings(HTMLParser):
    """Collect (level, id, text) for h2..h4 elements that carry an id."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: List[Tuple[int, str, str]] = []
        self._cur: Optional[List] = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "h4"):
            self._cur = [int(tag[1]), dict(attrs).get("id") or "", []]

    def handle_data(self, data):
        if self._cur is not None:
            self._cur[2].append(data)

    def handle_endtag(self, tag):
        if self._cur is not None and tag in ("h2", "h3", "h4"):
            level, hid, parts = self._cur
            self._cur = None
            text = re.sub(r"[\u200b\s]+", " ", "".join(parts)).strip()
            if hid:
                self.headings.append((level, hid, text))


def parse_deprecations(html: str) -> List[Dict[str, str]]:
    """Return one dict (anchor, title, release) per item under a 'Deprecations' heading."""
    p = _Headings()
    p.feed(html)
    out: List[Dict[str, str]] = []
    release = ""
    in_dep = False
    for level, hid, text in p.headings:
        m = _SECTION_ID.match(hid)
        if level == 2:
            release = m.group(1) if m else hid
            in_dep = False
        elif level == 3:
            in_dep = bool(_DEPRECATIONS_ID.match(hid))
        elif level == 4 and in_dep:
            out.append({"anchor": hid, "title": text, "release": release})
    return out


def rule_anchors() -> Set[str]:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from gradle10_ready.rules import RULES  # noqa: WPS433

    return {r.url.split("#", 1)[1] for r in RULES.values() if "#" in r.url and r.url.startswith(GUIDE_URL)}


def stale_anchors(html: str, covered: Set[str]) -> List[str]:
    """Rule anchors (upgrade guide 9) that no longer exist as an id in the page."""
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    return sorted(a for a in covered if a not in ids)


def load_triaged(path: str = TRIAGED) -> Set[str]:
    anchors: Set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    anchors.add(line.split()[0])
    return anchors


def new_items(items: List[Dict[str, str]], covered: Set[str], triaged: Set[str]) -> List[Dict[str, str]]:
    return [i for i in items if i["anchor"] not in covered and i["anchor"] not in triaged]


def key_for(items: List[Dict[str, str]]) -> str:
    return hashlib.sha1(",".join(sorted(i["anchor"] for i in items)).encode()).hexdigest()[:8]


def fetch(url: str, timeout: int = 30) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "gradle10-ready-watch"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URLs)
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def gradle10_signals(guide10_status: int, versions_json: str) -> List[str]:
    sig = []
    if guide10_status == 200:
        sig.append(f"{GUIDE10_URL} now exists (HTTP 200).")
    try:
        found = sorted({v["version"] for v in json.loads(versions_json) if str(v.get("version", "")).startswith("10.")})
    except (ValueError, TypeError):
        found = []
    if found:
        sig.append("services.gradle.org lists Gradle 10 builds: " + ", ".join(found[:8]) + (" ..." if len(found) > 8 else ""))
    return sig


def render_issue(items: List[Dict[str, str]], signals: List[str], covered: int, total: int) -> Tuple[str, str]:
    key = key_for(items) if items else "signals-" + hashlib.sha1("|".join(signals).encode()).hexdigest()[:8]
    if items:
        title = f"Gradle upgrade guide: {len(items)} new deprecation(s) without a rule [{key}]"
    else:
        title = f"Gradle upgrade guide: Gradle 10 or stale-anchor signals [{key}]"
    lines = ["Opened by the scheduled `Gradle deprecation watch` workflow.", ""]
    if signals:
        lines += ["### Signals", ""] + [f"- {s}" for s in signals] + [""]
    if items:
        lines += [
            f"### New deprecations ({len(items)})", "",
            f"The guide lists {total} deprecation items; {covered} are cited by a rule or already triaged.", "",
            "| Release | Item | Anchor |", "|---|---|---|",
        ]
        for i in items:
            lines.append(f"| {i['release']} | {i['title']} | [`{i['anchor']}`]({GUIDE_URL}#{i['anchor']}) |")
        lines += [
            "", "### What to do", "",
            "1. Decide per item: add a rule in `src/gradle10_ready/rules.py` (cite the anchor), or",
            "2. add the anchor to `scripts/watch/triaged.txt` with a reason (`anchor  # why no rule`).",
            "Close this issue once both lists cover every row.", "",
            "Heading titles are a proxy for \"will be removed in the next major\"; read the section before deciding.",
        ]
    lines.append(f"\n<!-- gradle10-ready:watch:{key} -->")
    return title, "\n".join(lines)


def run(html: str, guide10_status: int, versions_json: str, triaged_path: str = TRIAGED) -> Dict:
    items = parse_deprecations(html)
    covered = rule_anchors()
    triaged = load_triaged(triaged_path)
    new = new_items(items, covered, triaged)
    signals = gradle10_signals(guide10_status, versions_json)
    stale = stale_anchors(html, covered)
    signals += [f"Rule table cites anchor `#{a}`, which no longer exists in the guide." for a in stale]
    title, body = render_issue(new, signals, len(items) - len(new), len(items)) if (new or signals) else ("", "")
    return {"total": len(items), "covered_by_rules": len([i for i in items if i["anchor"] in covered]),
            "triaged": len([i for i in items if i["anchor"] in triaged and i["anchor"] not in covered]),
            "new": new, "stale": stale, "signals": signals, "title": title, "body": body}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--html", help="read the guide from this file instead of fetching it")
    ap.add_argument("--offline", action="store_true", help="skip the Gradle 10 page and versions lookups")
    ap.add_argument("--triaged", default=TRIAGED)
    ap.add_argument("--out", help="write the result JSON (including issue title/body) to this file")
    ap.add_argument("--print-baseline", action="store_true", help="print triaged.txt lines for every uncovered item")
    a = ap.parse_args(argv)
    try:
        if a.html:
            html = open(a.html, encoding="utf-8").read()
        else:
            status, html = fetch(GUIDE_URL)
            if status != 200 or not html:
                print(f"error: {GUIDE_URL} returned HTTP {status}", file=sys.stderr)
                return 2
        s10, vers = (404, "[]") if a.offline else (fetch(GUIDE10_URL)[0], fetch(VERSIONS_URL)[1] or "[]")
    except (OSError, urllib.error.URLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = run(html, s10, vers, a.triaged)
    if res["total"] == 0:
        print("error: found no deprecation items; the guide layout may have changed", file=sys.stderr)
        return 2
    if a.print_baseline:
        for i in res["new"]:
            print(f"{i['anchor']}  # baseline: {i['release']} {i['title']}")
        return 0
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2)
    print(f"deprecation items: {res['total']}; cited by a rule: {res['covered_by_rules']}; triaged: {res['triaged']}; new: {len(res['new'])}")
    for i in res["new"]:
        print(f"  NEW {i['release']}: {i['title']}  (#{i['anchor']})")
    for s in res["signals"]:
        print("  SIGNAL", s)
    return 3 if (res["new"] or res["signals"]) else 0


if __name__ == "__main__":
    sys.exit(main())
