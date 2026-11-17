"""Check for updates, only when the user asks (About, "Check for updates"). Never automatic.

What it does, in order:
  1. Downloads latest.json and latest.json.issig from the site address in packaging/release.toml,
     over HTTPS only. A redirect is followed only to a host on the list in that file.
  2. Checks the signature with the public key built into the app (installer/issig-public-key.txt,
     the same key the web installer has) before reading anything from the file list.
  3. Compares the version with this program's version.
On request it also downloads the web installer named in the signed file list, checks its size,
SHA-256 and signature, and only then hands it to Windows to run.
Nothing is sent but the HTTP requests themselves: no identifiers, no settings, no statistics.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from pqsse import paths

from . import issig

CONFIG_FILE = "packaging/release.toml"
PUBLIC_KEY_FILE = "installer/issig-public-key.txt"
MAX_MANIFEST = 64 * 1024
MAX_SIGNATURE = 4 * 1024
MAX_WEB_SETUP = 20 * 1024 * 1024


class UpdateError(Exception):
    """A plain-language reason the check could not finish."""


@dataclass
class Config:
    manifest_url: str
    allowed_hosts: set[str]
    public_key: issig.PublicKey | None
    insecure_hosts: set[str] = field(default_factory=set)   # tests only: plain http to these hosts
    timeout: float = 15.0


def load_config() -> Config:
    with open(paths.resource(CONFIG_FILE), "rb") as handle:
        data = tomllib.load(handle)
    key_path = paths.resource(PUBLIC_KEY_FILE)
    key = issig.parse_public_key(key_path.read_text(encoding="utf-8")) if key_path.is_file() else None
    return Config(manifest_url=data["project"]["manifest_url"], allowed_hosts=set(data["web_setup"]["allowed_hosts"]), public_key=key)


def _check_url(url: str, config: Config) -> None:
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme == "http" and host in config.insecure_hosts:
        return
    if parts.scheme != "https":
        raise UpdateError(f"refused a non-HTTPS address: {url}")
    if host not in config.allowed_hosts:
        raise UpdateError(f"refused an address outside the official hosts: {host}")


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl, self.config)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url: str, config: Config, limit: int) -> bytes:
    _check_url(url, config)
    # the system proxy settings apply (urllib reads them from Windows)
    opener = urllib.request.build_opener(_Redirects(config))
    request = urllib.request.Request(url, headers={"User-Agent": "PQ-SSE-Desktop-update-check"})
    try:
        with opener.open(request, timeout=config.timeout) as response:
            data = response.read(limit + 1)
    except UpdateError:
        raise
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"the server answered with HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateError(f"no connection to the update server ({reason})") from None
    if len(data) > limit:
        raise UpdateError("the server sent more data than expected")
    return data


def version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for piece in str(text).strip().lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def fetch_manifest(config: Config) -> dict:
    if config.public_key is None:
        raise UpdateError("this build has no signing key built in, so it cannot check the file list")
    manifest = _get(config.manifest_url, config, MAX_MANIFEST)
    signature = _get(config.manifest_url + ".issig", config, MAX_SIGNATURE)
    try:
        issig.verify(signature.decode("utf-8", errors="replace"), manifest, [config.public_key], expected_name="latest.json")
    except issig.SignatureError as exc:
        raise UpdateError(f"the file list failed its signature check ({exc})") from None
    data = json.loads(manifest.decode("utf-8"))
    if data.get("schema") != 1 or "version" not in data:
        raise UpdateError("the file list has a format this version does not know")
    return data


def check(current_version: str, config: Config | None = None) -> dict:
    """Returns {status: newer|current|error, version, current, released, notes_url, download_page, message, manifest}."""
    config = config or load_config()
    result = {"current": current_version, "version": "", "released": "", "notes_url": "", "download_page": "", "message": "",
              "web_available": False}
    try:
        manifest = fetch_manifest(config)
    except UpdateError as exc:
        return {**result, "status": "error", "message": str(exc)}
    except (ValueError, UnicodeDecodeError):
        return {**result, "status": "error", "message": "the file list could not be read"}
    newer = version_tuple(manifest["version"]) > version_tuple(current_version)
    return {**result, "status": "newer" if newer else "current", "version": manifest["version"],
            "released": manifest.get("released", ""), "notes_url": manifest.get("notes_url", ""),
            "download_page": manifest.get("download_page", ""), "web_available": bool(manifest.get("web_setup", {}).get("available")),
            "manifest": manifest}


def download_web_setup(manifest: dict, target_dir: Path, config: Config | None = None) -> Path:
    """Download the web installer from the signed file list and check it. Returns its path."""
    config = config or load_config()
    entry = manifest.get("web_setup", {})
    if not entry.get("available"):
        raise UpdateError("this release has no web installer; use the download page")
    data = _get(entry["url"], config, MAX_WEB_SETUP)
    signature = _get(entry["url"] + ".issig", config, MAX_SIGNATURE)
    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise UpdateError("the web installer does not match the signed file list; it was not run")
    try:
        issig.verify(signature.decode("utf-8", errors="replace"), data, [config.public_key], expected_name=entry["file"])
    except issig.SignatureError as exc:
        raise UpdateError(f"the web installer failed its signature check ({exc}); it was not run") from None
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / entry["file"]
    path.write_bytes(data)
    return path
