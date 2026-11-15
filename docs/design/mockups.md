# Design brief and mockups (Milestone 1)

Figma file: https://www.figma.com/design/1ITGajzn7VbHwqhlO5c91G (page "Mockups (dark)").
Five frames at 1440 x 900, built from editable layers, colors bound to the token variables.

| # | Frame | Picture | What it shows |
| --- | --- | --- | --- |
| 1 | Journey | `mockups/1-journey.png` | Path of 13 steps with done, current and coming states; one focused step card with one primary button; challenges and reset as quiet side cards. |
| 2 | Stage | `mockups/2-stage.png` | Alice left, the Cloud in the middle behind frosted glass showing only scrambled bytes, Bob and Carol right; a locked box travelling; lens control; session timeline; inspector hint. |
| 3 | Workspace as Alice | `mockups/3-workspace-alice.png` | Role rail; four task cards (Documents, People and access, Publish, Revoke); only the next sensible step has the filled button; "More options" on each card. |
| 4 | Step Inspector on Search | `mockups/4-step-inspector-search.png` | Inspector docked right: four detail levels, the animation of this step, numbered sub-steps, playback controls, scrubber, metaphor label. |
| 5 | Security Lab | `mockups/5-security-lab.png` | Attack cards that name the check that catches each; R versus RE side by side with the honest limit in words. |

The pictures of frames 1, 3, 4 and 5 were saved before the critique fix below (their
background lights are stronger than in the Figma file now). Picture 2 is after the fix.

Limits of these mockups, stated plainly:

- Figma has no Segoe UI on this account, so the frames use **Inter** as a stand-in. The app
  will use Segoe UI Variable (Windows 11) or Segoe UI (Windows 10).
- Dock tiles show the shortcut number where the icon will be. Icons and the three avatars
  are not designed yet (planned with Canva and SVG in Milestone 5).
- Only the dark theme is drawn. The light theme exists as tokens, not as frames.
- No Insights frame, no command palette frame, no error state, no empty state yet.
- A mockup cannot show motion. The spike (`spike/quick/`) shows the real glass, the dock
  hover, the depth transition and the encryption replay.

## Tokens

In Figma as variables, and to be copied one to one into `app/spatial/qml/Theme.qml`.

**Color** (collections "Color / Dark" and "Color / Light", 18 each). Figma's free plan
allows one mode per collection, so the two themes are two collections with the same names.

| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| room/top, room/bottom | #0E1626, #2A4368 | #EAF0FA, #C9D8F0 | Background gradient |
| glass/fill, glass/raised, glass/stroke | #22304A, #2C3D5C, #5E7397 | #FFFFFF, #F4F7FC, #B7C4DA | Panels, chips and inner cards, 1 px rim |
| text/primary, secondary, muted | #FFFFFF, #C9D6EA, #9DB0CC | #101828, #344054, #52607A | Text |
| accent/primary, accent/on | #6C9BFF, #07142B | #1F5FD6, #FFFFFF | Primary button, selection, focus ring |
| role/alice, bob, carol, cloud | #F2B544, #4CC9F0, #C792EA, #9AA9BD | #8A5A00, #0B6E8E, #7A3FB0, #4B5B73 | One color per character, always with name or initial |
| state/ok, fail, warn | #4ADE80, #FF7A7A, #FFC857 | #17703A, #B42318, #8A6500 | Results, always with an icon and a word |
| attacker | #FF5C7A | #B4233F | Security Lab |

**Scale** (collection "Scale", 26 values): space 4, 8, 12, 16, 24, 32, 48; radius chip 12,
card 20, panel 28, dock 30; blur chip 16, panel 48; elevation content 18, floating 36;
type caption 12, body 14, body large 16, title 20, headline 28, display 36.

**Motion**: fast 120 ms, base 220 ms, slow 360 ms, stage 600 ms, stagger 40 ms.
Curves: ease-out cubic for fades and moves; one spring (spring 3.2, damping 0.36) for
page and panel entrances, the signature curve; a stiffer spring (5, 0.4) for hover.
Educational animations may run longer than 600 ms and can always be skipped.

**Depth layers**: background (room, lights), content (pages, cards), floating (Story bar,
dock, inspector, palette, popovers). Floating panels have the larger shadow.

## Design critique of the mockups

Context: desktop teaching app, audience includes people new to cryptography, stage: first
mockups before any real build. Reviewed from the five frame screenshots.

### Overall impression

The structure reads at a glance: one sentence at the top says what is happening, one
panel is in focus, one button is filled. The largest risk was the background: the
colored lights were strong enough to tint panels and compete with content.

### Usability

| Finding | Severity | Recommendation |
| --- | --- | --- |
| Dock tiles show numbers, not pictures. A number does not say "Stage". | Moderate | Real icons plus the label; keep the number as a small shortcut hint. Milestone 2. |
| Stage: the travelling box and its caption sit in the narrow gap between Alice and the Cloud and the caption collides with the Cloud panel. | Moderate | Give the lane between zones a fixed width (at least 160) and put captions under the lane, never over a panel. Milestone 3. |
| Stage: Bob's and Carol's panels are mostly empty while Alice's is full. | Minor | Size zones to their content; an empty person gets a compact card with one action ("Invite Carol"). |
| Workspace: "More options" looks like plain text, not a control. | Moderate | Make it a quiet button with a chevron and a focus ring. |
| Inspector: four tabs in 400 px are tight ("Under the hood" touches its neighbours). | Moderate | Widen the inspector to 480, or use short labels with the long name in a tooltip: Words, Moved, Hood, Why. Decide in Milestone 3 with real text scaling. |
| Journey: step labels under the path are 12 px and 13 of them is a lot to scan. | Minor | Show labels for done, current and next only; the rest on hover and focus. |
| Security Lab: only 6 of 11 attacks visible, the rest behind a text link. | Minor | Scroll the grid; the count stays visible ("11 attacks"). |
| No empty, loading or error state is drawn. | Moderate | Add them to the handoff spec before Milestone 4; errors reuse the three-part text. |

### Visual hierarchy

- **What draws the eye first**: before the fix, the cyan and violet lights. After it, the
  focused card and its filled button, which is correct.
- **Reading flow**: Story bar, page title, focus card, side cards, dock. Good on Journey
  and Workspace. On Stage the eye has no single start; the active zone should be brighter
  and the others dimmed while a step plays.
- **Emphasis**: one filled button per screen holds. The Revoke card needs a visible
  caution mark, since it is the one action that cannot be undone.

### Consistency

| Element | Issue | Recommendation |
| --- | --- | --- |
| Ambient light strength | Frames 1 and 2 used 22 % opacity, frames 3 to 5 12 % | **Fixed in Figma**: all at 10 % with a wider blur. |
| Glass opacity | 72 % let the background change the panel color from place to place | **Fixed in Figma**: 86 % for content panels. The app uses blur plus a tint of the same strength. |
| Chip sizes | Width is estimated from text length, some chips are loose | In QML chips size to their text; padding 12, height 30. |
| Buttons | Secondary buttons differ in width for no reason | Minimum width 120; same height 44 everywhere. |

### Accessibility

- **Contrast (calculated for the solid token colors, dark theme)**: text/primary on
  glass/fill about 13:1, text/secondary about 9:1, text/muted about 5.9:1, accent/on on
  accent/primary about 6.7:1. All pass WCAG AA for normal text. On translucent glass the
  real value depends on what is behind; the fix above keeps the tint strong enough, and
  the performance and contrast check in Milestone 7 must measure it on real screenshots.
- **Light theme**: token values were chosen for AA on white but are not drawn or measured yet.
- **Meaning by color alone**: role colors always come with a name or initial; results carry
  a word ("Caught by", "Safe", "Not safe for old data"). The done steps on the Journey path
  say "OK". The session timeline dots on Stage rely on color: add a check mark shape.
- **Targets**: buttons 44 high. Dock tiles 36: enlarge the hit area to the whole 92 x 60 cell.
- **Text size**: 12 px is used for labels and notes. With the "large" text setting everything
  scales; nothing below 12 at normal size.

### What works well

- The Story bar: one plain sentence, with the actor's color, answers "what is happening".
- The Cloud panel shows only bytes and counts. The main lesson is visible without reading.
- Honest limits are on the screen, in words: the R versus RE panel, the "Simplification"
  line on Journey, "Picture: ... is a metaphor" in the inspector and on Stage.
- One filled button per screen.

### Priority recommendations

1. **Real icons and avatars** for the dock and the four characters, before the shell is built.
2. **Stage layout rules**: fixed lanes between zones, captions under lanes, the active zone
   lit and the others dimmed during a step.
3. **Inspector width and tab labels** decided with the large text setting switched on.

## Tools used for this milestone

| Tool | Used | What it produced |
| --- | --- | --- |
| Mobbin | No: refused, the connector needs a paid plan | Nothing |
| 21st.dev | Yes | 16 references in `references.md` |
| Figma | Yes | New file, 62 token variables, 5 mockup frames |
| `design:design-critique` | Yes | The critique above, two fixes applied in Figma |
| Canva, `frontend-design`, `design:design-system`, `design:ux-copy`, `design:accessibility-review`, `design:design-handoff`, `dataviz` | Not yet | Planned for Milestones 5 to 7 as the plan says |
