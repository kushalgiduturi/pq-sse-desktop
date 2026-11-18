"""Checks of the built website (site/public). Exit code 1 on any failure.

    python scripts/check_site.py [--no-browser]

Static checks (Python): well-formed HTML (every non-void element closed in order), lang and title,
one h1 and no skipped heading level, unique ids, every for / aria-labelledby / aria-controls /
aria-describedby target present, every internal link and #anchor resolving, and the contrast
table: every text token on every fill (glass and dense, composited over the world) at 4.5:1 or
more in both themes, white on the accent and on the solid danger colour at 4.5:1.

Browser checks (Qt WebEngine, a Chromium engine): every page in both themes, with JavaScript on
and off. Every request is recorded and a request to another host fails the run. With JavaScript
off the download links must be present and the theme follows the system. In the rendered page
every visible text node is measured against its real background (computed colours, composited up
the tree over the world) at 4.5:1 (3:1 for large text), and every link, button and form field
must have an accessible name.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "site" / "public"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SVG_SELF = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "stop", "use"}


# ------------------------------------------------------------------ static checks
class Page(HTMLParser):
    def __init__(self, name: str) -> None:
        super().__init__(convert_charrefs=True)
        self.name, self.stack, self.problems = name, [], []
        self.ids, self.refs, self.links, self.headings = set(), [], [], []
        self.lang = self.title = False
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = True
        if tag == "title":
            self.title = True
        if "id" in a:
            if a["id"] in self.ids:
                self.problems.append(f"duplicate id {a['id']}")
            self.ids.add(a["id"])
        for attr in ("for", "aria-labelledby", "aria-controls", "aria-describedby"):
            for target in (a.get(attr) or "").split():
                self.refs.append((attr, target))
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
            self.h1 += tag == "h1"
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"</{tag}> does not close the open <{self.stack[-1] if self.stack else 'nothing'}>")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()


def static_checks() -> list[str]:
    problems = []
    pages = {p.name: p for p in sorted(PUBLIC.glob("*.html"))}
    parsed = {}
    for name, path in pages.items():
        page = Page(name)
        page.feed(path.read_text(encoding="utf-8"))
        page.close()
        parsed[name] = page
        problems += [f"{name}: {p}" for p in page.problems]
        if page.stack:
            problems.append(f"{name}: elements left open: {page.stack}")
        if not page.lang or not page.title:
            problems.append(f"{name}: no lang or no title")
        if page.h1 != 1:
            problems.append(f"{name}: {page.h1} h1 elements (one expected)")
        for prev, cur in zip(page.headings, page.headings[1:]):
            if cur > prev + 1:
                problems.append(f"{name}: heading level jumps from h{prev} to h{cur}")
        for attr, target in page.refs:
            if target not in page.ids:
                problems.append(f"{name}: {attr} points at missing id {target}")
    for name, page in parsed.items():
        if name == "404.html":
            continue                          # its links are absolute to the site root
        for href in page.links:
            url = urlparse(href)
            if url.scheme in ("http", "https", "mailto"):
                continue
            target, _, anchor = href.partition("#")
            target = target or name
            if not (PUBLIC / target).is_file():
                problems.append(f"{name}: link to missing file {href}")
            elif anchor and target.endswith(".html") and anchor not in parsed.get(target, Page(target)).ids:
                problems.append(f"{name}: link to missing anchor {href}")
    return problems


# ------------------------------------------------------------------ contrast table
def _parse_color(value: str) -> tuple:
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(r"rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\s*\)", value)
    if m:
        r, g, b, a = m.groups()
        return (float(r) / 255, float(g) / 255, float(b) / 255, float(a) if a else 1.0)
    raise ValueError(value)


def _block(css: str, selector: str) -> dict:
    start = css.index(selector + " {")
    body = css[start:css.index("\n}", start)]
    return dict(re.findall(r"(--sp-[\w-]+):\s*([^;]+);", body))


def _over(top, under):
    a = top[3]
    return tuple(t * a + u * (1 - a) for t, u in zip(top[:3], under[:3])) + (1.0,)


def _lum(c) -> float:
    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def contrast_table() -> tuple[list[str], list[str]]:
    css = (PUBLIC / "assets" / "site.css").read_text(encoding="utf-8")
    dark = _block(css, "html.sp-ui")
    light = {**dark, **_block(css, 'html.sp-ui[data-theme="light"]')}
    lines, failures = [], []
    for theme, tokens in (("dark", dark), ("light", light)):
        color = {}
        for key, value in tokens.items():
            try:
                color[key] = _parse_color(value)
            except ValueError:
                pass
        worlds = [color["--sp-world"], color["--sp-world-edge"]]
        grounds = {"world": worlds[0], "world edge": worlds[1]}
        for depth in (1, 2, 3, 4):
            for kind in ("fill", "solid"):
                for i, w in enumerate(worlds):
                    under = _over(color["--sp-fill-2"], w) if depth == 1 else w   # insets sit on the panel
                    grounds[f"{kind}-{depth} on world {i}"] = _over(color[f"--sp-{kind}-{depth}"], under)
        texts = ("--sp-text", "--sp-text-2", "--sp-text-3", "--sp-accent-text", "--sp-ok", "--sp-warn", "--sp-bad", "--sp-info")
        for name in texts:
            for ground, bg in grounds.items():
                fg = _over(color[name], bg) if color[name][3] < 1 else color[name]
                value = ratio(fg, bg)
                line = f"{theme:5} {name:16} on {ground:20} {value:5.2f}:1"
                lines.append(line)
                if value < 4.5:
                    failures.append(line + " (needs 4.5)")
        for fg, bg in (("--sp-on-accent", "--sp-accent"), ("--sp-on-accent", "--sp-bad-solid")):
            value = ratio(color[fg], color[bg])
            line = f"{theme:5} {fg} on {bg} {value:5.2f}:1"
            lines.append(line)
            if value < 4.5:
                failures.append(line + " (needs 4.5)")
    return lines, failures


# ------------------------------------------------------------------ browser checks
AUDIT_JS = r"""
(function () {
  function parse(c) { var m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; var p = m[1].split(',').map(parseFloat);
    return [p[0] / 255, p[1] / 255, p[2] / 255, p.length > 3 ? p[3] : 1]; }
  function over(t, u) { var a = t[3]; return [t[0] * a + u[0] * (1 - a), t[1] * a + u[1] * (1 - a), t[2] * a + u[2] * (1 - a), 1]; }
  function lum(c) { function l(v) { return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); } return .2126 * l(c[0]) + .7152 * l(c[1]) + .0722 * l(c[2]); }
  function ratio(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); }
  var world = parse(getComputedStyle(document.documentElement).backgroundColor) || [0, 0, 0, 1];
  function background(el) {
    var layers = [];
    for (var e = el; e && e.nodeType === 1; e = e.parentElement) {
      var c = parse(getComputedStyle(e).backgroundColor);
      if (c && c[3] > 0) layers.push(c);
    }
    var bg = world;
    for (var i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg);
    return bg;
  }
  var problems = [], checked = 0;
  var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    var node = walker.currentNode, el = node.parentElement;
    if (!node.textContent.trim() || !el) continue;
    var cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || !el.getClientRects().length) continue;
    if (el.closest('.sp-world, [aria-hidden="true"], .sp-toast, .sp-skip, svg')) continue;
    if (el.closest(':disabled, [aria-disabled="true"]')) continue;   // WCAG 1.4.3: inactive controls are exempt
    var fg = parse(cs.color); if (!fg) continue;
    var bg = background(el);
    if (fg[3] < 1) fg = over(fg, bg);
    var size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 600;
    var need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    var r = ratio(fg, bg); checked++;
    if (r < need) problems.push('contrast ' + r.toFixed(2) + ':1 (needs ' + need + ') "' + node.textContent.trim().slice(0, 40) + '"');
  }
  document.querySelectorAll('a[href], button, input, select, textarea').forEach(function (el) {
    if (!el.getClientRects().length || el.closest('[hidden]')) return;
    var name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') || '').trim();
    if (el.matches('input, select, textarea')) {
      var id = el.id; name = (id && document.querySelector('label[for="' + id + '"]')) ? 'label' : (el.getAttribute('aria-label') || '');
    }
    if (!name) problems.push('no accessible name: <' + el.tagName.toLowerCase() + ' class="' + el.className + '">');
  });
  // theme twins: of each light/dark picture pair exactly one is shown, the one for the current theme
  var dark = document.documentElement.getAttribute('data-theme') === 'dark' ||
             (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  document.querySelectorAll('figure').forEach(function (fig) {
    var light = fig.querySelector('img.sp-on-light'), darkImg = fig.querySelector('img.sp-on-dark');
    if (!light || !darkImg) return;
    var shown = [light, darkImg].filter(function (i) { return getComputedStyle(i).display !== 'none'; });
    if (shown.length !== 1 || shown[0] !== (dark ? darkImg : light))
      problems.push('theme picture pair shows ' + shown.map(function (i) { return i.className; }).join(' and ') + ' in the ' + (dark ? 'dark' : 'light') + ' theme');
  });
  return JSON.stringify({ problems: problems, checked: checked,
    exes: document.querySelectorAll('a[href$=".exe"]').length,
    themeButtonHidden: !!(document.querySelector('[data-theme-toggle]') || {}).hidden });
})()
"""


def browser_checks() -> tuple[list[str], list[str]]:
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(PUBLIC)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    origin = f"127.0.0.1:{httpd.server_address[1]}"
    foreign: list[str] = []

    class Watch(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            if url.scheme() not in ("data", "blob") and url.authority() != origin:
                foreign.append(url.toString())
                info.block(True)

    watch = Watch()
    profile = QWebEngineProfile("site-check")
    profile.setUrlRequestInterceptor(watch)
    view = QWebEngineView()
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    view.resize(1280, 900)
    view.show()

    def run_js(code: str, world: int = 0):
        out = {}
        loop = QEventLoop()
        page.runJavaScript(code, world, lambda v: (out.setdefault("v", v), loop.quit()))
        QTimer.singleShot(8000, loop.quit)
        loop.exec()
        return out.get("v")

    def load(url: str) -> None:
        loop = QEventLoop()
        page.loadFinished.connect(loop.quit)
        page.load(QUrl(url))
        QTimer.singleShot(15000, loop.quit)
        loop.exec()
        page.loadFinished.disconnect(loop.quit)

    problems, notes = [], []
    names = [p.name for p in sorted(PUBLIC.glob("*.html"))]
    for js_on in (True, False):
        page.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, js_on)
        for name in names:
            for theme in ("dark", "light"):
                load(f"http://{origin}/{name}")
                if js_on:
                    run_js(f"document.documentElement.setAttribute('data-theme','{theme}')")
                    loop = QEventLoop()
                    QTimer.singleShot(600, loop.quit)   # past the longest colour transition (350 ms)
                    loop.exec()
                    page.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                    raw = run_js(AUDIT_JS)
                else:
                    # JavaScript off for the page; the audit runs in Qt's isolated application world
                    raw = run_js(AUDIT_JS, world=1)
                result = json.loads(raw) if raw else {"problems": ["the audit did not run"], "checked": 0}
                tag = f"{name} {theme} js={'on' if js_on else 'off'}"
                problems += [f"{tag}: {p}" for p in result["problems"]]
                if name == "download.html" and result.get("exes", 0) < 1:
                    problems.append(f"{tag}: no download link")
                if not js_on and not result.get("themeButtonHidden", True):
                    problems.append(f"{tag}: the theme button shows without JavaScript")
                notes.append(f"{tag}: {result.get('checked', 0)} text nodes measured")
                if not js_on:
                    break                    # without JavaScript the theme cannot be switched: one pass (system setting)
    httpd.shutdown()
    problems += [f"request to another host: {u}" for u in sorted(set(foreign))]
    return problems, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not PUBLIC.is_dir():
        print("FAILED: site/public does not exist; run scripts/build_site.py first")
        return 1
    problems = static_checks()
    lines, failures = contrast_table()
    problems += failures
    print(f"static: {len(list(PUBLIC.glob('*.html')))} pages; contrast table: {len(lines)} pairs, {len(failures)} below the minimum")
    if not args.no_browser:
        browser, notes = browser_checks()
        problems += browser
        print(f"browser: {len(notes)} page loads")
        if args.verbose:
            print("\n".join(notes))
    for p in problems:
        print("FAIL " + p)
    print(f"site check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
