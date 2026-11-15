"""Check the feature map in SPATIAL_PLAN.md: every old feature must have a new location.

    python scripts/check_feature_map.py            fails if a row has no new location
    python scripts/check_feature_map.py --done     also fails if a row is not ticked [x]

Exit code 0 = fine, 1 = a feature would be lost.
"""
from __future__ import annotations

import sys
from pathlib import Path

PLAN = Path(__file__).resolve().parent.parent / "SPATIAL_PLAN.md"
VAGUE = {"", "tbd", "todo", "?", "none", "removed", "n/a"}


def rows(text: str) -> list[list[str]]:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("| # | Feature today"):
            inside = True
            continue
        if inside:
            if not line.startswith("|"):
                break
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells and cells[0].isdigit():
                out.append(cells)
    return out


def check(text: str, require_done: bool = False) -> list[str]:
    problems = []
    table = rows(text)
    if len(table) < 30:
        problems.append(f"the feature map has only {len(table)} rows; it should list every old feature")
    for cells in table:
        number, feature = cells[0], cells[1] if len(cells) > 1 else ""
        new = cells[3] if len(cells) > 3 else ""
        done = cells[4] if len(cells) > 4 else ""
        if new.lower() in VAGUE:
            problems.append(f"row {number} ({feature}): no new location")
        if require_done and "[x]" not in done.lower():
            problems.append(f"row {number} ({feature}): not ticked as done")
    return problems


def main(argv: list[str]) -> int:
    text = PLAN.read_text(encoding="utf-8")
    problems = check(text, "--done" in argv)
    for line in problems:
        print("FEATURE MAP:", line)
    table = rows(text)
    ticked = sum(1 for cells in table if len(cells) > 4 and "[x]" in cells[4].lower())
    print(f"Feature map: {len(table)} rows, {ticked} ticked, {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
