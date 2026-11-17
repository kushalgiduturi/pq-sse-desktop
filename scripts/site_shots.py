"""Screenshots of the website in both themes at 390, 768 and 1440 px, with Qt WebEngine.

    python scripts/site_shots.py [--pages index styleguide] [--out docs/design/site]

Serves site/public on 127.0.0.1, opens each page in a real Chromium engine (Qt WebEngine),
sets the theme the way the toggle does, scrolls through the full page and saves PNGs. Every
request the page makes is recorded; a request to any other host is reported and fails the run.
"""
from __future__ import annotations

import argparse
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "site" / "public"
WIDTHS = (390, 768, 1440)


PREFIX = "/pq-sse-desktop"  # the site's path on GitHub Pages; the 404 page links to it absolutely


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def translate_path(self, path):
        if path.startswith(PREFIX + "/"):
            path = path[len(PREFIX):]
        return super().translate_path(path)


def serve(folder: Path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(folder)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", nargs="*", default=["index", "styleguide"])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "design" / "site")
    parser.add_argument("--themes", nargs="*", default=["dark", "light"])
    parser.add_argument("--widths", nargs="*", type=int, default=list(WIDTHS))
    parser.add_argument("--viewport-only", action="store_true", help="first screen only, not the full page")
    args = parser.parse_args()

    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    httpd = serve(PUBLIC)
    origin = f"127.0.0.1:{httpd.server_address[1]}"
    foreign: list[str] = []

    class Watch(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            if url.scheme() not in ("data", "blob") and url.authority() != origin:
                foreign.append(url.toString())
                info.block(True)

    watch = Watch()
    profile = QWebEngineProfile("site-shots")
    profile.setUrlRequestInterceptor(watch)
    from PySide6.QtWebEngineCore import QWebEnginePage

    view = QWebEngineView()
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    view.show()

    def wait(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def js(code: str):
        result = {}
        loop = QEventLoop()
        page.runJavaScript(code, 0, lambda value: (result.setdefault("v", value), loop.quit()))
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        return result.get("v")

    def save_scrolled(view, js, wait, width, height, target):
        """Scroll through the page and stitch the screens; the fixed top bar shows once."""
        from PySide6.QtGui import QImage, QPainter
        step = view.height()
        # the world is fixed to the screen; pin it to the page so the stitched image has no seams
        js(f"var w=document.querySelector('.sp-world'); if(w){{w.style.position='absolute'; w.style.height='{height}px';}}")
        canvas = QImage(width, height, QImage.Format_RGB32)
        painter = QPainter(canvas)
        y = 0
        last = -1
        while y < height:
            js(f"window.scrollTo(0, {y}); document.querySelectorAll('.sp-bar').forEach(function(b){{b.style.visibility = {y} ? 'hidden' : ''}});")
            wait(450)
            actual = int(js("Math.round(window.scrollY)") or 0)
            shot = view.grab().toImage()
            painter.drawImage(0, actual, shot)
            if actual + step >= height or actual <= last:
                break  # the end of the page, or the page would not scroll further
            last = actual
            y = actual + step
        painter.end()
        js("document.querySelectorAll('.sp-bar').forEach(function(b){b.style.visibility=''}); window.scrollTo(0,0);")
        canvas.save(str(target))

    args.out.mkdir(parents=True, exist_ok=True)
    saved = 0
    for name in args.pages:
        for width in args.widths:
            for theme in args.themes:
                view.resize(width, 900)
                loaded = QEventLoop()
                page.loadFinished.connect(loaded.quit)
                QTimer.singleShot(20000, loaded.quit)  # never wait forever for a page
                view.load(QUrl(f"http://{origin}{PREFIX}/{name}.html"))
                loaded.exec()
                page.loadFinished.disconnect(loaded.quit)
                js(f"document.documentElement.setAttribute('data-theme','{theme}'); window.PQSSE && window.PQSSE.placeAll();"
                   "document.querySelectorAll('img[loading=lazy]').forEach(function(i){i.loading='eager'});")
                wait(900)
                height = 900 if args.viewport_only else int(js("Math.ceil(document.documentElement.scrollHeight)") or 900)
                save_scrolled(view, js, wait, width, min(height, 12000), args.out / f"{name}-{theme}-{width}.png")
                saved += 1
    httpd.shutdown()
    print(f"saved {saved} screenshots to {args.out}")
    if foreign:
        print("REQUESTS TO OTHER HOSTS (blocked):")
        for url in sorted(set(foreign)):
            print("  " + url)
        return 1
    print("no request left 127.0.0.1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
