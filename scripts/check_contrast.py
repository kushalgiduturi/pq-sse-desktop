"""WCAG contrast check of the theme tokens in app/spatial/qml/Theme.qml, both themes.

    python scripts/check_contrast.py

Text tokens must reach 4.5:1 on the panel colors; marks, role colors and chart colors
must reach 3:1 (WCAG 1.4.11, non-text). Panels are a tint over the room, so each text
color is also checked on the panel color blended over the darkest and lightest room color
at the panel's real opacity. Exit code 1 if any pair fails.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

THEME = Path(__file__).resolve().parent.parent / "app" / "spatial" / "qml" / "Theme.qml"
TEXT = ("textPrimary", "textSecondary", "textMuted")
MARKS = ("accent", "alice", "bob", "carol", "cloud", "ok", "fail", "warn", "attacker", "series1", "series2")
PANEL_OPACITY = 0.86


def tokens() -> dict[str, tuple[str, str]]:
    found = {}
    for name, dark, light in re.findall(r'readonly property color (\w+): dark \? "(#[0-9A-Fa-f]{6})" : "(#[0-9A-Fa-f]{6})"', THEME.read_text(encoding="utf-8")):
        found[name] = (dark, light)
    return found


def rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def luminance(color: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: tuple, b: tuple) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(top: tuple, under: tuple, alpha: float) -> tuple:
    return tuple(t * alpha + u * (1 - alpha) for t, u in zip(top, under))


def check() -> tuple[list[str], list[str]]:
    table = tokens()
    lines, failures = [], []
    for mode, index in (("dark", 0), ("light", 1)):
        color = {name: rgb(pair[index]) for name, pair in table.items()}
        surfaces = {"panel": color["glassFill"], "raised": color["glassRaised"],
                    "panel over room top": blend(color["glassFill"], color["roomTop"], PANEL_OPACITY),
                    "panel over room bottom": blend(color["glassFill"], color["roomBottom"], PANEL_OPACITY)}
        pairs = [(name, surface, 4.5) for name in TEXT for surface in surfaces]
        pairs += [(name, "panel", 3.0) for name in MARKS] + [("accentOn", "accent", 4.5), ("onRole", "alice", 4.5),
                                                              ("onRole", "bob", 4.5), ("onRole", "carol", 4.5), ("onRole", "cloud", 4.5),
                                                              ("onRole", "attacker", 4.5), ("glassStroke", "panel", 1.5)]
        for name, surface, need in pairs:
            background = surfaces[surface] if surface in surfaces else color[surface]
            value = ratio(color[name], background)
            ok = value >= need
            line = f"{mode:5} {name:14} on {surface:22} {value:5.2f}:1 (needs {need}:1) {'pass' if ok else 'FAIL'}"
            lines.append(line)
            if not ok:
                failures.append(line)
    return lines, failures


def main() -> int:
    lines, failures = check()
    print("\n".join(lines))
    print(f"\n{len(lines)} pairs checked, {len(failures)} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
