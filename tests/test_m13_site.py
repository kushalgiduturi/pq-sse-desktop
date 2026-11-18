"""The website: it shows exactly the manifest's values, the committed build matches its sources,
the craft floor holds, and the static and browser checks pass (scripts/check_site.py)."""
from __future__ import annotations

import filecmp
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "site" / "public"
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402
import craft_check_site  # noqa: E402


def fake_manifest(gpu: bool) -> dict:
    def entry(name, size):
        return {"available": True, "file": name, "url": f"https://github.com/kushalgiduturi/pq-sse-desktop/releases/download/v9.9.9/{name}",
                "size": size, "sha256": hashlib.sha256(name.encode()).hexdigest()}
    return {"schema": 1, "version": "9.9.9", "released": "2030-01-02", "min_os": "10.0.17763",
            "notes_url": "x", "download_page": "x",
            "channels": {"standard": entry("PQ-SSE-Desktop-Setup-9.9.9.exe", 57_000_000),
                         "gpu": {**(entry("PQ-SSE-Desktop-Setup-9.9.9-GPU.exe", 129_000_000) if gpu else {"available": False}),
                                 "min_driver": "528.33"}},
            "portable": {"standard": entry("PQ-SSE-Desktop-9.9.9-portable-standard.zip", 86_000_000), "gpu": {"available": False}},
            "web_setup": entry("PQ-SSE-Web-Setup.exe", 2_200_000)}


@pytest.mark.parametrize("gpu", [False, True])
def test_site_shows_exactly_the_manifest_values(tmp_path, gpu):
    m = fake_manifest(gpu)
    build_site.build(m, tmp_path / "public")
    entries = [e for e in (m["channels"]["standard"], m["channels"]["gpu"], m["portable"]["standard"], m["web_setup"]) if e.get("available")]
    for page in ("download.html", "verify.html", "release-notes.html"):
        html = (tmp_path / "public" / page).read_text(encoding="utf-8")
        for e in entries:
            assert e["sha256"] in html and e["url"] in html, (page, e["file"])
            assert f"{e['size'] / 2**20:.1f} MB" in html
        shown = set(re.findall(r"\b[0-9a-f]{64}\b", html))
        assert shown <= {e["sha256"] for e in entries}, page             # no checksum that is not in the manifest
        assert "9.9.9" in html
        if page != "verify.html":
            assert "2030-01-02" in html
    download = (tmp_path / "public" / "download.html").read_text(encoding="utf-8")
    assert m["web_setup"]["url"] in download.split("All files")[0]          # the web installer is the recommended one
    if not gpu:
        assert "not available yet" in download and "-GPU.exe" not in download
    assert json.loads((tmp_path / "public" / "latest.json").read_text()) == m


def test_committed_site_matches_its_sources(tmp_path):
    manifest = json.loads((PUBLIC / "latest.json").read_text(encoding="utf-8"))
    build_site.build(manifest, tmp_path / "public")
    for path in sorted(PUBLIC.rglob("*")):
        if path.is_file() and path.suffix in (".html", ".css", ".js", ".json", ".svg"):
            rebuilt = tmp_path / "public" / path.relative_to(PUBLIC)
            assert rebuilt.is_file() and filecmp.cmp(path, rebuilt, shallow=False), \
                f"{path.relative_to(ROOT)} is out of date: run scripts/build_site.py"


def test_site_craft_floor():
    assert craft_check_site.check() == []


def _has_webengine() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("PySide6.QtWebEngineCore") is not None
    except ImportError:
        return False


def _check_site(*options: str) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_site.py"), *options],
                            capture_output=True, text=True, timeout=900)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert "site check: 0 problem(s)" in result.stdout


def test_site_static_checks():
    _check_site("--no-browser")


@pytest.mark.skipif(sys.platform != "win32" or not _has_webengine(),
                    reason="needs Qt WebEngine (the dev environment has it; the release build environment does not)")
def test_site_browser_checks():
    _check_site()


def test_feature_inventory_matches_the_app_and_is_up_to_date():
    """Every label in site/data/features.json is a string the app shows, every named test exists,
    and docs/FEATURE_INVENTORY.md is the current rendering of the JSON."""
    import json
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_feature_inventory as inv
    data = json.loads(inv.FEATURES.read_text(encoding="utf-8"))
    assert inv.check(data) == []
    assert inv.OUT.read_text(encoding="utf-8") == inv.render(data), "run scripts/build_feature_inventory.py"
