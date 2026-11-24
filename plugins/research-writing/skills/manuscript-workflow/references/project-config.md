# Manuscript project settings — `.manuscript/project.json`

<!-- toc -->
**Contents**

- What goes in
- `grammar` — the scope of the pre-submission grammar check
- `markers` and `procedure` — two values the entry skill uses
- What stays out of this file — boundaries
- Triggers differ per project
- New projects are made by the `new-manuscript` skill
<!-- /toc -->

The loader also reads the old path `.writing/`, but new projects are made with `.manuscript/`.

This file gathers in one place the values the tools use to adapt to a project.
**The number of chapters, the file names, the folder structure and the trigger values differ from project to project.**

Copy `templates/project.example.json` and change only the values.
`new-manuscript/tools/_config.py` is the loader that reads this file, and it is copied into the project's tools folder (`tools_dir`) at initialization.

## What goes in

| Key | Tool that uses it | If absent |
|---|---|---|
| `tools_dir` | Hook · `update_tools` · tool messages | `tools`. The folder (directly under the root) that holds the managed tools |
| `manuscript.source_dir` | Number check, build | `manuscript_src`, or the project root if absent |
| `manuscript.chapters` | Number check, build | `ch1.md` – `ch4.md` |
| `manuscript.references` | Number check | `references.md` |
| `manuscript.figure_dir` | The project's own build script (no managed tool reads it) | `fig_src`. The folder of figure sources |
| `manuscript.build_script` | Number check | `build_tpl.py`. **A project without it skips that check** |
| `tracker.*` | Open-item tidying and index | `tracker_index.md` · `tracker_pending.md` · `tracker_records_index.md` · `tracker_literature.md` · `tracker_proposals.md` · `records/` · `records/archive.md`. The five files (`index` · `pending` · `record_index` · `literature` · `proposals`) are paths relative to the root, so a subfolder (`tracking/tracker_index.md`) also works — tools and hooks look only at this value, and when you move them, change `markers` as well |
| `tracker.triggers` | Tidying tool | The common five — `now` · `when working on the section` · `user decision` · `when data is available` · `before final submission` (older projects list their Korean spellings, which count as the same triggers). A project adds values tied to its schedule. **A value not in the list triggers a warning** |
| `tracker.movable_prefixes` | Tidying tool · sync check (S7) | `["A","B","C","D"]`. The section letters of the pending file — the initial letter of a section title `## X.` and of a row ID. If you reduce the letters, the letters of old IDs stay in the list (`tracker-workflow.md` "Category letters of the open-item tables — set by the project") |
| `tracker.section_markers` | Location syntax (tidying · index · new-record check) | An empty list. A project's own section notation (a list of regular expressions) |
| `tracker.record_prefix` | New record · sync check | `E`. The letter that starts completion-record IDs (`E12`) |
| `tracker.index_size_limit_kb` | Tidying tool | `40`. Above this size of the index file the tool warns that its structure needs another look |
| `tracker.record_index_exclude` | Record index | An empty list. Globs of files and folders to leave out of §1 of the record index (relative to the root; a folder ends with `/`) |
| `tracker.checkpoint` | Sync check | None. The handoff file (relative to the root) — it is snapshotted as a shared file, but because it is a document that gets overwritten, it is left out of loss reports |
| `sync.*` | Sync check · hook · tidying · index · new item · `update_tools` | All run on defaults. `shared_extra` (extra globs for shared files) · `snapshot_dir` (`archive/tracker_backup`) · `conflict_patterns` · `exclude` · `stale_days` (2) · `snapshot_days` (30) · `snapshot_days_others` (90) · `snapshot_min` (10) · `snapshot_max` (20) · `snapshot_max_local` (100) · `ack_hours` (4) · `known_gaps` · `rewrite_ok` · `survival_pct` (70). For their meaning see `tracker-workflow.md` "Sync — several computers write the shared files" |
| `manuscript.output_pattern` | Record index, initialization | None. A glob for build output names (`manuscript_v*.docx`) — left out of the record index |
| `grammar.*` | grammar_baseline | The scope is the `chapters` in `manuscript.source_dir` (the references file excluded). `sources` (sources **added** to the default scope) · `exclude_prefixes` (`["@NOTE"]`) · `avoid_lists` (none). See "`grammar` — the scope of the pre-submission grammar check" below |
| `markers` | Guard of the `manuscript` entry skill and of project-local skills | — |
| `procedure` | `manuscript` entry skill — checks that the file exists | **That check is skipped** |

**The tools run even without a settings file.** Defaults are built in.

**Projects made by 0.12 or earlier use the old default names, which are Korean — the values are in `_config.LEGACY_DEFAULTS`.**
If you write those names into the settings, they run as they are. If you do not, and only the old names exist on disk, the tools stop and the hook blocks writes except to the settings file,
and both show the values to add to the settings — `update_tools.py` shows the same values and does not apply anything until they are written.

## `grammar` — the scope of the pre-submission grammar check

`tools/grammar_baseline.py` reads it (for the rules, see `revision-protocol.md` "Pre-submission grammar check"). **If the key is absent, the scope is the chapter files in the manuscript folder** —
add with `sources` only English text that lies outside the chapter files, such as the abstract, text inside the build script, and short titles for the table of contents.

| Key | Value |
|---|---|
| `sources` | List of sources. For each item: `file` (a path **relative to the root**) · `kind` · (for lines) `regions` |
| `exclude_prefixes` | Initial strings of md blocks to leave out. Default `["@NOTE"]` |
| `avoid_lists` | Avoid lists (a list of paths relative to the root). If the first code span in the first cell of a table row is in a changed unit, it is flagged (case-insensitive) |

| `kind` | Unit |
|---|---|
| `md` (default) | One block separated by blank lines. A block that starts with one of the `exclude_prefixes` is left out — if a note is attached to a paragraph with no blank line, it is one unit with the paragraph |
| `lines` | One non-empty line inside a `regions` span. A span runs from the line that matches the `start` regular expression up to, and **not including**, the line that matches the `end` regular expression, searched from the next line on (the end line is not included). If there are several matches, all of them count |
| `json-values` | One string value (not the key). The values of keys that start with `_` are all description fields below it, so they are left out |

The fingerprint is the SHA-256 of the normalized text (NFC · LF line ends · leading and trailing whitespace stripped), and it does not include the file or the position — a unit that only changed order does not come up again.
**Unknown keys, unknown `kind` values, section markers that are not found, missing files and 0 units trigger a warning.** A key that starts with `_` is treated as a comment.
A file other than `.md` with no `kind` is read as md, with a warning.

## `markers` and `procedure` — two values the entry skill uses

The `manuscript` skill can be called from any folder, so **the guard comes first.**

- **`markers`** — the project counts as initialized only if **all** these files exist. If even one is missing,
  first check the base root and what is missing, and do not run initialization automatically on an existing project.
  Choose files that exist only in that project.
- **`procedure`** — the procedure document for that paper. It is a **path relative to the project root.**
  For a project-local skill, point at `.claude/skills/<name>/SKILL.md` or the like as it is, or write the path of the shared procedure
  document. **The entry skill only checks that the file exists; it does not read it.** The file is opened when a row of the project
  guidance's reading guide (§2 of a generated `CLAUDE.md`) points to it, for the task that needs it. A large procedure document works best as a short
  index whose numbered sections point to per-task files one level below it, so that each task reads only its own file.
  **Both Claude and Codex read that file directly**, and do not assume a skill of the same name has been registered automatically;
  where an app really has it registered, it may be called directly. If an app needs the local skill registered to call it, add only
  that app's project registration and **keep a single body** — never put it into the global plugin, where it could fire in other paper folders.
  **If the key is absent, proceed with the applicable project instructions and the tracker index.** If the file at the stated path is missing, report the omission and do not guess the required protection steps.

For a linked project where `AGENTS.md` names another manuscript source folder as the base root, first check the relative paths and markers in that instruction file, then read this setting in the target root. The tools also run from the target root.

**Do not put paper-specific procedures in the plugin.** File structure and constraints differ from paper to paper,
so only the entry logic is shared, and each project owns the content.

## What stays out of this file — boundaries

**`project.json` holds only values the tools read.** A value that no tool uses becomes a dead key that has to be
maintained in two places. The following differ from project to project, but **they do not go here.**

| What differs per project | Where it goes |
|---|---|
| The template (school-issued file, journal template) and the rule for finding it | The build script and that project's `CLAUDE.md` |
| The figure source folder and the figure-to-file table | That project's `CLAUDE.md`; the table goes in a separate `INDEX.md` |
| Read-only paths of raw experimental data and journal manuscript originals | That project's `CLAUDE.md`; if several projects share them, the parent `CLAUDE.md` |
| Domain limits of evidence, lists of what must not be cited | That project's `CLAUDE.md` — **do not raise them to the plugin or a parent level** |
| Per-task procedures (detecting the latest output, rebuilding, verifying) | That project's procedure document (`procedure`), opened through the reading guide |

**A manuscript project that does not use the tracking system does not need this file.** The `manuscript` entry skill
identifies it from the identity stated in the project instructions in that folder (`CLAUDE.md` · `AGENTS.md`) and the guide to the documents to read (a file map in older projects), and does not recommend initialization.

## Triggers differ per project

Each project writes its list in `tracker.triggers` (table above): the common five plus values tied to its own schedule —
a dissertation adds values such as `after the committee is set` and `after the graduation date is set`, a journal manuscript values such as `after the reviewers respond`.
The rule — why only values from the list may be used — is `tracker-workflow.md` "Triggers — a fixed set of values".

## New projects are made by the `new-manuscript` skill

**Do not make one by hand.** `init_manuscript.py` of the `new-manuscript` skill generates the managed files (the tools listed below · the hook), the settings,
the skeleton of the tracker files, the canonical `CLAUDE.md` and a thin Codex entry note `AGENTS.md` in one go.

```bash
python <plugin>/skills/new-manuscript/init_manuscript.py <target folder> --name "paper name"     --chapters intro.md results.md --references bib.md
```

**Files that already exist are skipped.** It is safe to run twice.

The canonical copy of the tools is in `skills/new-manuscript/tools/`, and at initialization it is **copied**
into each project's tools folder. The project then runs on its own and, if needed, can be modified only there.
The single source for the list of managed files is `new-manuscript/managed_files.json`. **When the canonical copy changes, bring each project copy in line
with `new-manuscript/update_tools.py`** — `--check` (judge) · `--apply` (replace — a locally modified copy needs `--force`, a missing file needs `--add`) ·
`--scan <folder>` (all sibling projects). The source is the plugin copy that holds the tool, and it recognizes old versions by the hashes in the canonical history (`tool_hashes.json`).
For Korean-named copies from 0.12 or earlier (`LEGACY_TOOL_NAMES` in `tools/_config.py`), `--apply` moves them to the new names.
A project whose tracker anchors still use the Korean spellings from before 0.14 is migrated in the same run (`new-manuscript/migrate_format.py`):
`--check` previews it, and `--apply` rewrites the anchors once every tool copy is current, then rebuilds the generated files.
A locally modified file is backed up to `.manuscript/tools_backup/<date>/` before it is replaced. The settings file is never written —
keys that rely on defaults are only reported, so show the needed values to the user and write them with Edit. The hook registration
(`.claude/settings.json`) is only compared; if it differs, merge the `hooks` block of `hooks/settings.example.json` by hand.
The command lines are in the `new-manuscript` skill, "Bringing an existing project's tools up to date".

```
tools/_config.py            settings loader · shared definitions (figure markers · status vocabulary) — use as is
tools/_location.py          "file · section" location syntax — used together by the index · location table · focus · new-record check
tools/check_numbers.py      Full cross-check of Figure · Table · reference numbers — after finishing each chapter
tools/tidy_tracker.py       Archives open items · builds the index
tools/index_records.py      Builds the reverse index of completion records — after editing a completion record (`--check-targets` reports names in old records that could not be verified)
tools/new_record.py         Assigns completion record numbers · checks the target · rebuilds the index (`--no-index` turns this off)
tools/new_pending.py        Assigns new open-item numbers — the pending letter tables · the proposal table (re-read inside the write lock to decide)
tools/_sync.py              Core of the shared-file sync guard — check · snapshot · write lock · `replace_once`
tools/check_sync.py         Session-start check · `--ack` · `--restore` · `--snapshots`
tools/grammar_baseline.py   Baseline for the pre-submission grammar check — picks out changed units (changed) · records units seen (clean · resolve) · checks candidate wording against the source (verify)
```
