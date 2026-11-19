"""Write winget manifests for the Standard installer from a release's latest.json.

    python scripts/make_winget.py <latest.json> [--out packaging/winget]
    winget validate --manifest packaging/winget/manifests/p/PQSSE/PQSSEDesktop/<version>

Writes the three files winget expects (version, installer, defaultLocale) under the same folder
layout as the winget-pkgs repository. Every URL and hash comes from latest.json. Submitting them
to winget-pkgs is a pull request on GitHub that the maintainer decides on; this script does not.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "1.12.0"                   # the manifest version winget-pkgs merges (checked 2026-11-19)
PACKAGE_ID = "PQSSE.PQSSEDesktop"


def product_code() -> str:
    """The Apps and Features key the installer writes: Inno Setup's AppId plus "_is1".

    Read from installer/pqsse.iss (the real app, not the test twin) so that winget can tell that the
    app is installed and which version it has."""
    iss = (ROOT / "installer" / "pqsse.iss").read_text(encoding="utf-8")
    found = re.search(r'#else\s*\n\s*#define AppName "PQ-SSE Desktop"\s*\n\s*#define AppIdValue "\{(\{[0-9A-F-]{36}\})"', iss)
    if not found:
        raise SystemExit("make_winget: the AppId of PQ-SSE Desktop was not found in installer/pqsse.iss")
    return found.group(1) + "_is1"


def write(out: Path, manifest: dict) -> Path:
    with open(ROOT / "packaging" / "release.toml", "rb") as handle:
        config = tomllib.load(handle)
    std = manifest["channels"]["standard"]
    version = manifest["version"]
    folder = out / "manifests" / "p" / "PQSSE" / "PQSSEDesktop" / version
    folder.mkdir(parents=True, exist_ok=True)
    header = f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{{kind}}.{SCHEMA}.schema.json\n"
    (folder / f"{PACKAGE_ID}.yaml").write_text(
        header.format(kind="version")
        + f"PackageIdentifier: {PACKAGE_ID}\nPackageVersion: {version}\nDefaultLocale: en-US\nManifestType: version\nManifestVersion: {SCHEMA}\n",
        encoding="utf-8")
    (folder / f"{PACKAGE_ID}.installer.yaml").write_text(
        header.format(kind="installer")
        + f"PackageIdentifier: {PACKAGE_ID}\nPackageVersion: {version}\n"
        + "InstallerType: inno\nScope: user\nInstallModes:\n  - interactive\n  - silent\n  - silentWithProgress\n"
        + "InstallerSwitches:\n  Silent: /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER\n"
        + "  SilentWithProgress: /SILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER\n"
        + "UpgradeBehavior: install\nElevationRequirement: elevationProhibited\n"
        + f"MinimumOSVersion: {manifest['min_os']}\n"
        + "Installers:\n  - Architecture: x64\n"
        + f"    InstallerUrl: {std['url']}\n    InstallerSha256: {std['sha256'].upper()}\n"
        + f"    ProductCode: '{product_code()}'\n"
        + f"ManifestType: installer\nManifestVersion: {SCHEMA}\n",
        encoding="utf-8")
    repo = config["project"]["repo"]
    (folder / f"{PACKAGE_ID}.locale.en-US.yaml").write_text(
        header.format(kind="defaultLocale")
        + f"PackageIdentifier: {PACKAGE_ID}\nPackageVersion: {version}\nPackageLocale: en-US\n"
        + "Publisher: PQ-SSE\nPackageName: PQ-SSE Desktop\nLicense: MIT\n"
        + f"LicenseUrl: https://github.com/{repo}/blob/master/LICENSE\n"
        + f"PackageUrl: {config['project']['site_url']}\nPublisherUrl: https://github.com/{repo}\n"
        + "ShortDescription: Search encrypted documents through an untrusted cloud, with post-quantum keys. Research and teaching software, not audited.\n"
        + f"ReleaseNotesUrl: https://github.com/{repo}/releases/tag/v{version}\n"
        + "Tags:\n  - encryption\n  - post-quantum\n  - searchable-encryption\n  - education\n"
        + f"ManifestType: defaultLocale\nManifestVersion: {SCHEMA}\n",
        encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "packaging" / "winget")
    args = parser.parse_args(argv)
    folder = write(args.out, json.loads(args.manifest.read_text(encoding="utf-8")))
    print(f"winget manifests: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
