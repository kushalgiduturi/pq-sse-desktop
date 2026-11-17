"""Convert the Hastra WOFF2 fonts to TTF for Qt (Qt cannot load WOFF2).

    python scripts/convert_fonts.py <Hastra fonts folder> <out folder>

Needs fontTools with brotli (a build-time tool only; the app ships the TTF files).
Onest is a variable font (weights 300 to 700); the latin subset is used, since the
app is in English. Share Tech Mono has one weight. The SIL Open Font License texts
are copied next to the fonts, as the license requires.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

FILES = {"onest-latin.woff2": "Onest-Variable.ttf", "share-tech-mono-latin.woff2": "ShareTechMono-Regular.ttf"}
LICENSES = ("OFL-Onest.txt", "OFL-ShareTechMono.txt")


def main(argv: list[str]) -> int:
    source, out = Path(argv[1]), Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for name, target in FILES.items():
        font = TTFont(source / name)
        font.flavor = None
        font.save(out / target)
        axes = [a.axisTag + f" {a.minValue:g}-{a.maxValue:g}" for a in font["fvar"].axes] if "fvar" in font else []
        print(f"{target}: {font['name'].getDebugName(1)}, {len(font.getGlyphOrder())} glyphs, axes {axes or 'none'}")
    for name in LICENSES:
        shutil.copy2(source / name, out / name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
