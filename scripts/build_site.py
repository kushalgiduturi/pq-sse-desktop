"""Build the PQ-SSE Desktop website into site/public/ (static files, no framework).

    python scripts/build_site.py --release-dir <folder with the release files>
    python scripts/build_site.py --manifest <latest.json>

Inputs: site/content.toml (all copy), site/src/ (templates, CSS, JS, fonts, the Stage drawing),
the manifest (every version, size, date and hash on the site comes from it), and the app's
screenshots in docs/design/restyle/after/ (converted to WebP). Output: site/public/, which can
be opened from disk or served by any static host.

Templates use {{ a.b }} (text, escaped) and {{{ a.b }}} (HTML built by this script).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SRC = SITE / "src"
OUT = SITE / "public"
SHOTS = ROOT / "docs" / "design" / "restyle" / "after"
sys.path.insert(0, str(ROOT / "scripts"))
import make_manifest  # noqa: E402

# One line icon set (24 grid, 1.5 stroke), the same family as the app's icons.
_SVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>'
ICONS = {
    "logo": '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/><path d="M12 14.5v2"/>',
    "download": '<path d="M12 4v11"/><path d="M7 10.5l5 5 5-5"/><path d="M5 19.5h14"/>',
    "theme": '<path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"/>',
    "menu": '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>',
    "check": '<path d="M5 12.5l5 5 9-10"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><path d="M12 7.6v.4"/>',
    "alert": '<path d="M12 3.5l9 16H3z"/><path d="M12 9.5v4"/><path d="M12 16.6v.4"/>',
    "person": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20.5c.6-4 3.4-6.5 7-6.5s6.4 2.5 7 6.5"/>',
    "cloud": '<path d="M7 18h10.5a4.5 4.5 0 0 0 0-9 6 6 0 0 0-11.3 1.6A3.8 3.8 0 0 0 7 18z"/>',
    "arrow": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "shield": '<path d="M12 3l7 3v5.5c0 4.5-3.2 7.8-7 9.5-3.8-1.7-7-5-7-9.5V6z"/><path d="M9 12l2.2 2.2 4-4.4"/>',
}
ICON_HTML = {name: _SVG.format(body) for name, body in ICONS.items()}

PLACEHOLDER = re.compile(r"\{\{\{\s*([\w.]+)\s*\}\}\}|\{\{\s*([\w.]+)\s*\}\}")
HEADER = re.compile(r"^<!-- page: (.*?) -->\s*", re.S)


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def lookup(ctx: dict, path: str):
    value = ctx
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(f"no value for {{{{ {path} }}}}")
    return value


def render(template: str, ctx: dict) -> str:
    def fill(match: re.Match) -> str:
        raw, text = match.group(1), match.group(2)
        if raw:
            return str(lookup(ctx, raw))
        return esc(lookup(ctx, text))
    return PLACEHOLDER.sub(fill, template)


def mb(size: int) -> str:
    return f"{size / 2**20:.1f} MB"


# ------------------------------------------------------------------ manifest
def flat_manifest(m: dict) -> dict:
    def part(e: dict, prefix: str) -> dict:
        if not e.get("available"):
            return {f"{prefix}_available": False, f"{prefix}_file": "", f"{prefix}_size": "", f"{prefix}_sha256": "", f"{prefix}_url": ""}
        return {f"{prefix}_available": True, f"{prefix}_file": e["file"], f"{prefix}_size": mb(e["size"]),
                f"{prefix}_sha256": e["sha256"], f"{prefix}_url": e["url"]}
    out = {"version": m["version"], "released": m["released"], "min_os": m["min_os"],
           "min_driver": m["channels"]["gpu"].get("min_driver", "")}
    out.update(part(m["channels"]["standard"], "standard"))
    out.update(part(m["channels"]["gpu"], "gpu"))
    out.update(part(m["portable"]["standard"], "zip_standard"))
    out.update(part(m["portable"]["gpu"], "zip_gpu"))
    out.update(part(m.get("web_setup", {"available": False}), "web"))
    return out


def files_table(m: dict, content: dict) -> str:
    """The table of every package, from the manifest. Unavailable rows have no link."""
    labels = content["files"]
    rows = [("web_setup", None, labels["web"]), ("channels", "standard", labels["standard"]), ("channels", "gpu", labels["gpu"]),
            ("portable", "standard", labels["zip_standard"]), ("portable", "gpu", labels["zip_gpu"])]
    body = []
    for group, key, (name, note) in rows:
        e = m.get(group, {}) if key is None else m[group][key]
        if e.get("available"):
            file_cell = f'<a href="{esc(e["url"])}">{esc(e["file"])}</a>'
            size = f'<span class="sp-mono sp-nowrap">{mb(e["size"])}</span>'
            sha = (f'<span class="sp-hash"><code>{esc(e["sha256"])}</code>'
                   f'<button class="sp-btn sp-btn--ghost sp-btn--icon sp-btn--sm sp-copy" type="button" data-copy="{esc(e["sha256"])}" '
                   f'data-copied="{esc(content["site"]["copied"])}" data-copy-failed="{esc(content["site"]["copy_failed"])}" '
                   f'aria-label="{esc(labels["copy_hash"])} {esc(e["file"])}" hidden>{ICON_HTML["copy"]}</button></span>')
        else:
            file_cell = f'<span class="sp-pill sp-pill--neutral">{esc(content["status"]["neutral"])}</span>'
            size = sha = '<span class="sp-muted">-</span>'
        body.append(f"<tr><td><b>{esc(name)}</b><span class=\"sp-sub\">{esc(note)}</span></td><td>{file_cell}</td>"
                    f"<td class=\"is-hide-sm\">{size}</td><td class=\"is-hide-sm\">{sha}</td></tr>")
    hide = ' class="is-hide-sm"'
    head = "".join(f'<th scope="col"{hide if i > 1 else ""}>{esc(h)}</th>' for i, h in enumerate(labels["head"]))
    return (f'<div class="sp-table-wrap"><table class="sp-table"><caption class="sp-sr">{esc(labels["caption"])}</caption>'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


# ------------------------------------------------------------------ screenshots
def convert_shots(names: list[str], out_dir: Path) -> dict[str, tuple[int, int]]:
    """PNG screenshots of the app -> WebP, 1280 px wide. Returns name -> (width, height)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841  (image plugins need it)
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name in names:
        src = SHOTS / f"{name}.png"
        if not src.is_file():
            raise SystemExit(f"FAILED: screenshot {src} is missing")
        image = QImage(str(src))
        if image.width() > 1280:
            image = image.scaledToWidth(1280, Qt.SmoothTransformation)
        target = out_dir / f"{name}.webp"
        if not image.save(str(target), "WEBP", 82):
            raise SystemExit("FAILED: this Qt has no WebP writer")
        sizes[name] = (image.width(), image.height())
    return sizes


# ------------------------------------------------------------------ page blocks
def nav_links(content: dict, current: str) -> str:
    out = []
    for item in content["nav"]:
        mark = ' aria-current="page"' if item["key"] == current else ""
        out.append(f'<a href="{esc(item["href"])}"{mark}>{esc(item["label"])}</a>')
    return "".join(out)


def footer_links(content: dict) -> str:
    return "".join(f'<a href="{esc(href)}">{esc(label)}</a>' for href, label in content["footer"]["links"])


def home_blocks(content: dict, shots: dict, flat: dict) -> dict:
    h = content["home"]
    cast = "".join(f'<li><span class="sp-glyph">{ICON_HTML[icon]}</span><div><b>{esc(name)}</b><span>{esc(text)}</span></div></li>'
                   for icon, name, text in h["cast"])
    items = []
    for name, alt in h["shots"]:
        w, ht = shots[name]
        items.append(f'<figure class="sp-shot"><img src="img/{name}.webp" width="{w}" height="{ht}" alt="{esc(alt)}" loading="lazy" decoding="async">'
                     f"<figcaption>{esc(alt)}</figcaption></figure>")
    facts = "".join(f'<li class="sp-list-row"><span class="sp-glyph">{ICON_HTML["check"]}</span><span class="sp-grow">{esc(f)}</span></li>' for f in h["facts"])
    nxt = "".join(f'<li class="sp-list-row"><span class="sp-grow"><a href="{esc(href)}"><b>{esc(title)}</b></a>'
                  f'<span class="sp-sub">{esc(text)}</span></span><span class="sp-muted">{ICON_HTML["arrow"]}</span></li>'
                  for href, title, text in h["next"])
    mono = lambda v: f'<span class="sp-mono sp-nowrap">{esc(v)}</span>'  # noqa: E731
    meta = esc(h["meta"]).replace("{version}", mono(flat["version"])).replace("{released}", mono(flat["released"]))
    return {"cast_items": cast, "shot_items": "".join(items), "fact_items": facts, "next_items": nxt,
            "home": {**h, "meta_html": meta}}


def styleguide_blocks(content: dict, manifest: dict) -> dict:
    sg = content["styleguide"]
    tags = {"display": '<p class="sp-title">{}</p>', "lg": '<p class="sp-section-title">{}</p>', "md": "<p>{}</p>",
            "sm": '<p class="sp-muted">{}</p>', "mono": '<p class="sp-mono">{}</p>'}
    types = "".join(tags[k].format(esc(t)) for k, t in sg["type_samples"])
    swatches = [("Accent", "--sp-accent"), ("Accent text", "--sp-accent-text"), ("Text", "--sp-text"), ("Text 2", "--sp-text-2"),
                ("Text 3", "--sp-text-3"), ("OK", "--sp-ok"), ("Warning", "--sp-warn"), ("Bad", "--sp-bad"), ("Info", "--sp-info"),
                ("World", "--sp-world")]
    sw = "".join(f'<li class="sp-swatch"><i class="sw-{token[5:]}"></i><b>{esc(name)}</b><span>{esc(token)}</span></li>' for name, token in swatches)
    depths = "".join(f'<div class="{cls}"><b>{esc(title)}</b><br><span class="sp-muted">{esc(text)}</span></div>' for cls, title, text in sg["depths"])
    seg = "".join(f'<button type="button" aria-pressed="{"true" if i == 0 else "false"}">{esc(label)}</button>' for i, label in enumerate(sg["seg"]))
    flat = flat_manifest(manifest)
    metrics = ('<div class="sp-metrics">'
               f'<div class="sp-metric"><span class="sp-metric-value sp-mono">{esc(flat["version"])}</span><span class="sp-metric-label">{esc(content["download"]["version_label"])}</span></div>'
               f'<div class="sp-metric"><span class="sp-metric-value sp-mono">{esc(flat["released"])}</span><span class="sp-metric-label">{esc(content["download"]["released_label"])}</span></div>'
               f'<div class="sp-metric"><span class="sp-metric-value sp-mono">{esc(flat["standard_size"])}</span><span class="sp-metric-label">{esc(content["download"]["size_label"])}</span></div>'
               "</div>")
    return {"type_items": types, "swatch_items": sw, "depth_items": depths, "seg_items": seg, "metrics_strip": metrics,
            "files_table": files_table(manifest, content)}


SWATCH_CSS = "".join(f"html.sp-ui .sw-{t} {{ background: var(--sp-{t}); }}\n"
                     for t in ("accent", "accent-text", "text", "text-2", "text-3", "ok", "warn", "bad", "info", "world"))


# ------------------------------------------------------------------ build
def build(manifest: dict, out: Path = OUT) -> list[Path]:
    with open(SITE / "content.toml", "rb") as handle:
        content = tomllib.load(handle)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    # CSS: the light tokens are written twice (toggle and system setting) from one source
    css = (SRC / "assets" / "site.css").read_text(encoding="utf-8")
    light = (SRC / "assets" / "tokens-light.css").read_text(encoding="utf-8").rstrip()
    if css.count("/* @light-tokens */") != 2:
        raise SystemExit("FAILED: site.css must hold the light token marker twice")
    css = css.replace("/* @light-tokens */", light) + "\n/* swatches of the style guide */\n" + SWATCH_CSS
    (out / "assets" / "site.css").write_text(css, encoding="utf-8")
    for name in ("site.js", "theme.js"):
        shutil.copy2(SRC / "assets" / name, out / "assets" / name)
    shutil.copytree(SRC / "fonts", out / "fonts")
    (out / "assets" / "icon.svg").write_text(
        _SVG.format(ICONS["logo"]).replace('stroke="currentColor"', 'stroke="#2563eb"').replace('aria-hidden="true" focusable="false"', 'xmlns="http://www.w3.org/2000/svg"'),
        encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    licenses = out / "third-party-licenses.txt"
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_helpers.py"), "licenses", str(licenses)], capture_output=True, text=True)
    if result.returncode != 0 or not licenses.is_file():
        raise SystemExit("FAILED: third-party licenses: " + result.stdout + result.stderr)
    with open(licenses, "a", encoding="utf-8") as handle:
        handle.write("\n\nThis website uses the same two fonts (Onest, Share Tech Mono) as WOFF2 files; their licenses are in fonts/.\n")

    shot_names = [name for name, _ in content["home"]["shots"]]
    shots = convert_shots(shot_names, out / "img")
    flat = flat_manifest(manifest)
    stage_svg = (SRC / "stage.svg").read_text(encoding="utf-8")
    stage_svg = re.sub(r"<!--.*?-->", "", stage_svg, flags=re.S).strip()
    base = (SRC / "base.html").read_text(encoding="utf-8")
    common = {"site": content["site"], "footer": content["footer"], "status": content["status"], "icon": ICON_HTML,
              "manifest": flat, "stage_svg": stage_svg, "footer_links": footer_links(content),
              "nav_label": {item["key"]: item["label"] for item in content["nav"]}, "home": content["home"],
              "styleguide": content["styleguide"]}
    written = []
    for page in sorted((SRC / "pages").glob("*.html")):
        text = page.read_text(encoding="utf-8")
        header = HEADER.match(text)
        if not header:
            raise SystemExit(f"FAILED: {page.name} has no page header comment")
        meta = dict(part.strip().split("=", 1) for part in header.group(1).split(";"))
        body_template = text[header.end():]
        ctx = dict(common)
        if meta["key"] == "home":
            ctx.update(home_blocks(content, shots, flat))
        if meta["key"] == "styleguide":
            ctx.update(styleguide_blocks(content, manifest))
        body = render(body_template, ctx)
        ctx["page"] = {"title": lookup(ctx, meta["title"]) if "." in meta["title"] else meta["title"],
                       "description": lookup(ctx, meta["description"]), "body": body, "head_extra": ""}
        if meta["key"] != "home":
            ctx["page"]["title"] = f'{ctx["page"]["title"]} - {content["site"]["name"]}'
        ctx["nav_links"] = nav_links(content, meta["key"])
        target = out / page.name
        target.write_text(render(base, ctx), encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--release-dir", type=Path)
    source.add_argument("--manifest", type=Path)
    parser.add_argument("--date", default=None)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    else:
        manifest = make_manifest.build_manifest(args.release_dir.resolve(), make_manifest.read_version(),
                                                args.date or __import__("datetime").date.today().isoformat())
    pages = build(manifest, args.out)
    total = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"Site: {len(pages)} pages in {args.out} ({total / 1024:.0f} KB with screenshots and fonts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
