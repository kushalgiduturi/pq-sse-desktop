# Restyle plan: PQ-SSE Desktop in Hastra "Quiet glass"

Goal: the spatial window looks and feels like Hastra's "Quiet glass" (direction A):
crimson on near-black at night, cobalt on white by day, one calm glass panel per page,
flat content, hairlines, a floating bar and dock, no boxes inside boxes, no rainbow, no
glow. Structure and behavior stay: five destinations, Story bar, command palette, Step
Inspector, every animation driven by real events. The Python core, the protocol and the
bridge contracts do not change.

Source of truth: `C:\xampp\htdocs\Hastra\docs\spatial-ui\` and `assets\css\theme-spatial.css`
(read only). The audit of the current UI is `docs/design/restyle-audit.md`.

## 1. Token mapping (old `Theme.qml` to new)

| Old | New | Dark | Light |
| --- | --- | --- | --- |
| `roomTop`, `roomBottom` | `world`, `worldWash` | `#050505` to `#0b0c10`, radial vignette | pale cool white-blue ground, faint wash |
| `glassFill` | `fill2` (page panel) | `rgba(10,11,16,.64)` | `rgba(255,255,255,.74)` |
| `glassRaised` | `fill3` (bar, raised controls) | `rgba(18,20,27,.72)` | `rgba(255,255,255,.80)` |
| (none) | `fill1` (insets) | `rgba(9,10,14,.46)` | `rgba(15,23,42,.05)` |
| (none) | `fill4` (dock, dialogs, popovers) | `rgba(14,15,20,.86)` | `rgba(255,255,255,.92)` |
| (none) | `solid1` to `solid4` (no blur) | `.90`, `.94`, `rgba(20,22,29,.96)`, `rgba(16,17,23,.98)` | `rgba(241,244,248,.96)`, `rgba(250,251,253,.97)`, `rgba(255,255,255,.98)`, `#ffffff` |
| `glassStroke` | `edgeHi`, `edgeSide`, `edgeLo`, `hair`, `hairStrong` | `.14`, `.06`, `.03`; hair `.09`, strong `.16` (white) | `.95`, `.5` (white), `rgba(15,23,42,.06)`; hair `.10`, strong `.18` (slate) |
| (none) | `hover`, `press`, `rowHover` | white `.06`, `.10`, `.04` | slate `.05`, `.09`, `.035` |
| `textPrimary`, `textSecondary`, `textMuted` | `text`, `text2`, `text3`, `textDisabled` | `#fff`, `.76`, `.62`, `.5` (white) | `#000`, `#2b3442`, `#3d4756`, `#6b7484` |
| `accent`, `accentOn` | `accent`, `accentText`, `onAccent`, `ring` | `#e50914`, `#ff4655`, `#fff`, `#ff4655` | `#2563eb`, `#1e40af`, `#fff`, `#2563eb` |
| `ok`, `fail`, `warn` | `ok`, `bad`, `badSolid`, `warn`, `info` | `#4ade80`, `#ff6b76`, `#d42033`, `#fbbf24`, `#67e8f9` | `#166534`, `#a51d2d`, `#c62031`, `#92400e`, `#155e75` |
| `alice`, `bob`, `carol`, `cloud`, `attacker`, `roleColor()` | removed | characters are neutral: `text`, `text2`; the attacker uses `bad` | |
| `series1`, `series2` | `accent` (GPU), `text2` (CPU) | | |
| `shadow` | `shadow2`, `shadow3`, `shadow4`, `shadowAccent` | neutral black, Hastra offsets and blurs | slate `rgba(15,23,42,…)` |
| `caption`, `body`, `bodyLarge`, `title`, `headline`, `display` | `fsXs` 12, `fsSm` 13, `fsMd` 15, `fsLg` 18, `fsXl` 24, `fs2xl` 32, `fsDisplay` 30 to 42 | | |
| (none) | `lhBody` 1.55, `lhTight` 1.1, `trackDisplay` -0.025 em | | |
| `s4` to `s48` | `sp1` 4, `sp2` 8, `sp3` 12, `sp4` 16, `sp5` 20, `sp6` 24, `sp8` 32, `sp10` 40, `sp12` 48, `sp16` 64; `panelPad` 20 to 40; `pageMax` 1180; `barInset` 12; `barH` 56 | | |
| `rChip`, `rCard`, `rPanel`, `rDock` | `rPanel` 28, `rFloat` 24, `rCard` 16, `rCtl` 14, `rSm` 10, pill = height / 2 | | |
| `fast`, `base`, `slow`, `stage` | `dur1` 150, `dur2` 220, `dur3` 280, `dur4` 350 | | |
| `spring`, `damping`, `hoverSpring` | `easeOut` (Bezier .16,1,.3,1), `springOvershoot`, `pressOvershoot` | | |
| (none) | `blur2` 18, `blur3` 16, `blur4` 20 (0 in every fallback) | | |
| (none) | `glow` (pointer light), `tiltMax` 3 degrees | white `.07` | see decision R6 |
| (none) | `dim` | `rgba(3,4,7,.4)` | `rgba(15,23,42,.28)` |

## 2. Component map

| Current | New | Notes |
| --- | --- | --- |
| `Glass.qml` | `Surface.qml` with `depth: 1..4` | depth 1 never blurs; edge and shadow per depth; dense fill in fallbacks; never nested (enforced by the craft check) |
| `TaskCard.qml` | `Section.qml` | title row (lg) with a hairline under it, flat content, optional "More options"; not glass |
| `PButton.qml` | `Button.qml` with `kind: primary / secondary / ghost / danger` | pill, sentence case, press spring, loading keeps width |
| `Field.qml` | `Field.qml` | depth-1 inset, radius 14, 2 px ring |
| `Segmented.qml` | `Segmented.qml` | inset track, raised pill that slides with the spring |
| `Chip.qml` | `Pill.qml` (status only) | 12 percent tint, solid AA text, status: ok, warn, bad, info, neutral |
| `Pick.qml` | `Choice.qml` | a checkbox-like row or segmented choice, not a chip |
| (none) | `Metrics.qml` | strip of numbers with vertical hairlines |
| (none) | `Row.qml` | flat list row with a hairline and a 4 percent hover |
| `Sheet.qml` | `Dialog.qml` | depth 4, radius 28, dim backdrop, primary pill and quiet cancel |
| `CommandPalette.qml` | same file | depth-4 popover |
| (none) | `Toast.qml` | depth-4 pill |
| `Dock.qml` | same file | depth-4 tray, radius 24, selected dot, magnification, press spring, 3 degree tilt |
| `StoryBar.qml` | `TopBar.qml` | island 12 px from the edges, pill, depth 3: Story sentence, engine pill, theme toggle, palette button |
| `Avatar.qml` | `Figure.qml` | monochrome glyph: person outline (Alice, doctors), cloud outline (Cloud), no color per character |
| `Icon.qml` | `Icon.qml` | one line set: stroke 1.5 at 24 px, round caps and joins |
| `Lbl.qml` | `Txt.qml` with `kind` (display, xl, lg, md, sm, xs, mono) | font, size, line height and tracking from tokens |
| (none) | `World.qml` | depth-0 backdrop: ground, wash, and the Stage scene drawn large and calm |
| (none) | `PointerLight.qml` | faint glow following the pointer on the page panel only |
| (none) | `Empty.qml` | icon, one line, one action, centered, no box |

## 3. Milestones

1. **Audit and plan** (this file, `docs/design/restyle-audit.md`, `docs/design/restyle/before/`). Done.
2. **Style guide**: `python -m app --styleguide`, Hastra's style guide translated to QML,
   screenshots in dark and light next to the Hastra screenshots. **STOP for approval.**
3. **Restyle**, a commit after each, tests green:
   a. Theme and surfaces (`Theme.qml` replaced, `Surface`, `Txt`, fonts loaded).
   b. Shell: top bar, dock, command palette, dialogs, toast.
   c. Stage (world scene) and Step Inspector.
   d. Workspace. **STOP: screenshots in both themes at 1280 x 800 and 1920 x 1080.**
   e. Journey. f. Security Lab. g. Insights. h. Animations.
4. **Verify and package**: `scripts/craft_check.py`, contrast on composites, fallback
   screenshots (software, reduce transparency, reduce motion), feature map, smoke test of
   all five destinations in both themes, frame times before and after, rebuild with
   `build_release.ps1`, installer test, comparison note.

## 4. Decisions

- **R1 Fonts.** Hastra ships WOFF2, which Qt cannot load. `scripts/convert_fonts.py` converts
  them with fontTools (a build-time tool, not a runtime dependency) into
  `app/spatial/fonts/`: `Onest-Variable.ttf` (weight axis 100 to 900, latin subset) and
  `ShareTechMono-Regular.ttf`, with both OFL licenses. Only the latin subset is used, as the
  app is in English (the same choice Hastra makes for its UI pages).
- **R2 Style guide shows one theme at a time.** Tokens are one singleton, so a single
  window cannot show both themes at once without duplicating every component. The style
  guide has a theme switch (as Hastra's own does), and the screenshot script saves both
  themes and also a stitched dark and light pair side by side.
- **R3 Springs.** Qt Quick has no stiffness, damping and mass easing for `NumberAnimation`.
  The spring (280, 25, .8: one small overshoot, about 4 percent) is `Easing.OutBack` with
  overshoot 0.8 at 350 ms; the press spring (550, 15, 1.1: about 8 percent) is
  `Easing.OutBack` with overshoot 1.6 at 220 ms. Ease-out is a Bezier spline with
  (.16, 1, .3, 1). These match Hastra's sampled `linear()` curves at their peaks.
- **R4 The inspector and the blur budget.** The Step Inspector is a depth-4 drawer. When it
  is open, the dock stays but loses its blur (dense fill), so at most three blurred layers
  remain: top bar, page panel, inspector. Dialogs and the command palette never blur; they
  use the dense depth-4 fill over a dim backdrop.
- **R5 The world.** No temple scene. Depth 0 is a near-black ground (dark) or a pale cool
  ground (light) with a soft radial wash, plus the Stage scene drawn large and low
  contrast: three figures (Alice, the Cloud, the doctors) with thin connecting paths.
  It is static (ambient motion off) and gives the glass something real to sample.
- **R6 Pointer light in the light theme.** Hastra's token is a cobalt tint, but its
  DIRECTIONS.md and this brief both say the glow is neutral. Dark: white at 7 percent.
  Light: white at 55 percent, which brightens the slightly grey glass instead of tinting it.
- **R7 Characters.** One monochrome figure glyph per kind (person, cloud) and the name.
  Bob and Carol are told apart by name and position, never by color.
- **R8 Status vs accent.** The accent marks emphasis and the one thing to watch in an
  animation; `ok` and `bad` appear only for results (a check passed, an attack caught).
- **R9 Title bar.** The native Windows title bar stays and follows the theme through
  `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE)`; nothing else about the window frame changes.
- **R10 Reduce transparency.** Windows has a "Transparency effects" setting
  (`EnableTransparency` under `HKCU\...\Themes\Personalize`). When it is off, or the app's
  own "Reduce transparency" setting is on, blur is off and the dense fills are used, as in
  the software renderer.
- **R11 Touch.** When a touch screen is present (`QInputDevice` of type touch screen),
  controls grow to at least 44 px and pointer light and tilt are off.
- **R12 No 21st.dev, no generic glass references.** Hastra is the only reference for this task.
- **R13** During the style guide the tokens live in `app/spatial/qml/quiet/Q.qml` (singleton `Q`), next to the new components. In step 3a this file replaces `Theme.qml`, so there is still one token file; `craft_check.py` treats it as the only place allowed to hold color literals.
- **R14** The token for text on the accent is called `accentInk`, not `onAccent`: QML reads any name starting with `on` and a capital letter as a signal handler.
- **R15** Dialogs and toasts are depth 4 with a dense fill (no blur), so the blur budget stays at three layers (page panel, top bar, dock) whatever is open. The style guide's depth band uses dense fills for the same reason.
- **R16** Glass samples one blurred copy of the world (`Q.worldBlur`, 20 px) rather than blurring per surface: one blur pass per frame, and the per-depth blur values (18, 16, 20) collapse to that one value. Recorded as a deviation from Hastra, which blurs per surface in CSS.
