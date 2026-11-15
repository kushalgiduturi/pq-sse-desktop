# Spatial UI plan

Goal: replace the six flat tabs with a calm, spatial front end (depth, glass, a dock, one
focused object at a time), a task-based structure, real-event animations and a Step
Inspector. The protocol, the cryptography, the cloud API and `pqsse/` stay as they are.

Status: all milestones (0 to 8) are done. The feature map is fully ticked. What is still
open is listed under S16 and in `docs/design/accessibility.md` and `docs/design/handoff.md`.

## 1. Technology decision (Milestone 0)

**Decision: Qt Quick (QML) inside PySide6, with the Python core behind a small bridge.**
The fallback (Widgets plus QGraphicsScene) is not needed.

The spike is in `spike/quick/` (`Spike.qml`, `spike_main.py`): a room background with
moving light, a blurred glass panel, a floating dock with hover magnification, a depth
page transition (spring), and an encryption scramble that replays a real AES-256-GCM
call (real sizes and real ciphertext glyphs, the key never reaches QML).

Measured on this PC (RTX 4060 Laptop GPU, 60 Hz screen, window 1280 x 800, Qt 6.12),
8 seconds of encryption replay plus page transitions, every frame counted:

| Run | Renderer | fps | Frame time mean / p95 / p99 / max (ms) | Frames over 20 ms |
| --- | --- | --- | --- | --- |
| From source | GPU scene graph (Direct3D 11) | 60.0 | 16.67 / 17.34 / 17.80 / 19.06 | 0 of 474 |
| From source | `QT_QUICK_BACKEND=software` | 62.7 | 15.94 / 20.13 / 21.41 / 22.98 | 26 of 497 (5.2 %) |
| Built exe (PyInstaller) | GPU scene graph (Direct3D 11) | 59.9 | 16.71 / 17.89 / 18.88 / 34.88 | 3 of 472 |
| Built exe (PyInstaller) | `QT_QUICK_BACKEND=software` | 62.5 | 15.99 / 19.79 / 21.49 / 22.45 | 20 of 495 (4.0 %) |

What this shows and what it does not:

- The GPU run is locked to the screen (60 Hz), so 60 fps is the ceiling, not the limit.
- The software run is on a fast laptop CPU with a small scene. A slow PC with a 4K
  screen will be slower. Not measured: no such machine here.
- Blur, shadows and shaders do not exist in the software renderer. The spike detects it
  (`GraphicsInfo.api`) and draws flat tinted panels instead. The real UI does the same
  and also switches off ambient motion and parallax there.
- Packaging works: the built exe loaded QML, rendered and animated. The spike folder is
  224 MB because PyInstaller collects every QML module (Quick 3D, virtual keyboard and
  others). The real build must list the needed modules and drop the rest; the size
  change is reported in Milestone 8.

Screenshots: `docs/design/screens/m0-spike-encryption-gpu.png`, `m0-spike-software.png`.

Not embedded and not used at run time: any web view, Electron, React code. The web
design tools are used for references and mockups only.

## 2. Architecture

```
pqsse/                     unchanged (only read-only narrator hooks may be added, with tests)
app/session.py             unchanged controller (owner, receivers, cloud child process)
app/lesson.py, challenges  reused: the lesson steps and checks drive Journey
app/main.py                starts the spatial UI; --classic starts the old Widgets window

app/spatial/
  bridge.py                AppBridge(QObject): session state as properties, actions as slots,
                           results and friendly errors as signals. Work runs on TaskRunner
                           threads; signals cross to the GUI thread.
  events.py                EventLog: subscribes to the narrator bus, records every Event,
                           exposes them as a QAbstractListModel, replays from the record
  inspector.py             builds the four Step Inspector layers and the sub-step timeline
                           for an event kind (plain words, what moved, under the hood, why safe)
  models.py                list models: documents, groups, people, cloud log, attacks, steps
  settings.py              theme, motion, text scale, detail level, mode; reads the Windows
                           "Show animations" setting
  copy.py                  every user-facing string of the new UI, one place
  qml/
    Theme.qml              singleton: color, type, spacing, radius, elevation, blur, motion tokens
    Main.qml               room, Story bar, status chips, page host, dock, inspector, palette
    components/            Glass, Dock, StoryBar, Chip, PrimaryButton, TaskCard, Lens, Timeline...
    pages/                 Journey, Stage, Workspace, SecurityLab, Insights
    anim/                  one file per animation: Encrypt, KeyExchange, Sign, IndexBuild,
                           Search, Verify, Decrypt, Update, Revoke, Attack
```

Rules:

- QML never computes protocol facts. It shows what the bridge sends.
- Every animation takes a recorded event (or a group of them) as input. "Replay at slow
  speed" is shown whenever the real step was faster than the animation.
- Event facts are numbers, short strings and lists of strings only (the narrator bus
  already refuses bytes). The inspector text is built from those facts.
- Reduce motion: one flag in `Theme`. Every animation file has a static path (frames with
  fades and captions). It is on when the user sets it, when Windows "Show animations" is
  off, and by default on the software renderer.

## 3. Information architecture

Dock (bottom center, keys 1 to 5), command palette (Ctrl+K), Story bar and status chips
always visible, Step Inspector sliding in from the right.

1. **Journey**: the guided lesson as a path, challenges, resume and reset.
2. **Stage**: Alice, the Cloud, Bob and Carol in space; objects move between them; lens
   (Everyone, Alice sees, Bob sees, Cloud sees).
3. **Workspace**: role rail (Alice, Bob, Carol, Cloud); task cards with one primary action.
4. **Security Lab**: attack cards, the check that catches each, R versus RE side by side.
5. **Insights**: benchmarks, engine, backend, data and logs, settings, About.

## 4. Feature map (old location to new location)

Every row must be ticked at the end. A script (`scripts/check_feature_map.py`, Milestone 2)
reads this table and fails if a row has no new location.

| # | Feature today | Old location | New location | Done |
| --- | --- | --- | --- | --- |
| 1 | Create or unlock the owner (Setup) | Owner tab | Workspace > Alice > card "Alice's keys" | [x] |
| 2 | Pair owner with cloud (import key files) | Owner tab, Cloud tab | Workspace > Alice > "Alice's keys" > More options; Workspace > Cloud > Server | [x] |
| 3 | Create groups | Owner tab | Workspace > Alice > People and access | [x] |
| 4 | See and approve join requests, choose groups | Owner tab | Workspace > Alice > People and access | [x] |
| 5 | Add, edit, delete, import documents (.txt, .md, .pdf) | Owner tab | Workspace > Alice > Documents | [x] |
| 6 | Build index | Owner tab | Workspace > Alice > Documents (primary button "Lock and upload") | [x] |
| 7 | Publish state | Owner tab | Workspace > Alice > Publish | [x] |
| 8 | Group overview (epoch, version, entries, dirty) | Owner tab | Workspace > Alice > Publish (summary), Inspector layer 3 | [x] |
| 9 | Revoke with policy R or RE | Owner tab | Workspace > Alice > Revoke | [x] |
| 10 | Create or unlock a receiver | Receiver tab | Workspace > Bob / Carol > card "Keys" (plus "Add a person" in the rail) | [x] |
| 11 | Pair receiver, send join request, fetch mailbox | Receiver tab | Workspace > Bob / Carol > Join | [x] |
| 12 | Search a group | Receiver tab | Workspace > Bob / Carol > Search | [x] |
| 13 | Verification panel (8 checks) | Receiver tab | Workspace > Bob / Carol > Verify; Inspector on Verify | [x] |
| 14 | Open (decrypt) a result | Receiver tab | Workspace > Bob / Carol > Open | [x] |
| 15 | Start and stop the cloud, passphrase | Cloud tab | Workspace > Cloud > Server; status chip | [x] |
| 16 | Cloud request log | Cloud tab | Workspace > Cloud > Activity log | [x] |
| 17 | Cloud statistics and stored data peek | Cloud tab | Workspace > Cloud > What it stores; Stage lens "Cloud sees" | [x] |
| 18 | Attack Lab: 11 scenarios | Attack Lab tab | Security Lab > attack cards | [x] |
| 19 | Attack teaching (tries, caught by, without protection) | Attack Lab tab | Security Lab > attack detail; Inspector layer 4 | [x] |
| 20 | Collusion demo R versus RE | Attack Lab tab, lesson step 11 | Security Lab > "R versus RE" side by side | [x] |
| 21 | Benchmarks: run, charts, CSV export | Benchmarks tab | Insights > Benchmarks | [x] |
| 22 | Parameter set (ML-KEM, ML-DSA), cloud port, freshness window | Settings tab | Insights > Settings > Advanced | [x] |
| 23 | Engine mode (auto, CPU, GPU), GPU self-test, calibration | Settings tab | Insights > Engine | [x] |
| 24 | Text size, reduce motion | Settings tab | Insights > Settings > Appearance (plus theme) | [x] |
| 25 | Guided lesson: 13 steps, Do it for me, Let me try, Check my work, resume, reset | Learn tab | Journey | [x] |
| 26 | Challenges (7) | Learn tab | Journey > Challenges | [x] |
| 27 | Who sees what, "show a document as the cloud sees it" | Learn tab | Stage lens (Everyone, Alice, Bob, Cloud) | [x] |
| 28 | Narrator lines with "Tell me more" | Narrator dock | Story bar (current sentence), Inspector layer 1, session timeline | [x] |
| 29 | Data-flow diagram with packets | Narrator dock | Stage | [x] |
| 30 | Slow motion, pause, packet list | Narrator dock | Inspector controls (play, pause, step, speed, replay), sub-step list | [x] |
| 31 | Glossary (F1), glossary search, term tooltips | Help menu, tooltips | Ctrl+K palette, F1 glossary sheet, term chips in the Inspector | [x] |
| 32 | Welcome screen and tour | First start, Help menu | First start sheet; Journey step 0; palette "Take the tour" | [x] |
| 33 | Beginner and Expert mode | Toolbar | Insights > Settings; status chip; palette | [x] |
| 34 | Friendly three-part errors, Copy technical details | Footer of every tab | Error sheet on the card that failed, same three parts and copy button | [x] |
| 35 | About (version, backend, GPU, licenses) | Help menu | Insights > About | [x] |
| 36 | Open data folder, open log folder | Help menu | Insights > Data and logs; palette | [x] |
| 37 | Lesson practice area and "your own data" switch | Learn tab header | Journey header; status chip shows which data is active | [x] |
| 38 | Engine and backend line in the header | Header | Status chip (click opens Insights > Engine) | [x] |
| 39 | `--smoke-test`, `--gpu-selftest`, `--version`, `--cloud` | Command line | Unchanged | [x] |
| 40 | The whole old window | Default | `--classic` until you say it can go | [x] |

## 5. Milestones

0. Spike and decision. **Done.**
1. References (Mobbin, 21st.dev), tokens, Figma mockups of five screens, critique. **STOP.**
2. Shell and bridge: Main.qml, dock, palette, Story bar, settings, bridge, event stream, `--classic`.
3. Stage and Step Inspector; animations for encryption, key exchange, signing, search first.
4. Workspace. **STOP: you try the app.**
5. Journey and Security Lab.
6. Insights (benchmark charts with the dataviz palette).
7. Polish: reduce motion, accessibility review, text scaling, themes, software run, performance, copy pass, handoff.
8. Packaging: Qt Quick modules in the build, installer and smoke tests, sizes.

## 6. Decisions

- **S1 Qt Quick, not Widgets.** See section 1.
- **S2 One bridge object plus list models**, registered as context properties. No QML code
  imports Python modules by name, so the bridge can be tested without a window.
- **S3 The old window stays** behind `--classic`, with its tests, until you decide.
- **S4 Software renderer and no-GPU PCs**: flat panels, no blur, no ambient motion, no
  parallax, Reduce motion on by default. Detected at start, shown in Insights > Engine.
- **S5 Windows "Show animations"** is read through `SystemParametersInfo`
  (SPI_GETCLIENTAREAANIMATION). Off means Reduce motion on.
- **S6 Fonts**: Segoe UI Variable (present on Windows 11), fallback Segoe UI on Windows 10;
  Cascadia Mono, fallback Consolas, for Under the hood. No font files are shipped.
- **S7 Icons** are drawn in QML (shapes) or shipped as SVG in `app/assets/`. No icon font.
- **S8 Sound**: none. A setting may be added later; it is not in this plan's scope unless you ask.
- **S9 The Step Inspector text lives in Python** (`inspector.py`, `copy.py`) next to the
  narrator stories, so the tests can check every algorithm and attack without QML.
- **S10 QML modules to bundle**: QtQuick, QtQuick.Window, QtQuick.Effects, QtQuick.Controls
  (Basic style only), QtQuick.Layouts, QtQuick.Shapes, QtQuick.Particles. Everything else
  is excluded from the build.

- **S11 Blur only on the floating layer.** The Story bar, dock, inspector, palette and sheets
  sample one blurred half-size copy of the room. Content cards are a strong tint (86 %) with a
  rim and a cheap shadow. Reason: many cards are on screen at once, and text contrast must not
  depend on what is behind a card.
- **S12 One read-only hook in the core**: `narrator.scope(name)` labels the events a thread
  emits inside a block, and the Attack Lab runs inside `scope("practice")`. The Stage and the
  Story bar ignore practice-copy events, so a comparison on a throwaway copy does not look like
  Alice creating new keys. Nothing about what is emitted changed; covered by a test.
- **S13 The spatial window is the default.** `--classic` opens the old window. If Qt Quick or
  the QML files are missing (the current packaged build excludes them until milestone 8), the
  app opens the classic window by itself and writes that to the log.
- **S14 "Play the story for me" on the Stage and "Run this step for me" in Journey** call the
  existing lesson actions in the practice area. They are the same real operations as before.
- **S15 Measured after milestone 4** (`scripts/spatial_perf.py`, this PC, 1440 x 900, Stage
  with the inspector replaying BuildIndex): GPU renderer 60.0 fps, frame time mean 16.67 ms,
  p95 17.29 ms, max 18.05 ms (limits: 50 fps, p95 25 ms). Software renderer: motion is reduced
  automatically and frames are drawn on demand; drawing time per frame mean 0.87 ms, p95
  2.73 ms (limit 50 ms). Window created in 2.2 to 2.7 s including the Python imports.
- **S16 Still open after milestone 8**: Update and Revoke have no animation of their own (they
  reuse Encrypt and Key exchange); no shared-element transition; avatars are letters and the
  Canva illustrations were not made; 21 labels are still written in QML files instead of
  `copy.py`; the lens exists for the first doctor only; focus is not trapped in sheets; no
  screen reader or keyboard-only walk-through was done; text scales to 125 %, not 200 %.
- **S17 Packaging.** `build_windows.ps1` bundles the QML files and Qt Quick, removes the Qt
  modules the app does not import (3D, WebEngine, Multimedia, Charts QML, virtual keyboard and
  others), and runs `--ui-selftest` on the built exe with the graphics chip and with the
  software renderer. The test opens the real window, visits the five destinations, runs two
  real steps and requires zero QML warnings and drawn frames.

## 7. Risks

- Blur cost on weak integrated graphics. Mitigation: panels blur a small region, blur is
  switchable, and the performance script (Milestone 7) records a threshold.
- QML text that drifts from the code. Mitigation: all text in `copy.py`, facts only from events.
- Size of the installer grows with the QML modules. Measured and reported in Milestone 8.
- A full redesign can lose a small feature. Mitigation: the feature map and its check script.