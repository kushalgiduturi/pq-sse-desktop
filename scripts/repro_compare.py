"""Reproducible build check: build the same thing twice and compare every file by SHA-256.

    python scripts/repro_compare.py A_FOLDER B_FOLDER [--out docs/measurements/reproducible.md]

The two folders are two build outputs of the same commit (for example two runs of build_server.ps1 with
different -BuildRoot). Prints and writes which files are identical, which differ, and which exist in only
one build. For a differing PE file (.exe, .dll, .pyd) it also says whether the difference is only in the
header time stamp, which is the usual reason.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pe_timestamp_only(a: bytes, b: bytes) -> bool:
    """True if two PE files differ only in the COFF header TimeDateStamp (and the checksum)."""
    if len(a) != len(b) or a[:2] != b"MZ":
        return False
    pe = struct.unpack_from("<I", a, 0x3C)[0]
    stamp = range(pe + 8, pe + 12)
    checksum = range(pe + 24 + 64, pe + 24 + 68)
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    return bool(diffs) and all(i in stamp or i in checksum for i in diffs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    fa = {p.relative_to(args.a).as_posix(): p for p in args.a.rglob("*") if p.is_file()}
    fb = {p.relative_to(args.b).as_posix(): p for p in args.b.rglob("*") if p.is_file()}
    same, differ, only = [], [], sorted(set(fa) ^ set(fb))
    for name in sorted(set(fa) & set(fb)):
        if sha(fa[name]) == sha(fb[name]):
            same.append(name)
        else:
            note = ""
            if name.lower().endswith((".exe", ".dll", ".pyd")):
                note = "PE time stamp only" if pe_timestamp_only(fa[name].read_bytes(), fb[name].read_bytes()) else "content"
            differ.append((name, fa[name].stat().st_size, note))
    lines = ["# Reproducible build comparison", "",
             f"Two builds of the same commit: `{args.a}` and `{args.b}`.", "",
             f"- Files in both: {len(same) + len(differ)}; identical: {len(same)}; different: {len(differ)}; in one build only: {len(only)}.",
             ""]
    if differ:
        lines += ["| Different file | Size (bytes) | Kind of difference |", "| --- | ---: | --- |"]
        lines += [f"| `{n}` | {s:,} | {k or 'content'} |" for n, s, k in differ]
        lines.append("")
    if only:
        lines += ["In one build only:", ""] + [f"- `{n}`" for n in only] + [""]
    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
