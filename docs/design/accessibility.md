# Accessibility audit: spatial UI

**Standard:** WCAG 2.1 AA. **Date:** 2026-11-15. **Method:** token contrast computed by
`scripts/check_contrast.py`; roles, names and keyboard handlers read from the QML source;
reduced motion and the software renderer exercised by tests and scripted runs.
**Not done:** no screen reader (Narrator, NVDA) was run, and nobody walked through the
window with the keyboard only. Those two checks decide whether the items marked "by
design" below really work.

## Summary

Issues found: 9. Critical: 0. Major: 3 (open). Minor: 6 (2 fixed, 4 open).

## Findings

### Perceivable

| # | Issue | Criterion | Severity | State |
| --- | --- | --- | --- | --- |
| 1 | Meaning by color: results, roles and chart series | 1.4.1 | Minor | Fixed. Results carry a check or cross shape and a word; roles carry a name or initial, the cloud is a square; chart series have a legend, value labels and a text table. |
| 2 | A passed verification showed the red "!" security mark in the Story bar | 1.4.1, 3.3.1 | Minor | Fixed: a pass shows a green check mark. |
| 3 | Text on translucent panels | 1.4.3 | Minor | Checked by calculation: every text token passes on the panel tint blended over the darkest and the lightest room color. Not measured on real pixels over the moving lights. |
| 4 | Text size goes up to 125 % only | 1.4.4 (200 %) | Major | Open. Layouts were built for 90 to 125 %. At 200 % the dock and the Journey path would not fit. Windows display scaling still applies on top. |

### Operable

| # | Issue | Criterion | Severity | State |
| --- | --- | --- | --- | --- |
| 5 | Sheets and the palette do not trap focus: Tab can reach controls behind them | 2.4.3 | Major | Open. Escape and the Close button work; the scrim blocks the mouse only. |
| 6 | A focused control inside a scrolling card area is not scrolled into view | 2.4.7, 2.1.1 | Major | Open. Every control is reachable with Tab and shows a 2 px focus ring, but it may be outside the visible part of the list. |
| 7 | Small targets: clickable chips (30 px high), "More options" (35 px), timeline marks (16 px dot in a 30 px cell) | 2.5.5 (AAA), 2.5.8 | Minor | Open. Primary and secondary buttons are 44 px. |
| 8 | Plain keys 1 to 5 and I only work when no text field has the focus | 2.1.4 | Minor | By design: Ctrl+1 to Ctrl+5 and Ctrl+I always work, and single-key shortcuts must not fire while typing. |

### Understandable and robust

| # | Issue | Criterion | Severity | State |
| --- | --- | --- | --- | --- |
| 9 | Custom controls need names and roles | 4.1.2, 3.3.2 | Minor | Set in code for buttons, chips, segmented controls, choice pills, text fields (including the password flag), dock items, path steps, timeline marks, cards and sheets. Not verified with a screen reader. |

Errors (3.3.1, 3.3.3) use the existing three-part text: what happened, why it matters,
what to do next, plus "Copy technical details". Passphrase fields are labeled and say that
a passphrase cannot be recovered.

## Color contrast (computed)

`python scripts/check_contrast.py`: 60 pairs, 0 failures. Lowest values per kind:

| Element | Theme | Ratio | Required |
| --- | --- | --- | --- |
| Muted text on panel (lowest: over the lightest room color) | dark | 5.77:1 | 4.5:1 |
| Muted text on panel (lowest: over the darkest room color) | light | 6.04:1 | 4.5:1 |
| Text on the filled button | dark, light | 6.79:1, 5.73:1 | 4.5:1 |
| Result marks and role colors on panel (lowest) | both | above 3:1 | 3:1 |
| Chart colors on panel | both | pass in the dataviz validator, colorblind separation 24.7 or more | 3:1 |

A test (`test_theme_tokens_meet_wcag_contrast`) runs this check on every test run.

## Motion

- Reduce motion is on when the setting is on, when Windows "Show animations" is off, or
  when the software renderer is in use.
- With it on: no ambient light motion, no parallax, no springs, no flying packets (they
  appear at the destination), and the Step Inspector advances one caption at a time.
  Short fades stay so that changes are still visible.
- A test checks that no animation is running in that mode once the fades have ended.
- No animation flashes. Educational replays can be paused, stepped and skipped.

## Keyboard map

| Keys | Action |
| --- | --- |
| Tab, Shift+Tab | Next and previous control |
| Enter or Space | Press the focused button, chip, pill, card, step or dock item |
| Left, Right | Move the selection in a segmented control |
| Ctrl+1 to Ctrl+5 (or 1 to 5 outside text fields) | Journey, Stage, Workspace, Security Lab, Insights |
| Ctrl+K or F1 | Command palette (Up, Down, Enter, Esc) |
| Ctrl+I (or I) | Open or close the Step Inspector |
| Esc | Close the palette, a sheet or the inspector |

## Priority fixes still to do

1. Trap focus inside sheets and the palette, and return it to the control that opened them.
2. Scroll the focused control into view inside card lists.
3. Test with Narrator or NVDA and with the keyboard only; fix what that finds.
4. Larger hit areas for chips, quiet buttons and timeline marks.
5. Decide whether to support 200 % text, or state Windows display scaling as the way to enlarge.
