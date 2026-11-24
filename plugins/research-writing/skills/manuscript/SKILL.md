---
name: manuscript
description: Entry point of a manuscript session. Decides which manuscript project the open folder is and hands over to that project's procedure; if the folder is not a manuscript project, it only explains how to set one up. Use it for requests such as "start working on the paper", "let's look at the manuscript" or "let's write the paper in this folder", and when a session starts in a manuscript folder.
---

# Entering manuscript work

**This skill is thin.** All it does is **decide and branch**. **Paper-specific procedures are not here** —
file names, folder layout, document templates, figure sources and domain constraints differ per project, so each project keeps its own.

It can be called from any folder. That is why **deciding comes first.**

## 0. Both apps use the same documents — confirm the base root first

- Claude Code and Codex use **this same document and the same shared reference documents**.
  The apps differ only in how they register skills and which tools they provide; manuscript rules are never copied per app.
- If the current folder is a working folder linked to manuscript sources, first confirm the base root from the **relative path and markers**
  that the project guidance names. Resolve every `project.json` · `markers` · `procedure` path from that root.
  If the path is ambiguous, do not search other drives by guessing.

## 1. Decide what this folder is — three cases

Read `.manuscript/project.json` in the base root, and check the project guidance for the project's identity and its reading guide
(§2 of a generated `CLAUDE.md`, "What to read for which task"; in older projects §2 has a Korean title, or a file map takes its place).
Read and check files with **the tools this environment provides**.

| Case | Condition | Next |
|---|---|---|
| **A. An initialised manuscript project** | `.manuscript/project.json` exists and **every** file in its non-empty `markers` list exists | §2 |
| **B. A manuscript project without the tracking system** | No `project.json`, but the folder's project guidance (`CLAUDE.md` or `AGENTS.md`) **states, through its identity and reading guide, that this is manuscript work** | §3 |
| **C. Not a manuscript project** | Neither | §4 |

- If `markers` exist but **any one is missing**, the session may have been opened in a subfolder.
  Go up to the root once and check again; if they are still missing, report that and **stop.**
- **Do not open files by guessing.** If you cannot decide, report what is missing.
  If the settings cannot be parsed or `markers` is empty, report it as a settings problem of the existing project.
  Never run the initialiser over it.

**Do not suggest turning B into A.** Some manuscripts need no tracker files or tools —
a revision that a few continuity notes cover is one. Suggest `new-manuscript` only when the user says
**open items are scattered and no longer manageable.**

## 2. A — an initialised manuscript project

The order is fixed. **Do not change it.**

| Order | What | Where | If missing |
|---|---|---|---|
| 1 | Project identity · reading guide · domain limits | The applicable `AGENTS.md` · `CLAUDE.md` and the shared documents they name | Do not assume guidance that is not there |
| 2 | That the paper's procedure document exists — **check only; do not read it here** | The file that `procedure` in `project.json` points to | Skip if the key is absent; if the named file is missing, report it |
| 3 | The open-item index | `tracker.index` in `project.json` | Skip if the key is absent; if the named file is missing, report it |

- **Open the procedure document by task, not at entry.** Open it — or only the part a task needs — when a row of the project guidance's
  reading guide points to it; a session whose tasks never need it never loads it. `procedure` is a path relative to the project root;
  how Claude and Codex reach a project-local skill is in [project-config.md](../manuscript-workflow/references/project-config.md)
  "`markers` and `procedure` — two values the entry skill uses".
  If the settings name a path and the file is missing, report it — never substitute a guessed version of a required protective procedure.
- **Read `tracker.index` in full every session.** If the settings do not name one, do not require the tracking system.
  If the named file is missing, report it, and do not edit open or confirmed items by guessing their state.

**From here on, this skill makes no decisions.** Follow the project guidance's reading guide — it says which document to open for each task,
the procedure document included. **If they conflict, the project wins.**

## 3. B — a manuscript project without the tracking system

**The folder's project guidance is the procedure.** If it has a table of working files, that table points to the hand-over documents —
read them first to restore the context, then follow the order they set.

**Do not suggest initialising, and do not pull in another project's procedure.**

## 4. C — not a manuscript project

**Do not run the manuscript procedure.** End in one of two ways.

- If the user wants to **start a new paper** → hand over to the `new-manuscript` skill. Confirm only the folder location
  and the chapter layout, and use the defaults for the rest.
- If the folder is simply not a manuscript folder → **say so and stop**, and tell the user which folder to open instead.

## In every case

**Check first that the files are current.** When the project folder is synced through the cloud, work done on another computer
may not have arrived yet. Look at **modification times**, not at the file list.
If the user says "this is already done", **assume the user remembers correctly and read the files again.**

The shared writing rules are in the `manuscript-workflow` skill — style, evidence grades and hedging, confirming citations,
proposing revisions and the user's confirmation, tracking open items, figure rules. **Before changing manuscript sentences and before
submitting a manuscript or a response letter, read [revision-protocol.md](../manuscript-workflow/references/revision-protocol.md).**

**Enter once per session.** Do not call this skill again in the same session.
