"""The Quiet glass craft floor for the website (site/src and the built site/public).

    python scripts/craft_check_site.py

Fails (exit code 1) on: colours written outside the token blocks; blur above 24 px; more than
three blurred layers on a page; eyebrow styling (upper case, letter spacing on labels); gradient
text, glow halos or coloured shadows; emoji; exclamation marks or long dashes in any text;
external URLs in src or link attributes, @import or url() (the site loads nothing from other
hosts); inline style attributes and inline scripts (blocked by the page's Content-Security-Policy);
images without width, height and alt; pages heavier than 300 KB without screenshots.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site" / "src"
PUBLIC = ROOT / "site" / "public"
EM_DASH = chr(0x2014)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\u2B50\uFE0F]")
# a raw colour; rgba(var(--token-rgb), alpha) is a tint of a token and allowed
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\((?!\s*var\()|hsla?\(")
LIMIT_KB = 300


def css_findings(path: Path) -> list[str]:
    found = []
    text = path.read_text(encoding="utf-8")
    depth, in_tokens = 0, False
    for number, line in enumerate(text.splitlines(), 1):
        code = re.sub(r"/\*.*?\*/", "", line)
        stripped = code.strip()
        # colours are allowed only as custom property values (tokens) and in the token file
        if COLOR.search(code) and path.name != "tokens-light.css" and not re.match(r"\s*--[\w-]+\s*:", code) \
                and not stripped.startswith("--"):
            found.append(f"{path.name}:{number}: colour outside a token")
        for blur in re.findall(r"blur\((\d+(?:\.\d+)?)px\)", code):
            if float(blur) > 24:
                found.append(f"{path.name}:{number}: blur {blur}px is above 24px")
        for blur in re.findall(r"--sp-blur-\d:\s*(\d+)px", code):
            if float(blur) > 24:
                found.append(f"{path.name}:{number}: blur token {blur}px is above 24px")
        if re.search(r"text-transform:\s*uppercase|letter-spacing:\s*\.(?:0[5-9]|[1-9])", code):
            found.append(f"{path.name}:{number}: eyebrow styling (upper case or wide letter spacing)")
        if re.search(r"background-clip:\s*text|-webkit-text-fill-color", code):
            found.append(f"{path.name}:{number}: gradient text")
        if re.search(r"box-shadow:[^;]*0 0 \d+px[^;]*rgba\((?!0, 0, 0|15, 23, 42)", code):
            found.append(f"{path.name}:{number}: glow or coloured shadow")
        if re.search(r"@import|url\(\s*['\"]?https?:", code):
            found.append(f"{path.name}:{number}: external stylesheet or url()")
    return found


class PageCheck(HTMLParser):
    def __init__(self, name: str) -> None:
        super().__init__(convert_charrefs=True)
        self.name, self.found, self.glass, self.text = name, [], 0, []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "style" in a:
            self.found.append(f"{self.name}: inline style attribute on <{tag}>")
        classes = (a.get("class") or "").split()
        if "sp-glass" in classes and "sp-d4" not in classes:
            self.glass += 1
        for attr in ("src", "href"):
            value = a.get(attr) or ""
            if tag in ("script", "img", "link", "source", "iframe") and re.match(r"https?:|//", value):
                self.found.append(f"{self.name}: <{tag} {attr}> loads from another host: {value}")
        if tag == "script":
            if not a.get("src"):
                self.found.append(f"{self.name}: inline script")
            self.in_script = True
        if tag == "img" and not (a.get("width") and a.get("height") and a.get("alt") is not None):
            self.found.append(f"{self.name}: <img> without width, height or alt")
        for attr in ("alt", "title", "aria-label", "placeholder", "content", "data-windows", "data-other"):
            if a.get(attr):
                self.text.append(a[attr])

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if not self.in_script:
            self.text.append(data)


def page_findings(path: Path) -> list[str]:
    check = PageCheck(path.name)
    check.feed(path.read_text(encoding="utf-8"))
    found = list(check.found)
    if check.glass > 3:
        found.append(f"{path.name}: {check.glass} blurred glass layers (at most 3)")
    text = " ".join(check.text)
    if "!" in re.sub(r"<!--.*?-->", "", text):
        found.append(f"{path.name}: exclamation mark in the text")
    if EMOJI.search(text):
        found.append(f"{path.name}: emoji")
    weight = path.stat().st_size + sum(p.stat().st_size for p in (PUBLIC / "assets").glob("*.*")
                                       if p.suffix in (".css",) or p.name in ("site.js", "theme.js"))
    weight += sum(p.stat().st_size for p in (PUBLIC / "fonts").glob("*.woff2"))
    if weight > LIMIT_KB * 1024:
        found.append(f"{path.name}: {weight / 1024:.0f} KB without screenshots (limit {LIMIT_KB} KB)")
    return found


def check() -> list[str]:
    found = []
    for path in sorted((SRC / "assets").glob("*.css")):
        found += css_findings(path)
    for path in sorted(SRC.rglob("*")) + [ROOT / "site" / "content.toml"]:
        if path.is_file() and path.suffix in (".html", ".css", ".js", ".svg", ".toml"):
            text = path.read_text(encoding="utf-8")
            if EM_DASH in text:
                found.append(f"{path.relative_to(ROOT)}: long dash")
            if EMOJI.search(text):
                found.append(f"{path.relative_to(ROOT)}: emoji")
    content = (ROOT / "site" / "content.toml").read_text(encoding="utf-8")
    for number, line in enumerate(content.splitlines(), 1):
        if not line.lstrip().startswith("#") and "!" in line:
            found.append(f"content.toml:{number}: exclamation mark")
    if PUBLIC.is_dir():
        for path in sorted(PUBLIC.glob("*.html")):
            found += page_findings(path)
    return found


def main() -> int:
    found = check()
    for line in found:
        print(line)
    print(f"site craft check: {len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
