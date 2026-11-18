"""Software bill of materials (CycloneDX 1.5 JSON) from the pinned requirement files.

    python scripts/make_sbom.py            -> docs/SBOM.cdx.json

One component per pinned package, with its PyPI package URL and, where the package is installed in this
environment at the same version, the licence and the SHA-256 of its installed RECORD file (so a reviewer
can tell which build environment it describes). Each component says which deliverables use it: the
desktop app, the GPU build, the server (and Docker image), or tests and building only.
The output has no timestamp, so the file changes only when the pins change.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FILES = {"requirements-lock.txt": "desktop app", "requirements-lock-gpu.txt": "desktop app (GPU build)",
         "requirements-server.txt": "server and Docker image"}
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.+\-]+)")


def pins() -> dict[tuple[str, str], dict]:
    found: dict[tuple[str, str], dict] = {}
    for name, use in FILES.items():
        section = use
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#"):
                header = line.strip("# ").lower()       # section headers are one word: "# tests", "# packaging"
                if header in ("tests", "packaging", "build"):
                    section = "tests and building only"
                continue
            m = PIN.match(line.strip())
            if not m:
                continue
            key = (m.group(1).lower().replace("_", "-"), m.group(2))
            entry = found.setdefault(key, {"name": m.group(1), "version": m.group(2), "uses": set()})
            entry["uses"].add(section)
    return found


def licence_and_record(name: str, version: str) -> tuple[str, str]:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return "", ""
    if dist.version != version:
        return "", ""
    meta = dist.metadata
    licence = meta.get("License-Expression") or ""
    if not licence:
        classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        licence = "; ".join(classifiers) or (meta.get("License") or "").splitlines()[0][:80] if (meta.get("License") or classifiers) else ""
    record = dist.read_text("RECORD") or ""
    return licence, hashlib.sha256(record.encode()).hexdigest() if record else ""


def main() -> int:
    from pqsse.version import get_version
    components = []
    for (key, version), entry in sorted(pins().items()):
        licence, record = licence_and_record(entry["name"], version)
        comp = {"type": "library", "name": entry["name"], "version": version,
                "purl": f"pkg:pypi/{key}@{version}",
                "properties": [{"name": "pqsse:used-by", "value": ", ".join(sorted(entry["uses"]))}]}
        if licence:
            comp["licenses"] = [{"license": {"name": licence}}]
        if record:
            comp["properties"].append({"name": "pqsse:installed-record-sha256", "value": record})
        components.append(comp)
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "metadata": {"component": {"type": "application", "name": "PQ-SSE Desktop and PQ-SSE server",
                                       "version": get_version()},
                         "properties": [{"name": "pqsse:source", "value": ", ".join(FILES)},
                                        {"name": "pqsse:python", "value": "3.11"}]},
            "components": components}
    out = ROOT / "docs" / "SBOM.cdx.json"
    out.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    print(f"{len(components)} components -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
