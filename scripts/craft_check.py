"""The Quiet glass craft floor, checked on the source. Exit code 1 on any finding.

    python scripts/craft_check.py

Checks (QML in app/spatial/qml, user text in app/spatial/copy.py, docs and plans):
  gradient text       a Text item that carries a gradient, or a gradient or opacity mask effect
  glow                Glow, DropShadow or RectangularGlow types, MultiEffect shadows, "glow" effects
  colored shadow      the shadow tokens in Theme.qml must be neutral (black or slate)
  nested glass        a blurred Surface (depth 2 to 4) inside another one in the same file
  blur above 24       the backdrop blur (Theme.worldBlur and the per-depth blurs) must stay at 24 or less
  blurred layers      the shell may hold at most three blurred layers at once (panel, top bar, dock;
                      the dock gives its blur to the open inspector)
  accent bars         a thin rectangle along a container's full height or width in a status or accent color
  eyebrows            upper-case or letter-spaced labels
  colors              color literals (hex, rgba, named colors) outside Theme.qml
  emoji               emoji or pictographs in QML or copy
  exclamation marks   in any user-facing string of copy.py
  em dashes           anywhere in app/, scripts/, tests/, docs/design/restyle*, RESTYLE_PLAN.md
The blurred-layer count is also measured at runtime in tests/test_m12_restyle.py.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QML = ROOT / "app" / "spatial" / "qml"
COPY = ROOT / "app" / "spatial" / "copy.py"
NAMED = r"\b(?:white|black|red|green|blue|yellow|orange|purple|gray|grey|pink|cyan|magenta)\b"
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆↔-⇿✀-➿️]")
EM_DASH = chr(0x2014)
FLOATING = {"StoryBar", "Dock", "TopBar", "Inspector"}   # components whose root is blurred glass


def blocks(text: str):
    """Yield (type, body, depth_stack) for every `Type {` block, with the enclosing types."""
    stack: list[tuple[str, int]] = []
    for m in re.finditer(r"([A-Z][A-Za-z0-9_.]*)\s*\{|\{|\}", text):
        if m.group(0) == "}":
            if stack:
                name, start = stack.pop()
                yield name, text[start:m.end()], [s[0] for s in stack]
        else:
            stack.append((m.group(1) or "", m.start()))


def own_props(body: str) -> str:
    """The text of a block without its nested blocks (its own property lines)."""
    out, depth = [], 0
    for ch in body[body.index("{") + 1:-1]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def blurred_surface(name: str, props: str) -> bool:
    if name in FLOATING:
        return True
    if name == "Surface":
        depth = re.search(r"\bdepth:\s*([^;\n]+)", props)
        d = depth.group(1).strip() if depth else "2"
        if d.isdigit() and int(d) < 2:
            return False
        return not re.search(r"\bblur:\s*false", props)
    if name == "Glass":
        return bool(re.search(r"\bfloating:\s*true", props)) and not re.search(r"\bblur:\s*false", props)
    return False


def check() -> list[str]:
    found: list[str] = []
    theme = (QML / "Theme.qml").read_text(encoding="utf-8")

    # backdrop blur values
    world = re.search(r"worldBlur:\s*([\d.]+)", theme)
    if not world or float(world.group(1)) > 24:
        found.append("Theme.qml: worldBlur is above 24")
    for value in re.search(r"blurs:\s*\[([^\]]*)\]", theme).group(1).split(","):
        if float(value) > 24:
            found.append(f"Theme.qml: a per-depth blur of {value.strip()} is above 24")
    # neutral shadows
    shadow = re.search(r'shadowColor:\s*dark \? "(#\w+)" : "(#\w+)"', theme)
    for value in shadow.groups():
        r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
        if max(r, g, b) - min(r, g, b) > 40:
            found.append(f"Theme.qml: shadow color {value} is colored")

    for path in sorted(QML.glob("*.qml")):
        text = path.read_text(encoding="utf-8")
        name = path.name
        code = re.sub(r"//[^\n]*", "", text)
        for number, line in enumerate(code.splitlines(), 1):
            where = f"{name}:{number}"
            if name != "Theme.qml":
                if re.search(r'"#[0-9A-Fa-f]{3,8}"|\brgba\(|Qt\.rgba\(|Qt\.hsla?\(', line):
                    found.append(f"{where}: color literal outside Theme.qml")
                if re.search(r'color:\s*"' + NAMED[2:-2] + '"', line) or re.search(r'Color:\s*"' + NAMED[2:-2] + '"', line):
                    found.append(f"{where}: named color outside Theme.qml")
            if re.search(r"\b(Glow|RectangularGlow|DropShadow|InnerShadow)\s*\{|shadowEnabled:\s*true|glowEnabled", line):
                found.append(f"{where}: glow or effect shadow")
            if re.search(r"\b(LinearGradient|RadialGradient|ConicalGradient|OpacityMask)\s*\{", line):
                found.append(f"{where}: gradient or mask effect (gradient text risk)")
            if re.search(r"Font\.AllUppercase|Font\.SmallCaps", line) or re.search(r"letterSpacing:\s*[1-9]", line):
                found.append(f"{where}: eyebrow styling (upper case or letter spacing)")
            if EMOJI.search(line):
                found.append(f"{where}: emoji")
            if EM_DASH in line:
                found.append(f"{where}: em dash")
        for block, body, enclosing in blocks(code):
            props = own_props(body)
            if block in ("Text", "Txt", "Lbl") and re.search(r"\bgradient:", props):
                found.append(f"{name}: gradient text in a {block}")
            if blurred_surface(block, props):
                outer = [b for b in enclosing if b in ("Surface", "Glass") or b in FLOATING]
                # only the text up to this block decides its parents; check them for blur
                if any(o in FLOATING for o in outer):
                    found.append(f"{name}: blurred {block} nested inside {outer}")
            if block == "Rectangle":
                thin = re.search(r"\bwidth:\s*[1-4]\b", props) and re.search(r"\bheight:\s*parent\.height", props)
                wide = re.search(r"\bheight:\s*[1-4]\b", props) and re.search(r"\bwidth:\s*parent\.width", props)
                tone = re.search(r"\bcolor:\s*Theme\.(accent|ok|warn|bad|info|attacker|fail|ring)\b", props)
                if (thin or wide) and tone:
                    found.append(f"{name}: accent or status bar along an edge")
        # nested blurred surfaces inside a blurred root component file
        root = re.search(r"^([A-Z]\w*)\s*\{", code, re.M)
        if root and (root.group(1) in FLOATING or (root.group(1) in ("Surface",) and not re.search(r"^\s{4}blur:\s*false", code, re.M)
                                                  and not re.search(r"^\s{4}depth:\s*1\b", code, re.M))):
            for block, body, enclosing in blocks(code):
                if enclosing and blurred_surface(block, own_props(body)):
                    found.append(f"{name}: blurred {block} inside a blurred {root.group(1)}")

    # the shell: at most three blurred layers at once
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    layers = ["panel" if re.search(r"id: panel\s*\n\s*depth: 2", main) else None,
              "top bar" if "StoryBar {" in main else None, "dock" if "Dock {" in main else None]
    inspector = "Inspector {" in main
    dock_yields = re.search(r"blur:\s*!win\.inspectorOpen", main) is not None
    count = len([x for x in layers if x]) + (1 if inspector and not dock_yields else 0)
    if count > 3:
        found.append(f"Main.qml: {count} blurred layers can be on screen at once")

    # user-facing text
    tree = ast.parse(COPY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if re.search(r"!(?!=)", value):
                found.append(f"copy.py:{node.lineno}: exclamation mark in {value[:50]!r}")
            if EMOJI.search(value):
                found.append(f"copy.py:{node.lineno}: emoji in {value[:50]!r}")
    for path in [ROOT / "RESTYLE_PLAN.md", *(ROOT / "app").rglob("*.py"), *(ROOT / "app").rglob("*.qml"),
                 *(ROOT / "scripts").glob("*.py"), *(ROOT / "tests").glob("*.py"),
                 *(ROOT / "docs" / "design").glob("restyle*.md"), *(ROOT / "docs" / "design" / "restyle").rglob("*.md")]:
        if path.is_file() and EM_DASH in path.read_text(encoding="utf-8", errors="ignore"):
            found.append(f"{path.relative_to(ROOT)}: em dash")
    return list(dict.fromkeys(found))


def main() -> int:
    found = check()
    for line in found:
        print(line)
    print(f"craft check: {len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
