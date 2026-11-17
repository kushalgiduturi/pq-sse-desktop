# Quiet glass restyle: comparison

The spatial window of PQ-SSE Desktop, restyled in the Hastra "Quiet glass" design language
(source of truth: `C:\xampp\htdocs\Hastra\docs\spatial-ui\`, read only). Light is blue and white
(white glass, black text, cobalt `#2563eb`); dark is red and black (obsidian, white text,
crimson `#e50914`). Structure, behavior, the Python core, the protocol and the bridge contract
are unchanged. Every decision is recorded under "Decisions" in `RESTYLE_PLAN.md` (R1 to R26).

## Folders

| Folder | What is in it |
| --- | --- |
| `before/` | The app before the restyle, both themes, 1440 x 900 |
| `after/` | The app after the restyle, same steps, same size, both themes |
| `compare/` | Each before and after pair side by side (before left) |
| `checkpoint/` | The second stop: shell, Stage, Inspector, Workspace at 1280 x 800 and 1920 x 1080 |
| `styleguide/` | The QML style guide (`python -m app --styleguide`), dark and light, and stitched pairs |
| `fallbacks/` | Software renderer (dark and light), Reduce transparency, Reduce motion, 200 percent text, touch |
| `perf/` | Frame time reports before and after |
| `../hastra-reference/` | The Hastra screenshots used as the visual reference |

## What changed, per screen

- **Shell.** The colored, drifting room lights became a still, quiet world (depth 0) with one
  soft wash. One depth-2 page panel per page, centered, at most 1180 px wide, with a faint
  pointer light. The Story bar is a depth-3 pill 12 px from the edges: the sentence, status
  pills (practice, cloud, engine), the mode, the theme switch and Search (Ctrl K). The dock is
  a small depth-4 tray with a dot under the current page, a slight magnification and a tilt of
  at most 3 degrees on hover. The native title bar follows the theme. Onest and Share Tech
  Mono are bundled and loaded at start.
- **Overlays.** Sheets (errors, glossary, welcome) and the command palette are depth-4 with a
  dense fill over a dim backdrop that is never blurred. The Step Inspector is a depth-4 drawer;
  while it is open the dock gives up its blur, so at most three blurred layers are on screen.
- **Stage.** Flat zones; the zone that acted last gets a soft tint instead of a colored rim.
  Characters are neutral (a glyph and a name). Documents are rows with hairlines, the stored
  bytes are mono, packets are neutral pills, the session timeline is short ticks colored only
  for a passed check or an attack.
- **Step Inspector.** The picture sits in a depth-1 inset; the scrubber is an inset track; the
  numbered step circles became a check (done) and a chevron (current).
- **Workspace.** A flat role rail with a hairline; task sections are titles with a hairline,
  not boxes; "Next step" is a neutral status pill; document rows with icons; people rows with a
  status pill; an inset text box with a focus ring.
- **Journey.** The numbered circles became a segmented track with the count in mono; the
  eyebrow "Step N of M" is gone; the check result sits in an inset with a status icon.
- **Security Lab.** The card grid became a flat list with a selected row and the detail on the
  right; the shared-element transition carries the title into the detail.
- **Insights.** A metrics strip from the measured runs; charts in accent (CPU) against text-2
  (GPU) with a dense tooltip; Reduce motion is a switch.
- **Animations.** Text glyphs became line marks (ring, check, cross); characters, the capsule
  and the lock are neutral; curves use the Quiet glass ease-out.

## Checks

| Check | Result |
| --- | --- |
| `scripts/craft_check.py` (gradient text, glow, colored shadows, nested glass, blur above 24, more than 3 blurred layers, accent bars, eyebrows, colors outside Theme.qml, emoji, exclamation marks, em dashes) | 0 findings |
| `scripts/check_contrast.py` on composites (fills blended over the world, panel, bar and floating layer, blurred and dense, both themes; text 4.5:1, pills 4.5:1, white on accent and on bad-solid 4.5:1, marks 3:1) | 616 pairs, 0 failures; tightest 3.77:1 (dark accent on the dense top bar, needs 3:1) |
| Runtime blur budget (tests/test_m12_restyle.py) | 3 surfaces ask for blur with the inspector closed and with it open |
| All five destinations, both themes, inspector open | no QML warnings |
| `scripts/check_feature_map.py` | 40 of 40 rows |
| Test suite | all passed |
| `impeccable detect` 0.1.18 | ran, 0 findings, but it reads HTML, CSS and JSX, not QML: not evidence |

## Performance (this PC, 60 Hz screen, 1440 x 900, Stage with the inspector replaying BuildIndex, 16 s; an earlier check found Qt drawing on the Intel iGPU, not the RTX 4060)

| | Before | After |
| --- | --- | --- |
| GPU renderer | 60.0 fps, p95 16.87 ms, max 19.16 ms | 60.0 fps, p95 16.86 ms, max 19.35 ms |
| Software renderer, drawing time per frame | p95 1.16 ms, max 4.38 ms | p95 1.24 ms, max 4.80 ms |

Both were measured with the same script, which keeps a 1 px item turning so the window draws
every frame (see R25). Without it the new UI draws nothing while nothing moves: the old drifting
lights forced a redraw every frame, the still world does not.

## Not verified

- Nobody has clicked through the restyled window by hand; it was driven by scripts and checked
  in screenshots. Screen readers were not tried with the new components.
- Reduce transparency and touch were forced with environment variables, not with the Windows
  setting or a touch screen. 4K and a weak graphics chip were not tested again after the restyle.
- The Hastra pages were compared through Hastra's own screenshots; the live pages could not be
  opened (the local web server was not running).
