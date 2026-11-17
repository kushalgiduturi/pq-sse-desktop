"""WCAG contrast check of the Quiet glass tokens in app/spatial/qml/Theme.qml, both themes.

    python scripts/check_contrast.py

Glass is translucent, so every check is made on the composite a person really sees: the
surface fill blended over the world (its darkest and lightest point, and the wash), for the
page panel (depth 2), the top bar (depth 3) and the floating layer (depth 4), in the blurred
and the dense (software or Reduce transparency) variant. Text and status colors need 4.5:1,
text on the accent and on the solid bad color needs 4.5:1, pill text on its 12 percent tint
needs 4.5:1, and the accent, the focus ring and the chart colors need 3:1 (WCAG 1.4.11).
Exit code 1 if any pair fails.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

THEME = Path(__file__).resolve().parent.parent / "app" / "spatial" / "qml" / "Theme.qml"
TEXT = ("text", "text2", "text3", "accentText", "ok", "warn", "bad", "info")
MARKS = ("accent", "ring", "series1", "series2")
PILLS = ("ok", "warn", "bad", "info", "accentText")

Color = tuple  # (r, g, b, a) in 0..1


def parse(value: str) -> Color:
    value = value.strip()
    if value.startswith('"#'):
        h = value.strip('"')
        return (int(h[1:3], 16) / 255, int(h[3:5], 16) / 255, int(h[5:7], 16) / 255, 1.0)
    m = re.fullmatch(r"rgba\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\s*\)", value)
    if m:
        r, g, b, a = (float(x) for x in m.groups())
        return (r / 255, g / 255, b / 255, a)
    raise ValueError(value)


def split_top(text: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur]


def tokens() -> dict[str, tuple[Color, Color]]:
    source = THEME.read_text(encoding="utf-8")
    found: dict[str, tuple[Color, Color]] = {}
    for name, dark, light in re.findall(r"readonly property color (\w+): dark \? (\"#[0-9A-Fa-f]{6}\"|rgba\([^)]*\)) : (\"#[0-9A-Fa-f]{6}\"|rgba\([^)]*\))", source):
        found[name] = (parse(dark), parse(light))
    for name, value in re.findall(r"readonly property color (\w+): (\"#[0-9A-Fa-f]{6}\")\s*$", source, re.M):
        found[name] = (parse(value), parse(value))
    for name in ("glassFills", "solidFills"):
        m = re.search(rf"readonly property var {name}: dark\s*\?\s*\[(.*?)\]\s*:\s*\[(.*?)\]", source, re.S)
        dark, light = (split_top(m.group(i)) for i in (1, 2))
        for depth, (d, l) in enumerate(zip(dark, light)):
            found[f"{name}{depth}"] = (parse(d), parse(l))
    # chart colors are aliases: measured series in accent, comparison in text-2
    found["series1"], found["series2"] = found["accent"], found["text2"]
    return found


def over(top: Color, under: Color) -> Color:
    a = top[3]
    return tuple(t * a + u * (1 - a) for t, u in zip(top[:3], under[:3])) + (1.0,)


def luminance(c: Color) -> float:
    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: Color, b: Color) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def check() -> tuple[list[str], list[str]]:
    table = tokens()
    lines, failures = [], []
    for mode, i in (("dark", 0), ("light", 1)):
        c = {name: pair[i] for name, pair in table.items()}
        worlds = {"world": c["world"], "world edge": c["worldEdge"], "world wash": over(c["worldWash"], c["world"])}
        surfaces = {}
        for depth, label in ((2, "panel"), (3, "bar"), (4, "float")):
            for variant in ("glassFills", "solidFills"):
                for wname, w in worlds.items():
                    surfaces[f"{label} {variant[:5]} on {wname}"] = over(c[f"{variant}{depth}"], w)
        def test(name: str, fg: Color, surface: str, bg: Color, need: float) -> None:
            fg = over(fg, bg) if fg[3] < 1 else fg
            value = ratio(fg, bg)
            ok = value >= need
            line = f"{mode:5} {name:16} on {surface:34} {value:5.2f}:1 (needs {need}) {'pass' if ok else 'FAIL'}"
            lines.append(line)
            if not ok:
                failures.append(line)
        for sname, bg in surfaces.items():
            for name in TEXT:
                test(name, c[name], sname, bg, 4.5)
            for name in MARKS:
                test(name, c[name], sname, bg, 3.0)
            for name in PILLS:
                test(name + " pill", c[name], sname + " +tint", over(c[name][:3] + (0.12,), bg), 4.5)
        test("accentInk", c["accentInk"], "accent", c["accent"], 4.5)
        test("accentInk", c["accentInk"], "badSolid", c["badSolid"], 4.5)
    return lines, failures


def main() -> int:
    lines, failures = check()
    print("\n".join(failures if "--failures" in sys.argv else lines))
    print(f"\n{len(lines)} pairs checked, {len(failures)} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
