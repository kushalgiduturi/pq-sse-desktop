# Restyle audit: current spatial UI against Hastra "Quiet glass"

Reference: `C:\xampp\htdocs\Hastra\docs\spatial-ui\DESIGN.md`, `DIRECTIONS.md` (direction A),
`COMPONENTS.md`, `assets\css\theme-spatial.css`. Reference screenshots are in
`docs\design\hastra-reference\`; screenshots of the current app are in
`docs\design\restyle\before\` (prefix `dark-` and `light-`).

Each row is one place where the current UI breaks a Hastra rule, and the fix.

## World and depth

| # | Where (file) | What breaks the rule | Rule | Fix |
| --- | --- | --- | --- | --- |
| 1 | `Main.qml` room | Navy to blue vertical gradient, light theme pale blue gradient | 4: the world stays quiet; no gradient showpiece | Near-black `#050505` to `#0b0c10` with a soft radial vignette (dark); pale cool white-blue ground with a faint wash (light) |
| 2 | `Main.qml` ambient lights | Three large colored circles (accent, Carol violet, Bob cyan) drifting and following the pointer | Craft floor: no glow, no animated gradients; ambient motion off | Removed. The Stage scene becomes the world (row 3) |
| 3 | Backdrop has no content | Blur samples only a gradient, so the glass reads as a tinted box | 4: glass needs something real behind it | The Stage scene (Alice, Cloud, doctors) drawn large, calm and low contrast at depth 0 behind every page |
| 4 | `Glass.qml` | Content glass is a translucent tint with a full 1 px border in `glassStroke` | 3: depth from fill, edge and shadow; one specular top edge, not an outline | Specular edge: bright top line, dim sides, dimmer bottom; no outline |
| 5 | `Glass.qml` shadow | Shadow rectangle offset 8 to 14 px with layer blur, same for every depth | 3: shadow grows with depth, neutral only | Shadow per depth (2, 3, 4) from the Hastra values, neutral black (dark) or slate (light) |
| 6 | `Glass.qml` fills | One fill at 72 or 86 percent for all floating or content layers | Depth stack 1 to 4 | Fills `fill1` to `fill4` and dense `solid1` to `solid4` from Hastra, per theme |
| 7 | Blur radius | Room copy blurred with `blurMax: 48` | Blur never above 24 | Blur 18 (panel), 16 (bar), 20 (dock, dialogs, popovers) |
| 8 | Blurred layers | Story bar, dock, inspector, palette and sheet can all be blurred at once (up to 5) | At most three blurred layers | Bar, panel, dock blur; inspector becomes a section inside the page panel or a depth-4 drawer that replaces the dock blur; dialogs dim without blur |
| 9 | `Main.qml` dialog scrim | Scrim is a tint of `roomTop` | Dim only, no blur, Hastra dim value | `dim` token: `rgba(3,4,7,.4)` dark, `rgba(15,23,42,.28)` light |

## Boxes inside boxes

| # | Where | What breaks the rule | Fix |
| --- | --- | --- | --- |
| 10 | Every page: `TaskCard` is a `Glass` | Each card is its own panel; pages are grids of equal glass cards | One depth-2 panel per page; a card becomes a section: title row (lg, hairline under it) and flat content |
| 11 | `PageWorkspace.qml` | Role rail is a separate glass panel next to card glass | Rail becomes a flat list on the left side of the one panel, separated by a vertical hairline |
| 12 | `PageWorkspace.qml` document rows | Each document is a bordered rounded rectangle inside a card | Flat rows with a hairline and a 4 percent hover tint |
| 13 | `PageStage.qml` zones | Alice, Cloud and each doctor are separate glass panels; documents inside are bordered boxes | Zones are drawn into the world (row 3) as calm figures with labels; what each party holds is a flat list in the page panel |
| 14 | `PageStage.qml` bottom bar | Session timeline in its own glass panel | Timeline is a flat strip at the bottom of the panel, under a hairline |
| 15 | `PageJourney.qml` | Path in its own glass, focus card in glass, side cards in glass | One panel: title, the path as a flat stepper, the current step as the main section, challenges as a flat list below a hairline |
| 16 | `PageLab.qml` | Grid of eleven equal attack cards, detail in another card, comparison in another card | Flat list of attacks with a selected row on the left, detail on the right of the same panel, R versus RE as two columns separated by a vertical hairline |
| 17 | `PageInsights.qml` | Cards in a two-column grid | One panel with sections: measurements, engine, appearance, advanced, data and logs, about |
| 18 | `Inspector.qml` | Animation in a bordered box inside the inspector glass | Animation area is a depth-1 inset well, the only inset in the inspector |

## Color

| # | Where | What breaks the rule | Fix |
| --- | --- | --- | --- |
| 19 | `Theme.qml` role colors | Alice amber, Bob cyan, Carol violet, Cloud grey; used for avatars, rims, packets, timeline dots | Characters by name, a monochrome avatar glyph and position. One accent for emphasis, status colors only for status |
| 20 | `Theme.roleColor` callers | `Avatar`, `Stage` zone rims, packets, `SessionTimeline` dots, `AnimMove`, `AnimKem`, `AnimSearch`, `AnimSign`, `Inspector` header | Neutral text colors; the accent marks the one thing to watch |
| 21 | Accent | `#6C9BFF` (dark) and `#1F5FD6` (light) | Crimson `#e50914` with accent text `#ff4655` (dark); cobalt `#2563eb` with accent text `#1e40af` (light) |
| 22 | Status colors | `ok #4ADE80`, `fail #FF7A7A`, `warn #FFC857`, plus a separate `attacker` pink | Hastra status set: ok, warn, bad, bad-solid, info, per theme; the attacker uses `bad` |
| 23 | `Theme.series1/2` chart colors | Blue and orange | Accent versus `text-2`, with labels so it reads without color |
| 24 | Text colors | `#FFFFFF`, `#C9D6EA`, `#9DB0CC` (dark); blue-grey tints | Hastra text, text-2, text-3, disabled, per theme |
| 25 | `AnimEncrypt.qml` padlock | Amber `warn` padlock | Neutral text color; the accent only on the letter being locked |

## Chips, glow and decoration

| # | Where | What breaks the rule | Fix |
| --- | --- | --- | --- |
| 26 | `Chip.qml` everywhere | Chips for engine, cloud, mode, practice area, palette, counts, group names, AES tags, KEM tags, result lines | Pills only for real status (ok, warn, failed, CPU, GPU). Counts become a metrics strip; tags become plain text in the step list; the palette button becomes a ghost button |
| 27 | `StoryBar.qml` avatar disc | A colored disc with a letter before the sentence | A small monochrome glyph in `text-2`, or none |
| 28 | `Dock.qml` | Selected item is a filled accent rounded box; numbers in the corner | Selected dot under the item; no box; shortcut numbers only in tooltips and the accessible name |
| 29 | `Segmented.qml` | Track has a border; thumb is a solid accent fill | Depth-1 inset track; raised depth-3 pill in the fill color with the top-lit edge; label weight changes |
| 30 | `PButton.qml` | Secondary has a 1 px border; primary has no top highlight; hover scale 1.03 | Primary: solid accent pill with a top highlight and the accent shadow; secondary: glass pill; ghost: text; press spring |
| 31 | `Field.qml` | Tint of `roomTop`, 12 px radius, accent border on focus | Depth-1 inset, radius 14, inner shadow, 2 px `ring` focus ring |
| 32 | `TaskCard.qml` "next" | 2 px accent rim around a card | No colored rims. The next step is shown by its button being the one primary pill |
| 33 | `TaskCard.qml` caution | A warning sign glyph before the title | Plain title; the explanation sentence says it cannot be undone |
| 34 | Journey path | Green filled discs with check marks, accent ring for the current step, green links | Neutral discs with a check glyph; the current step is the accent; links are hairlines |
| 35 | `Icon.qml` | Mixed: filled shapes and strokes, 2 px stroke | One line icon set, stroke 1.5 at 24 px, round caps |
| 36 | Sheet scrim and palette | Palette is floating glass over a tinted scrim | Depth-4 popover, near-opaque, dim scrim |
| 37 | `AnimKem.qml` green rings | Green halo rings to show "same secret" | A neutral check mark next to each side and the word "same secret"; no rings |
| 38 | `AnimSearch.qml` | Matching cells glow green | Matching cells take the accent fill; others stay neutral |
| 39 | `AnimAttack.qml` | Pink attacker disc with "!" | Neutral figure glyph; the failing check uses `bad` |

## Type, radii, spacing, motion

| # | Where | What breaks the rule | Fix |
| --- | --- | --- | --- |
| 40 | Font | Segoe UI and Consolas | Onest (variable) for UI, Share Tech Mono only for ids, hashes, sizes and timestamps, both bundled |
| 41 | Type scale | 12, 14, 16, 20, 28, 36 | xs 12, sm 13, md 15 (body), lg 18 (section titles), xl 24, 2xl 32 (metrics), display 30 to 42 with -0.025 em tracking |
| 42 | Line height | 1.25 for all text | 1.55 body, 1.1 display |
| 43 | Radii | chip 12, card 20, panel 28, dock 30, buttons 14 | panel 28, float 24, card 16, control 14, small 10, pill (height / 2) |
| 44 | Spacing | 4, 8, 12, 16, 24, 32, 48 | 4, 8, 12, 16, 20, 24, 32, 40, 48, 64; panel padding 20 to 40; page max width 1180 |
| 45 | Durations | 120, 220, 360, 600 | 150, 220, 280, 350 |
| 46 | Curves | Ease-out cubic, `SpringAnimation` 3.2 / 0.36, hover spring 5 / 0.4 | Ease-out `cubic-bezier(.16,1,.3,1)`; spring with one small overshoot (stiffness 280, damping 25, mass .8); press spring (550, 15, 1.1) |
| 47 | Parallax | Pages and lights follow the pointer | Removed. Pointer light only on the page panel, 3 degree tilt only on dock items and destination links |
| 48 | Window title bar | Windows default (light in both themes) | DWM immersive dark mode attribute set from the theme |

## Copy

| # | Where | What breaks the rule | Fix |
| --- | --- | --- | --- |
| 49 | `copy.py` | "Search (Ctrl+K)" as a chip label, chip-style fragments | Short sentences, sentence case. Most copy already complies |
| 50 | `copy.py` | Several Title Case-ish fragments in chips ("Step Inspector (Ctrl+I)") | Sentence case: "Step inspector" |

## Counts

| Check | Now | Target |
| --- | --- | --- |
| Glass surfaces on the Workspace as Alice | 7 (rail, 5 cards, bar) plus dock | 3 (bar, panel, dock) |
| Blurred layers at worst | 5 (bar, dock, inspector, palette, sheet) | 3 |
| Distinct hues on one screen (Stage) | 9 (blue accent, amber, cyan, violet, grey, green, red, amber warn, pink) | 2 (accent plus one status when a status is shown) |
| Fonts | system Segoe UI, Consolas | Onest, Share Tech Mono (bundled) |
