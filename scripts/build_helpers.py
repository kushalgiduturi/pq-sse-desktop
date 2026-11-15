"""Small build steps shared by build_windows.ps1, build_release.ps1 and the CI workflow.

    python scripts/build_helpers.py version
    python scripts/build_helpers.py version-file <out.txt> [--variant Standard|GPU]
    python scripts/build_helpers.py licenses <out.txt> [--gpu]
    python scripts/build_helpers.py cuda-runtime <out folder>
    python scripts/build_helpers.py scan <folder>
    python scripts/build_helpers.py emdash <file or folder> ...
    python scripts/build_helpers.py zip <source folder> <out.zip> <name of the top folder in the zip>
    python scripts/build_helpers.py checksums <folder>

Only the standard library is used. Every command prints what it did and returns 0 on
success, 1 on a failed check.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LONG_DASH = chr(0x2014)
APP_NAME = "PQ-SSE Desktop"
COMPANY = "PQ-SSE"
EXE_NAME = "PQ-SSE-Desktop.exe"

# Files that must never be inside a build: databases, key files, settings, pairing files.
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite-wal", ".sqlite-shm", ".db", ".key", ".pem", ".pfx", ".p12", ".pqpub")
FORBIDDEN_NAMES = ("settings.json", "cloud_process.log", ".env")
TEXT_SUFFIXES = (".py", ".md", ".txt", ".toml", ".ps1", ".json", ".cfg", ".ini", ".iss", ".yml", ".yaml", ".rtf")

BASE_PACKAGES = ("PySide6_Essentials", "PySide6_Addons", "shiboken6", "cryptography", "cffi", "kyber-py",
                 "dilithium-py", "numpy", "pypdf", "pyinstaller")
GPU_PACKAGES = ("cupy-cuda12x", "cuda-pathfinder", "nvidia-cuda-nvrtc-cu12", "nvidia-cuda-runtime-cu12")
LICENSE_WORDS = ("license", "licence", "copying", "notice", "eula")
CUDA_DLL_PREFIXES = ("nvrtc", "cudart")


def read_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def cmd_version(args) -> int:
    print(read_version())
    return 0


def cmd_version_file(args) -> int:
    """Write the Windows version resource that PyInstaller embeds in the exe."""
    version = read_version()
    numbers = [int(part) for part in version.split(".")[:3] if part.isdigit()]
    numbers = (numbers + [0, 0, 0, 0])[:4]
    name = APP_NAME if args.variant == "Standard" else f"{APP_NAME} ({args.variant} build)"
    text = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(numbers)}, prodvers={tuple(numbers)}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{COMPANY}'),
      StringStruct('FileDescription', '{name}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'PQ-SSE-Desktop'),
      StringStruct('LegalCopyright', 'MIT License. Copyright (c) PQ-SSE Desktop authors.'),
      StringStruct('OriginalFilename', '{EXE_NAME}'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Version resource for {version} ({args.variant}) written to {out}")
    return 0


def _license_files(dist: metadata.Distribution) -> list[Path]:
    found = []
    for item in dist.files or []:
        name = Path(str(item)).name.lower()
        inside_info = ".dist-info" in str(item)
        if inside_info and any(word in name for word in LICENSE_WORDS):
            found.append(Path(dist.locate_file(item)))
    return [path for path in found if path.is_file()]


def _clean(text: str) -> str:
    return text.replace(LONG_DASH, "-").replace("\r\n", "\n")


def cmd_licenses(args) -> int:
    """Collect name, version, license and license text of every bundled library."""
    names = list(BASE_PACKAGES) + (list(GPU_PACKAGES) if args.gpu else [])
    summary, bodies, missing = [], [], []
    for name in names:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
            continue
        meta = dist.metadata
        license_id = (meta.get("License-Expression") or meta.get("License") or "").strip().splitlines()
        license_id = license_id[0][:80] if license_id else ""
        if not license_id:
            license_id = "; ".join(c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License"))
        home = meta.get("Home-page") or next((u.split(",", 1)[1].strip() for u in meta.get_all("Project-URL") or []), "")
        summary.append(f"  {meta['Name']} {meta['Version']}: {license_id or 'see the text below'}  {home}")
        texts = [_clean(path.read_text(encoding="utf-8", errors="replace")) for path in _license_files(dist)]
        bodies.append("=" * 78 + f"\n{meta['Name']} {meta['Version']}\n" + "=" * 78 + "\n"
                      + ("\n\n".join(texts) if texts else "No license file is shipped inside this package. See its project page.\n"))
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    summary.append(f"  Python {sys.version.split()[0]}: PSF License  https://www.python.org")
    if python_license.is_file():
        bodies.append("=" * 78 + f"\nPython {sys.version.split()[0]}\n" + "=" * 78 + "\n"
                      + _clean(python_license.read_text(encoding="utf-8", errors="replace")))
    header = [
        "Third-party software shipped with PQ-SSE Desktop",
        "",
        "PQ-SSE Desktop itself is under the MIT License (see LICENSE.txt).",
        "The libraries below are shipped unchanged inside this program. Each keeps its own license.",
        "Qt and PySide6 are used under the LGPL version 3: they are shipped as separate library files",
        "in the _internal folder, which you may replace with your own builds of the same version.",
    ]
    if args.gpu:
        header += ["The NVIDIA CUDA runtime files (NVRTC and the CUDA runtime) are redistributed under the",
                   "NVIDIA CUDA Toolkit end user license agreement, whose text is included below."]
    header += ["Note: long dashes in the original license texts were replaced by hyphens. Nothing else was changed.",
               "", "Summary", "-------"] + summary + [""]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(header) + "\n" + "\n\n".join(bodies) + "\n", encoding="utf-8")
    print(f"Licenses of {len(summary)} components written to {out}")
    if missing:
        print("Not installed in this environment, so not listed: " + ", ".join(missing))
    return 0


def cmd_cuda_runtime(args) -> int:
    """Build a minimal CUDA folder (bin with the NVRTC and runtime DLLs, include with the
    headers) from NVIDIA's pip wheels. The packaged app points CUDA_PATH at it."""
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "bin").mkdir(parents=True)
    (out / "include").mkdir()
    dlls, headers = [], 0
    for name in ("nvidia-cuda-nvrtc-cu12", "nvidia-cuda-runtime-cu12"):
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            print(f"FAILED: the package {name} is not installed in this environment.")
            return 1
        for item in dist.files or []:
            path = Path(dist.locate_file(item))
            parts = [part.lower() for part in Path(str(item)).parts]
            if not path.is_file() or "__pycache__" in parts:
                continue
            if path.suffix.lower() == ".dll" and path.name.lower().startswith(CUDA_DLL_PREFIXES):
                shutil.copy2(path, out / "bin" / path.name)
                dlls.append((path.name, path.stat().st_size))
            elif "include" in parts and path.suffix.lower() in (".h", ".hpp"):
                relative = Path(*Path(str(item)).parts[parts.index("include") + 1:])
                (out / "include" / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, out / "include" / relative)
                headers += 1
    if not any(name.lower().startswith("nvrtc64") for name, _ in dlls):
        print("FAILED: no NVRTC DLL was found in the installed NVIDIA packages.")
        return 1
    if headers == 0:
        print("FAILED: no CUDA header files were found in the installed NVIDIA packages.")
        return 1
    for name, size in dlls:
        print(f"  bin/{name}  {size / 2**20:.1f} MB")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"CUDA runtime: {len(dlls)} DLLs and {headers} header files, {total / 2**20:.1f} MB, in {out}")
    return 0


def cmd_scan(args) -> int:
    """Fail when a build folder holds a database, key file, settings or pairing file."""
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"FAILED: {folder} is not a folder.")
        return 1
    bad, count = [], 0
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        count += 1
        lower = path.name.lower()
        if lower.endswith(FORBIDDEN_SUFFIXES) or lower in FORBIDDEN_NAMES:
            bad.append(str(path.relative_to(folder)))
    if bad:
        print(f"FAILED: {len(bad)} forbidden file(s) in {folder}:")
        for name in bad[:40]:
            print("  " + name)
        return 1
    print(f"Secret scan OK: {count} files in {folder}, no database, key, settings or pairing file.")
    return 0


def _text_files(target: Path):
    if target.is_file():
        yield target
        return
    for path in target.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and not any(
                part in {".git", "__pycache__", ".pytest_cache", "_internal"} for part in path.parts):
            yield path


def cmd_emdash(args) -> int:
    """Fail when a text file contains the long dash character."""
    bad, count = [], 0
    for target in args.targets:
        for path in _text_files(Path(target)):
            count += 1
            raw = path.read_bytes()
            utf16 = raw[:2] in (b"\xff\xfe", b"\xfe\xff")
            text = raw.decode("utf-16" if utf16 else "utf-8", errors="ignore")
            if LONG_DASH in text:
                bad.append(str(path))
    if bad:
        print(f"FAILED: long dash found in {len(bad)} file(s):")
        for name in bad:
            print("  " + name)
        return 1
    print(f"Long dash check OK: {count} text files.")
    return 0


def cmd_zip(args) -> int:
    source, out = Path(args.source), Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, str(Path(args.top) / path.relative_to(source)))
                count += 1
    print(f"Zip: {count} files, {out.stat().st_size / 2**20:.1f} MB, {out}")
    return 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cmd_checksums(args) -> int:
    folder = Path(args.folder)
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    lines = [f"{sha256(path)}  {path.name}" for path in files]
    (folder / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="ascii")
    for line in lines:
        print(line)
    print(f"Checksums of {len(files)} files written to {folder / 'SHA256SUMS.txt'}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="PQ-SSE Desktop build helpers")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version").set_defaults(fn=cmd_version)
    p = sub.add_parser("version-file")
    p.add_argument("out")
    p.add_argument("--variant", default="Standard")
    p.set_defaults(fn=cmd_version_file)
    p = sub.add_parser("licenses")
    p.add_argument("out")
    p.add_argument("--gpu", action="store_true")
    p.set_defaults(fn=cmd_licenses)
    p = sub.add_parser("cuda-runtime")
    p.add_argument("out")
    p.set_defaults(fn=cmd_cuda_runtime)
    p = sub.add_parser("scan")
    p.add_argument("folder")
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("emdash")
    p.add_argument("targets", nargs="+")
    p.set_defaults(fn=cmd_emdash)
    p = sub.add_parser("zip")
    p.add_argument("source")
    p.add_argument("out")
    p.add_argument("top")
    p.set_defaults(fn=cmd_zip)
    p = sub.add_parser("checksums")
    p.add_argument("folder")
    p.set_defaults(fn=cmd_checksums)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
