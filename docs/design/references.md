# Design references

Collected for Milestone 1. These are references for look, spacing and motion only. No
code from them is used: they are React components and the app is Qt Quick.

## Tools

| Tool | Result |
| --- | --- |
| Mobbin | **Not available.** Every search was refused: the connector needs a paid Mobbin plan. No Mobbin reference was used, and the `mobbin:redesign-screen` skill was not run. |
| 21st.dev | Used (catalog search, metadata and previews only). The references below. |
| Figma | Used for tokens and mockups, see `docs/design/mockups.md`. |
| Canva | Not used yet. Planned for the avatars and the welcome illustration (Milestone 5). |

## References from 21st.dev (16)

| # | Reference | What to borrow |
| --- | --- | --- |
| 1 | [Glass Card, educalvolpz](https://21st.dev/@educalvolpz/components/glass-card) | The bright rim on the top edge and the highlight that follows the pointer: this is what makes a panel read as glass, not as a grey box. |
| 2 | [Liquid Glass, manuarora700](https://21st.dev/@manuarora700/components/liquid-glass) | A frosted fallback when refraction is not possible. Our software renderer path is exactly that fallback. |
| 3 | [Liquid Glass Card, designali-in](https://21st.dev/@designali-in/components/liquid-glass-card) | Generous inner padding (24 to 32) and a single line of secondary text under the title. |
| 4 | [Liquid Weather glass, uilayout.contact](https://21st.dev/@uilayout.contact/components/liquid-weather-glass) | Small glass chips sitting on a larger glass panel: two blur strengths, so layers stay distinct. Used for status chips. |
| 5 | [Floating Dock, manuarora700](https://21st.dev/@manuarora700/components/floating-dock) | Magnification of the hovered icon and softer growth of its neighbours. |
| 6 | [Mac-Style Floating Dock, themeocean](https://21st.dev/@themeocean/components/mac-style-floating-dock) | Dark glass dock with a fisheye curve. We keep labels always visible, because beginners should not guess icons. |
| 7 | [Dock, luv-jeri](https://21st.dev/@luv-jeri_c92deb60/components/dock) | A labelled vertical rail next to a dock: the model for the Workspace role rail. |
| 8 | [Animated Progress Stepper, shadcnspace](https://21st.dev/@shadcnspace/components/stepper-03) | Spring-animated progress line, pulsing active step, icon turning into a check. Model for the Journey path. |
| 9 | [Vertical Titled Stepper, sean0205](https://21st.dev/@sean0205/components/c-stepper-15) | Numbered vertical steps with title and a loading state. Model for the sub-step timeline in the Step Inspector. |
| 10 | [Stepper, originui](https://21st.dev/@originui/components/stepper) | Inline title plus one-line description per step, readable without color. |
| 11 | [Command Palette, rafa-porto](https://21st.dev/@rafa-porto/components/command-palette) | Raycast-like grouping: Actions, Pages, Content. Ours: Go to, Do, Glossary, Lesson steps, Settings. |
| 12 | [Command Palette, vovalopuh13](https://21st.dev/@vovalopuh13/components/command-palette) | Matched letters underlined, a preview pane, full keyboard model (arrows, Home, End, Enter, Esc). The preview pane shows the glossary meaning. |
| 13 | [Scramble Text, dqnamo](https://21st.dev/@dqnamo/components/scramble-text) | Character-by-character change with a reduced-motion fallback and a screen-reader text that holds the final value. |
| 14 | [Text Scramble, ibelick](https://21st.dev/@ibelick/components/text-scramble) | Left-to-right settling. We run it in the encrypt direction (readable to scrambled) and use real ciphertext glyphs, not random ones. |
| 15 | [Segmented Control, ddoemonn](https://21st.dev/@ddoemonn/components/segmented-control) | Sliding thumb with arrow-key navigation and radio-group semantics. Used for the lens and the inspector layers. |
| 16 | [Segmented Control, flohoeller](https://21st.dev/@flohoeller_5a53e102/components/segmented-control) | Icons plus labels in each segment, and a count badge. Used for the lens (icon of the viewer plus name). |

## Other references (general knowledge, not fetched)

- Apple visionOS design guidance: glass material, depth instead of borders, one window in
  focus, ornaments (our dock and inspector are ornaments).
- Windows 11 Mica and Acrylic: how blur behaves on Windows and when to fall back to a solid tint.

## What we deliberately do not borrow

- Icon-only docks. Every destination has a text label.
- Refraction and chromatic fringing. Expensive, and it hurts text contrast.
- Random scramble glyphs. Ours come from the real ciphertext of the real event.
