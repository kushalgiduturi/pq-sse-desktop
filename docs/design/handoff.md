# Handoff spec: spatial UI

For whoever continues this code. Everything named here exists in `app/spatial/`.
Screens: `docs/design/screens/final-*.png` (dark) and `final-light-*.png`.

## Overview

One Qt Quick window on top of the unchanged `Session` and `pqsse/` core. QML shows state
and sends actions; Python does everything else. Start: `python -m app` (spatial),
`python -m app --classic` (old window).

| Layer | File | Job |
| --- | --- | --- |
| Bridge | `bridge.py` | State snapshot as properties, actions as slots on worker threads, errors as three-part maps |
| Event log | `events.py` | Narrator events to Step Inspector records, on the GUI thread |
| Inspector text | `inspector.py`, `copy.py` | Four layers, sub-steps, animation name per event kind and per attack |
| Text | `copy.py` | `T` (labels), `INSPECT`, `TRY`, `CHALLENGE_HINTS` |
| Tokens | `qml/Theme.qml` | Colors, type, spacing, radii, motion. Same values as the Figma variables |
| Window | `qml/Main.qml` | Room, Story bar, pages, dock, inspector, palette, sheets, shortcuts |

## Layout

- Window 1440 x 900 by default, minimum 1120 x 720. No breakpoints below that.
- Story bar: top, 16 from the edge, height 52 or more (two lines of text allowed).
- Dock: bottom center, 78 high at normal text size.
- Page area: between them, side margin 32. When the inspector is open the page area
  shrinks by the inspector width (36 % of the window, at most 500) plus 16; pages reflow.
- Cards: two columns when the page area is wider than 880, otherwise one.

## Tokens (all in `Theme.qml`)

| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `roomTop`, `roomBottom` | #0E1626, #2A4368 | #EAF0FA, #C9D8F0 | Background gradient |
| `glassFill`, `glassRaised`, `glassStroke` | #22304A, #2C3D5C, #5E7397 | #FFFFFF, #F4F7FC, #B7C4DA | Panels, inner controls, rims |
| `textPrimary`, `textSecondary`, `textMuted` | #FFFFFF, #C9D6EA, #9DB0CC | #101828, #344054, #52607A | Text |
| `accent`, `accentOn` | #6C9BFF, #07142B | #1F5FD6, #FFFFFF | Filled button, selection, focus |
| `alice`, `bob`, `carol`, `cloud` | #F2B544, #4CC9F0, #C792EA, #9AA9BD | #8A5A00, #0B6E8E, #7A3FB0, #4B5B73 | Characters (`Theme.roleColor(name)`) |
| `ok`, `fail`, `warn`, `attacker` | #4ADE80, #FF7A7A, #FFC857, #FF5C7A | #17703A, #B42318, #8A6500, #B4233F | Results, caution, Security Lab |
| `series1`, `series2` | #3987e5, #d95926 | #2a78d6, #eb6834 | Chart: CPU, GPU |
| `caption` .. `display` | 12, 14, 16, 20, 28, 36 px times the text scale (0.9, 1.0, 1.25) | | Type scale |
| `s4` .. `s48` | 4, 8, 12, 16, 24, 32, 48 | | Spacing |
| `rChip`, `rCard`, `rPanel`, `rDock` | 12, 20, 28, 30 | | Radii |
| `fast`, `base`, `slow`, `stage`, `stagger` | 120, 220, 360, 600, 40 ms | | Durations |
| `spring`, `damping` | 3.2, 0.36 | | Page and panel entrances (the signature curve) |
| `hoverSpring`, `hoverDamping` | 5.0, 0.4 | | Hover growth |

Fonts: Segoe UI Variable when installed, else Segoe UI; Cascadia Mono, else Consolas.
No font or image files are shipped; icons are drawn in `Icon.qml`.

## Components

| Component | Variants and properties | Notes |
| --- | --- | --- |
| `Glass` | `floating` (blur from the shared blurred room, soft shadow) or content (86 % tint, rim, cheap shadow); `rim`, `rimWidth`, `padding`, `radius` | Software renderer: flat tint, no blur, no shadow |
| `PButton` | `primary`, `danger`, `quiet`; disabled at 45 % opacity | 44 high (quiet: 35). At most one `primary` per card |
| `Chip` | `mark`: none, dot, ok, fail; `clickable`; `maxWidth` elides | The word carries the meaning |
| `Pick` | `selected` shows a check mark and a fill | Choice pills for groups, people, policies |
| `Segmented` | `labels`, `current`; arrow keys | Lens, detail level, theme, text size, mode, engine |
| `Field` | `hint`, `secret` | One line. The multi-line document text is a `TextEdit` in the Workspace |
| `TaskCard` | `title`, `summary`, `next` (accent rim), `caution` (warning mark), `hasMore` / `more` / `extra` | "More options" holds the advanced controls |
| `Avatar` | `who`, `size` | Letter on a disc; the cloud is a rounded square |
| `Sheet` | `rows` of head and body, `technical` (copy button), `error`, `actionText`, `closeText` | Errors, glossary entries, welcome |
| `CommandPalette` | filters `app.paletteItems` | Groups: Go to, Work as, Do, Lesson step, Setting, Glossary |
| `Inspector` | `index` into the event log, or `override` record for an attack | Player: play, pause, back, next, replay, speed, scrubber |
| `SessionTimeline` | `current` | One mark per recorded event |
| `BarChart` | `rows`, `field`, `title` | One measure per chart, legend, value labels, hover tooltip |
| `Anim*` | `record`, `progress` 0 to 1 | Encrypt, Kem, Sign, Search, Verify, Move, Attack |

## States and interactions

| Element | State | Behavior |
| --- | --- | --- |
| Any button | Hover | Grows to 103 % with the hover spring (not with Reduce motion) |
| Any control | Keyboard focus | 2 px ring in `textPrimary` |
| Any action | Running | Story bar shows "Working: ..." with a turning mark; action buttons are disabled |
| Any action | Refused or failed | Error sheet: what happened, why it matters, what to do next, Copy technical details |
| Task card | Next step | Accent rim 2 px and the filled button |
| Dock item | Hover | 116 %, neighbours 105 % |
| Page change | | Outgoing page fades and scales to 94 % or 105 %; incoming springs to 100 % (360 ms fade) |
| Stage zone | An event from that party | Rim in the party's color for 2.2 s, other zones dim to 72 % |
| Stage packet | Event with a packet | Flies from source to destination in 1.2 s on an arc, stays 0.7 s, fades |
| Inspector | Opens | Slides in from the right in 360 ms; the page area narrows |
| Reduce motion | On | No movement, no springs, no ambient lights or parallax; fades stay; inspector steps by caption |

## Empty, loading and edge cases

- Nothing set up: each role's first card explains the first step and holds the only filled button.
- Stage with nothing: "Alice has not set up her keys yet", "The cloud is switched off",
  "No doctor has been added yet". "Play the story for me" builds it.
- Cloud stopped: animations that show ciphertext say they use sample bytes.
- Long titles and chips elide with "..."; long hex and paths wrap anywhere.
- More than three doctors: the Stage shows the first three; all are in the Workspace rail.
- More than 400 events: the oldest are dropped from the session timeline.
- Long operations (BuildIndex with many documents, benchmarks): run on worker threads, the window stays usable.

## Motion table for the teaching animations

Each takes a recorded event and a progress value from the inspector's player. The player
runs 1.7 s per sub-step at speed 1 (0.25x to 4x).

| Animation | Events | What the phases show |
| --- | --- | --- |
| Encrypt | build_index, update, reencrypt, decrypt (reversed), cloud_view | Letters flip to real ciphertext glyphs under the padlock; tags; index entries appear (one lane on the CPU, all at once on the GPU, decided from the real entry count); Alice's stamp |
| Kem | join.approved, join.capability, rekey, revoke, setup.receiver | Open lock (public key), sealed capsule flies, opens, matching green rings |
| Sign | setup.owner, join.request, publish | Stamp presses; magnifier checks; a changed copy fails |
| Search | tokengen, search | Word stays; slip flies; addressed cells glow; boxes return |
| Verify | verify, verify.failed, attack | Checks tick in order; the failing one shows a cross |
| Attack | Security Lab cards | Attacker reaches; item cracks; the real checks list; the one that caught it |
| Move | everything else | Sender, labeled packet, receiver, what is inside and who can read it |

## Known debt

- 21 labels are still written inside QML files instead of `copy.py`.
- Update and Revoke reuse Encrypt and Kem; they have no animation of their own
  (new unlinkable addresses, the key ring turning, R and RE side by side in motion).
- No shared-element transition when a card opens into its detail.
- Avatars are letters. The Canva illustrations were not made.
- See `accessibility.md` for the open accessibility items.
