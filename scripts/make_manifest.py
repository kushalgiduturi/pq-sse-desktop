"""Write latest.json and SHA256SUMS.txt for a release folder, and sign them when a key is set.

    python scripts/make_manifest.py <release folder> [--date 2026-11-20] [--sign]

Every size and hash comes from the real files in the folder. A GPU file that is not in the
folder is written as "available": false (the site then says "not available yet", without a
link). With --sign, Inno Setup's ISSigTool signs latest.json and every package; the private key
file is named by the ISSIGTOOL_KEY_FILE environment variable and is never read by this script.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "packaging" / "release.toml"
SCHEMA = 1


def load_config() -> dict:
    with open(CONFIG, "rb") as handle:
        return tomllib.load(handle)


def read_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def entry(folder: Path, name: str, base: str) -> dict:
    path = folder / name
    if not path.is_file():
        return {"available": False}
    return {"available": True, "file": name, "url": base + name, "size": path.stat().st_size, "sha256": sha256(path)}


def build_manifest(folder: Path, version: str, released: str, config: dict | None = None) -> dict:
    config = config or load_config()
    files = {key: value.format(version=version) for key, value in config["files"].items()}
    base = config["project"]["download_base"].format(version=version)
    site = config["project"]["site_url"]
    web_name = config["web_setup"]["file_name"]
    manifest = {
        "schema": SCHEMA,
        "name": config["project"]["name"],
        "version": version,
        "released": released,
        "notes_url": site + "release-notes.html",
        "download_page": site + "download.html",
        "min_os": config["requirements"]["min_os"],
        "channels": {
            "standard": entry(folder, files["standard_setup"], base),
            "gpu": {**entry(folder, files["gpu_setup"], base), "min_driver": config["requirements"]["min_driver"]},
        },
        "portable": {
            "standard": entry(folder, files["standard_zip"], base),
            "gpu": entry(folder, files["gpu_zip"], base),
        },
        "web_setup": entry(folder, web_name, base),
    }
    if not manifest["channels"]["standard"]["available"]:
        raise SystemExit(f"FAILED: {files['standard_setup']} is not in {folder}")
    return manifest


def write_sums(folder: Path) -> Path:
    lines = [f"{sha256(p)}  {p.name}" for p in sorted(folder.iterdir())
             if p.is_file() and p.suffix.lower() in (".exe", ".zip", ".json")]
    out = folder / "SHA256SUMS.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def find_issigtool() -> str | None:
    found = shutil.which("ISSigTool.exe")
    if found:
        return found
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        for sub in ("Programs\\Inno Setup 6", "Inno Setup 6"):
            candidate = Path(base) / sub / "ISSigTool.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def sign(paths: list[Path]) -> None:
    if not os.environ.get("ISSIGTOOL_KEY_FILE"):
        raise SystemExit("FAILED: --sign needs the environment variable ISSIGTOOL_KEY_FILE (path of the private key file).")
    tool = find_issigtool()
    if not tool:
        raise SystemExit("FAILED: ISSigTool.exe (Inno Setup 6.5 or newer) was not found.")
    result = subprocess.run([tool, "--quiet", "--allow-overwrite", "sign", *map(str, paths)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit("FAILED: ISSigTool could not sign: " + (result.stderr or result.stdout).strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--version", default=None)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--sign", action="store_true")
    args = parser.parse_args(argv)
    folder = args.folder.resolve()
    manifest = build_manifest(folder, args.version or read_version(), args.date)
    out = folder / "latest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.sign:
        packages = [folder / e["file"] for e in (manifest["channels"]["standard"], manifest["channels"]["gpu"],
                                                 manifest["portable"]["standard"], manifest["portable"]["gpu"],
                                                 manifest["web_setup"]) if e.get("available")]
        sign([out, *packages])
    write_sums(folder)
    print(f"latest.json and SHA256SUMS.txt written to {folder}" + (" (signed)" if args.sign else " (not signed)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
