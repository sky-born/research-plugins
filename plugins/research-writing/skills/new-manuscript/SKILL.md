---
name: new-manuscript
description: Creates a new paper or manuscript project in one go — the tools (number check, open-item tidy-up, record index, record-number assignment, location syntax, grammar baseline), the updater that brings an existing project's tools up to the canonical copy (update_tools.py), the Claude Code hook that stops completion records from being overwritten, the settings (.manuscript/project.json), the tracker file skeleton, and the shared CLAUDE.md with an AGENTS.md entry note for Codex. Use it for requests such as "start a new paper", "make me a project", "set up a paper folder" or "prepare a new manuscript". Never use it on an existing project.
---

# Creating a new manuscript project

`init_manuscript.py` turns one folder into a **ready-to-work state**.
The user should never have to create files by hand.

## Check first

**If the target folder already has `.manuscript/project.json` (older: `.writing/`) or a tracker index (`tracker_index.md`, or its old default name in `_config.LEGACY_DEFAULTS`), it is an existing project.**
Do not initialise it; say so. (The script skips existing files too, but checking first is better.)

## What to ask — only what you do not know

| Value | Default | Note |
|---|---|---|
| Folder location | — | **Always confirm.** Usually next to the sibling projects (the other manuscript projects in the same parent folder) |
| Paper title | — | `--name`. Any script, including Korean |
| Kind | `journal` | For a dissertation, `--kind dissertation` |
| Chapters | `ch1.md` `ch2.md` | `--chapters intro.md methods.md results.md` or `--chapter-count 4` |
| Manuscript folder | `manuscript_src` | Change it like `--source-dir manuscript` |
| References | `references.md` | `--references bib.md` |
| Build script | none | If you build with a university template, `--build-script build_tpl.py`. Follow [build-technical.md](../manuscript-workflow/references/build-technical.md) when writing the script |

**Keep the conversation short.** Even if the user only says "let's start the follow-up study",
confirm the folder location and the chapters and use the defaults for the rest.

## Running it

```text
python -X utf8 "<this skill folder>/init_manuscript.py" "<target folder>" --name "Paper title" --kind journal --source-dir manuscript --chapters intro.md methods.md results.md --references bib.md
```

`<this skill folder>` is **the parent folder of the `SKILL.md` you just read**. Check that `init_manuscript.py` and
`tools/` really are there. Do not guess where Claude or Codex installed it, and do not pick another version.
For `python`, use the Python 3 interpreter you confirmed in this environment
([checking the environment](../manuscript-workflow/references/environment.md)).

**Existing files are skipped.** Running it twice keeps their content. `--force` overwrites,
so use it only when the user explicitly asks to replace existing files.

## What it creates

```
<project>/
  CLAUDE.md                  §1 identity · §2 what to read for each task · §3 the single source of each record · §4 session start and end commands. §5 read-only sources and §6 domain limits are left blank
  writing_guide.md           chapter outline · this manuscript's writing rules (blank). Read only when writing, through the §2 table
  AGENTS.md                  entry note for Codex. Points it to CLAUDE.md and the shared procedure
  .manuscript/project.json   chapters · file names · triggers. The tools read it
  .claude/settings.json      Pre- and PostToolUse hook registration (Edit · Write · Bash · PowerShell) — refuses to overwrite completion records · refuses hand-registered open-item IDs · sync guard · snapshot after writing
  .claude/hooks/guard_write.py  the hook itself (copied from hooks/). The plugin's hooks/hooks.json registers the same script
  tools/                     the managed tools — the list is in project-config.md, "New projects are made by the `new-manuscript` skill"
  tracker_index.md           index (with the markers of its generated sections)
  tracker_pending.md         open-item tables — A · B · C · D by default (the project sets the letters)
  tracker_records_index.md   record index (empty)
  tracker_literature.md      tables F · G
  tracker_proposals.md       table H
  records/                   README.md (format rules) · archive.md
  <manuscript folder>/       chapter skeletons + references
```

## Always do after creating

**1) Check that the tools run.**

```text
python -X utf8 tools/check_numbers.py
python -X utf8 tools/tidy_tracker.py
python -X utf8 tools/check_sync.py
```

The third is the sync check of the shared files — the safeguard for a project used from several computers through a cloud-synced folder
(rules in [tracker-workflow.md](../manuscript-workflow/references/tracker-workflow.md) "Sync — several computers write the shared files"). Run it at the start of every session.

Warnings are normal in a new project — zero completion records,
uncited references (the skeleton's example entries). Exit code `1` from `tidy_tracker.py` means diagnostic warnings; check that they are
these empty-project warnings. Do not treat a missing file or a crash as the same warning.
Zero open items is a note, not a warning — with intact tables, the lists are rebuilt empty.

**2) Fill in the blank sections.**

§5 read-only sources and §6 domain limits in `CLAUDE.md`, and the chapter outline and writing rules in `writing_guide.md`,
still read `**Fill in**` (a Korean placeholder in projects made before 0.14). Ask the user and fill them in, or register them as open items if they cannot be filled now.
Rules needed for one task only go to a file that a row of the §2 table points to, not into `CLAUDE.md`.

**3) Decide whether the project needs its own skill.**

If many procedures belong to this paper alone, such as its build or where its source data is,
keep them in a procedure document inside the project, put its relative path in `procedure` in `.manuscript/project.json`,
and point the §2 table rows of the tasks that need it at it. How the document is reached and how a local skill is registered:
[project-config.md](../manuscript-workflow/references/project-config.md) "`markers` and `procedure` — two values the entry skill uses".

**4) Check the boundary with sibling projects.**

If the new project uses the same data as an existing one, write the scope of data use and the read-only boundary of the other
manuscripts into the new project's identity block. If a sibling project's guidance also needs changing,
confirm the user's instruction for that file and scope. Creating a new project gives no permission to edit sibling documents.

## Bringing an existing project's tools up to date — `update_tools.py`

Initialising is for new projects only. When an existing project's tools or hooks differ from the canonical copy (after a plugin update),
bring them up to date with `update_tools.py` in this folder.

```text
python -X utf8 "<this skill folder>/update_tools.py" "<project>"            # report only — same · older canonical version · locally modified · missing · old name
python -X utf8 "<this skill folder>/update_tools.py" "<project>" --apply    # replace older canonical versions and add missing required modules; locally modified: --force <file>, other missing: --add <file>
python -X utf8 "<this skill folder>/update_tools.py" --scan "<parent folder>"   # status table of all sibling projects
```

What it judges and replaces, what it never writes (the settings file), backups, 0.12-or-earlier names, the tracker format migration and the hook registration:
[project-config.md](../manuscript-workflow/references/project-config.md) "New projects are made by the `new-manuscript` skill".
A project whose tracker anchors still use the pre-0.14 Korean spellings is migrated in the same run (`migrate_format.py` — previewed
without `--apply`): [tracker-workflow.md](../manuscript-workflow/references/tracker-workflow.md) "Format tokens — English written, the old Korean spellings read".
To see beforehand what a release changes in sibling projects, use `scripts/preview_projects.py` in the repository.

## Shared rules

Style, hedging, citations and the revision protocol follow [manuscript-workflow](../manuscript-workflow/SKILL.md).
The `.manuscript/project.json` schema is in [project-config.md](../manuscript-workflow/references/project-config.md).
