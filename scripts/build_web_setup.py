"""Compile the web installer (installer/web-setup.iss) with the values from packaging/release.toml.

    python scripts/build_web_setup.py --out <folder> [--public-key installer/issig-public-key.txt]

Test builds (local tests only, never released): --test-manifest http://127.0.0.1:8123/latest.json
--test-hosts 127.0.0.1 allow plain http, the /TESTGPU= and /LOGFILE= parameters, and the given hosts.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.issig import parse_public_key  # noqa: E402

DEFAULT_KEY = ROOT / "installer" / "issig-public-key.txt"


def find_iscc() -> str | None:
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        for sub in ("Programs\\Inno Setup 6", "Inno Setup 6"):
            candidate = Path(base) / sub / "ISCC.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def key_include(public_key: Path, out_dir: Path) -> Path:
    key = parse_public_key(public_key.read_text(encoding="utf-8"))
    include = out_dir / "issig-key.iss"
    include.write_text(
        "[ISSigKeys]\n"
        f'Name: "pqsse_release"; RuntimeID: "pqsse_release"; KeyID: "{key.key_id}"; PublicX: "{key.x}"; PublicY: "{key.y}"\n',
        encoding="utf-8")
    return include


def build(out_dir: Path, public_key: Path = DEFAULT_KEY, version: str | None = None, test_manifest: str | None = None,
          test_hosts: list[str] | None = None, base_name: str = "PQ-SSE-Web-Setup") -> Path:
    if not public_key.is_file():
        raise SystemExit(f"FAILED: no public key at {public_key}. Run scripts/new_signing_key.ps1 first.")
    iscc = find_iscc()
    if not iscc:
        raise SystemExit("FAILED: ISCC.exe (Inno Setup 6.7) was not found.")
    with open(ROOT / "packaging" / "release.toml", "rb") as handle:
        config = tomllib.load(handle)
    with open(ROOT / "pyproject.toml", "rb") as handle:
        version = version or tomllib.load(handle)["project"]["version"]
    out_dir.mkdir(parents=True, exist_ok=True)
    # the key include is a build input, not a release file: keep it out of out_dir
    work = Path(tempfile.mkdtemp(prefix="pqsse-web-setup-"))
    include = key_include(public_key, work)
    hosts = list(config["web_setup"]["allowed_hosts"]) + list(test_hosts or [])
    defines = {
        "AppVersion": version,
        "ManifestUrl": test_manifest or config["project"]["manifest_url"],
        "AllowedHosts": ";".join(hosts),
        "MinDriver": config["requirements"]["min_driver"],
        "KeyInclude": str(include),
        "DownloadPageUrl": config["project"]["site_url"] + "download.html",
        "OutputDir": str(out_dir),
        "OutputBase": base_name,
    }
    args = [iscc, "/Q"] + [f"/D{k}={v}" for k, v in defines.items()]
    if test_manifest:
        args.append("/DTestBuild=1")
    args.append(str(ROOT / "installer" / "web-setup.iss"))
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if result.returncode != 0:
        raise SystemExit("FAILED: the web installer did not compile:\n" + (result.stdout + result.stderr).strip())
    exe = out_dir / (base_name + ".exe")
    print(f"Web installer: {exe} ({exe.stat().st_size / 2**20:.1f} MB)" + (" TEST BUILD" if test_manifest else ""))
    return exe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--version")
    parser.add_argument("--test-manifest")
    parser.add_argument("--test-hosts", nargs="*", default=[])
    args = parser.parse_args(argv)
    build(args.out, args.public_key, args.version, args.test_manifest, args.test_hosts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
