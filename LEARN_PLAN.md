# Learn Mode: plan

Goal: a beginner can open PQ-SSE Desktop, follow one story (Alice the hospital records
manager, doctors Bob and Carol, an untrusted rented Cloud) and understand each step while
the real system runs. No protocol, wire format or cloud API change.

## 1. Architecture

```
pqsse/narrator.py        typed event bus (Event, subscribe, emit) plus the story text for every
                         event kind: tag, plain line, "tell me more", technical name, under the hood.
                         No Qt. Owner and receiver code call narrator.emit(...) in one line each.
app/glossary.py          one dictionary of terms; term(key) returns linked rich text,
                         tip(widget, key) sets a hover tooltip; GlossaryDialog with search.
app/session.py           explain_full(exc) -> Friendly(what, why, next, technical);
                         explain(exc) stays and returns the "what" line. Lesson profile switch.
app/common.py            TabBase: story intro, three-part error footer, "Copy technical details",
                         "Show advanced" handling. Light shows a text label next to its color.
app/narrator_panel.py    right-hand dock: data-flow diagram on top, narrator lines below,
                         detail pane for "Tell me more".
app/flow.py              QGraphicsScene diagram with animated, clickable packets.
app/lesson.py            the 13 lesson steps (data + actions on the real session) and demo documents.
app/challenges.py        7 practice tasks checked from narrator events and session state.
app/tab_learn.py         "Learn" tab: guided lesson, "Who sees what", challenges.
app/party_view.py        three-column "What can each party see?" view.
app/welcome.py           welcome dialog and the skippable window tour.
app/main.py              toolbar Beginner/Expert toggle, Help menu, dock, font scale.
pqsse/attacklab.py       each Outcome names the check that caught the attack; teaching texts.
docs/START_HERE.md, docs/concepts.md, docs/cheatsheet.md, README section.
```

Event flow: `owner / receiver code -> narrator.emit(kind, who, **facts) -> bus ->`
`NarratorPanel (Qt signal to the GUI thread) -> narrator line + diagram packet + challenge check`.
Facts are counts, sizes, names and words the acting party already sees. Never key material.

## 2. Milestones

1. Glossary, tooltips, friendly three-part errors.
2. Narrator event bus, hooks in owner and receiver, tests for every event.
3. Beginner / Expert toggle, welcome dialog, tour.
4. Guided lesson engine, lesson profile, demo data, reset.
5. Data-flow diagram and "Who sees what" view.
6. Attack teaching and challenges.
7. Beginner docs and README section.
8. Accessibility pass, wording pass, final full test run.

Each milestone: full test suite, commit.

## 3. Decisions

- **L1 Lesson sandbox profile.** The guided lesson runs the real code paths (real cloud
  process over HTTP, real keys, real tabs) but in its own data folder
  `%LOCALAPPDATA%\PQ-SSE-Desktop\lesson`, with the fixed passphrase `lesson` for every role.
  Reason: the lesson must be able to open the roles for "Do it for me" and to reset to a
  clean state without touching (or needing the passphrases of) the user's own data.
  Entering the lesson switches the whole app to that profile; "Exit lesson" switches back.
- **L2 Step 4 and step 6.** In this implementation a document is encrypted and its index
  entries are created in one signed batch. So step 4 creates the groups and loads the demo
  documents on Alice's side, and step 6 runs BuildIndex (encrypt, index, upload) and Publish.
- **L3 Steps 7 and 8.** TokenGen, Search and Verify are one call in the code. Step 7 runs
  the search and focuses on what the cloud saw; step 8 runs it again and walks the checks.
- **L4 Step 10, forward privacy.** The lesson explains it and shows the entry counts; the
  measured proof lives in `tests/test_m2_protocol.py` and the lesson says so.
- **L5 Step 11.** The R versus RE comparison runs on a throwaway copy (the Attack Lab
  collusion scenario). The real lesson system then revokes Bob with policy R.
- **L6 Narrator events come from owner and receiver code.** The cloud is another process,
  so its side of Search is narrated from the receiver's view of the reply and from the
  cloud's request log.
- **L7 Default mode.** First real launch (`python -m app`) starts in Beginner Mode. A
  window built directly in code (the tests) defaults to Expert Mode, which is exactly the
  previous six-tab window, so the existing tests run unchanged. In Expert Mode the Learn
  tab is removed and the Narrator is optional (View menu).
- **L8 `explain` keeps its one-line answers** (existing tests compare them); the new
  `explain_full` adds "Why it matters" and "What to do next" under the same line.
- **L9 Tooltips cannot hold clickable links in Qt.** Tooltips end with "Press F1 for the
  glossary"; labels use real links that open the glossary at the term.
- **L10 No information by color alone.** Every light shows a word (OK, Failed, Not
  checked, Running, Stopped) and narrator tags are words in brackets.
- **L11 "Try it without protection" is text only.** It describes what a system without
  the check would return. No code path is weakened.

## 4. Risks

- Teaching text that drifts from the code. Mitigation: narrator facts come from the real
  operation, and a final pass reads every string against the implementation.
- The lesson depends on a child process. Mitigation: each step re-establishes what it
  needs (cloud running, roles open) before acting, so resume after restart works.
- More GUI surface. Mitigation: everything is callable without modal dialogs and is
  covered by the offscreen tests.
