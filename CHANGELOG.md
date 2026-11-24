# Changelog

User-facing changes to each plugin, newest first. Each released version gets a `### <version> — <date>` entry at the top of its plugin's section.
`python scripts/release.py check` stops when a raised version has no entry.

## research-writing

### 0.14.0 — 2026-11-25

- The format the tools write into a project is English — block markers (`<!-- location-table -->` · `<!-- now -->` · `<!-- archived-list:A -->` …),
  the generation stamp, column names (`Item` · `Location` · `Trigger` · `Status` · `Note` …), completion-record fields (`**Completed**` · `**Target**` · `**Status**`),
  status words (`applied (awaiting confirmation)` · `confirmed` · `closed` · `done` · `waiting` …), the `now` trigger, the focus line, the generated blocks
  and the record index. The Korean spellings of earlier versions are read forever; they are listed, with their meanings, in one legacy section of
  `tools/_config.py`, and `tracker-workflow.md` "Format tokens" describes the rules
- A project's format is read from its anchors (markers, stamps, `| ID |` header rows). The writing tools refuse a project whose anchors are still Korean
  or mixed (exit 5); diagnosis keeps working. The sync check gains S9 — mixed anchors are an ERROR, Korean ones an INFO
- `update_tools.py` migrates an existing project in the same run (`migrate_format.py`): without `--apply` it previews; with `--apply` it updates the tool
  copies, rewrites the marker lines, stamp lines and known column names, and rebuilds the generated files. Completion records, archive rows, status
  and trigger values, headings and `project.json` stay as written. Idempotent, under the write lock, with Drive snapshots before and after.
  It refuses while the sync check has an open ERROR other than S9, and a managed tool the project never installed does not block it
- English status words count only at the head of the cell; `needed` or `waiting` anywhere keeps an item open (`done (visual check needed)`)
- New projects get English templates and a shorter `CLAUDE.md` — §1 identity · §2 what to read for each task · §3 the single source of each record ·
  §4 the session start and end commands · §5 read-only sources · §6 domain limits. It leaves out the folder map and the full tool list, points to the
  `manuscript-workflow` reference table instead of copying it, and points to rules kept in the skills rather than repeating them. The chapter outline
  and the manuscript's own writing rules go to a new `writing_guide.md`, which is read only when writing. Existing projects keep their `CLAUDE.md`;
  it is written only when a project is created
- `grammar_baseline.py` writes English keys and the packet format `grammar-packet/2`; older baselines and packets are read
- The sync loss report (S6) leaves out anchor lines, so the migration does not raise it on other computers
- Location syntax: a plain word after a code file counts only as an item of a file list (after the file or `·` / `,`), so English remarks after a
  file are no longer read as section names, and a backticked `Class.method` is one identifier. A record index can change by a row on the next rebuild
- The longer reference documents (`tracker-workflow.md` · `revision-protocol.md` · `style-guide.md` · `project-config.md` · `environment.md`) open with a
  table of contents
- The `manuscript` and `manuscript-workflow` skills do not ask the agent to open `CLAUDE.md` · `AGENTS.md` again — the app loads
  them at the start, and a generated `AGENTS.md` already points Codex to `CLAUDE.md`
- The `manuscript` entry skill no longer reads the `procedure` document at the start of a session; it only checks that the file exists.
  The document is opened when a row of the project's reading guide (`CLAUDE.md` §2) points to it, for the task that needs it.
  A large procedure document works best as a short index that points to per-task files (`project-config.md`)
- Rules that were repeated across documents now live in one place, and the other documents point to it — local-skill registration, the tool
  list and how to use `update_tools.py` in `project-config.md`, the trigger rule in `tracker-workflow.md`
- Skill instructions, reference documents, tool messages and help are in English
- Reference documents have English section titles — notes in existing projects that cite a section by its Korean title should use
  the English one
- The plugin `README.md` is in English, with the Korean edition in `README.ko.md` beside it
- `index_records.py --check-targets` replaces the old Korean flag, which is still accepted; `tidy_tracker.py --focus` takes `off` or `none` to turn the focus off
- **Existing projects — in this order.** ① Update the plugin on every computer (`bootstrap.py update`) and reopen the sessions — an older tool that meets
  English anchors rebuilds the record index with empty fields and adds a Korean stamp, and S9 then reports the mix. ② Per project, preview with
  `update_tools.py <project>`, then run `--apply` once the user agrees — it replaces every managed tool and migrates the anchors together.
  ③ On the other computers, open the project after Drive has caught up and check S9 with `check_sync.py`. Until a project is migrated, write values
  in the spelling its files already use

### 0.13.1 — 2026-11-24

- `update_tools.py` — when a tool exists under both its new and its old name and the old copy was edited by hand, the old copy is kept; only `--force`
  removes it, after backing it up

### 0.13.0 — 2026-11-24

- Nine management tools have English file names — `_동기화.py` → `_sync.py` · `_위치.py` → `_location.py` · `동기화_점검.py` → `check_sync.py` ·
  `번호점검.py` → `check_numbers.py` · `문법기준.py` → `grammar_baseline.py` · `수정필요_정리.py` → `tidy_tracker.py` ·
  `완료기록_색인.py` → `index_records.py` · `완료기록_새항목.py` → `new_record.py` · `미결_새항목.py` → `new_pending.py`
- New projects get English default names — tools folder `tools/` (new setting `tools_dir`) · manuscript folder `manuscript_src/` · tracker files `tracker_*.md` ·
  records folder `records/` (migrated records `records/archive.md`) · snapshots `archive/tracker_backup/` · tool backups `.manuscript/tools_backup/` ·
  grammar baseline `.manuscript/grammar_baseline.jsonl` (packets `grammar_packets/`)
- Projects made by 0.12 or earlier — old (Korean) names written in the settings keep working. If they are not written and only the old names exist, the tools
  stop and the hook blocks every write except to the settings file; both show the values to add. `update_tools.py` shows the same values and does not apply
  until they are added; after that, `--apply` moves the old-name tool copies to the new names. A grammar baseline file that exists only under its old name is
  used as it is
- Names used by the tools, the hook and project setup are read from the defaults in `_config.py`
- Update every computer that uses the same project together — hooks from 0.12 or earlier cannot find the new-name tool copies and skip the check for
  hand-registered pending numbers

### 0.12.2 — 2026-11-24

- The README install line and the manifest's repository URL point to `sky-born/research-plugins`

### 0.12.1 — 2026-11-23

- Plugin `README.md` — one-line install, requirements (hooks on Windows need Git Bash), and a summary of the skills, hooks and project tools
- `plugin.json` has the keyword `scaffold`, which only the marketplace entry had

## paper-index

### 0.12.0 — 2026-11-25

- Skill instructions, the reference document, tool messages and help are in English
- What it writes to disk is English — `papers_index.md` (headings such as `## By topic` · `## Needs attention`, `year unknown`), the CSV header,
  tool-written notes, fallback journal names, the `untagged` tag, Scopus result files (`match_by` · `oa_note` · `## Per-entry abstracts`),
  the citation-check report and the `tags.auto.json` draft. The Korean values of earlier versions are read; they are listed, with their meanings,
  in `lib/legacy.py`
- The first `index` / `reindex` after updating rewrites the values earlier versions wrote into existing rows of `papers_index.json` — tags of the
  preset, the two tool notes and the fallback journal names, exact matches only — and keeps one copy of the old file in `<index_dir>/_backup/`.
  Hand-written notes, edited tags and titles stay as written. Old Scopus result files stay as they are.
  Update the plugin on every computer that shares the index first — an older version would add Korean tags to new rows (the next `reindex` converts them)
- A preset can rename its tags with `"renamed": {"<old name>": "<new name>"}`; the bundled `solder-thesis.json` uses it for its English tag names.
  `search --tag` finds a tag by its old or new name
- `scopus-tidy` moves old launcher files to `_scopus/_done/`; an existing older archive folder is still used. The download list an agent keeps is
  `download_requests.md`; an existing older list keeps being used
- The citation-check example config looks in `manuscript_src/`, the default manuscript folder of `research-writing`
- The plugin `README.md` and the citation-check `README.md` are in English, with Korean editions in `README.ko.md` beside them

### 0.11.0 — 2026-11-24

- The default OA staging folder (`oa_staging`) is `_oa_inbox` instead of `_수신` ("received"). Without `oa_staging` in the settings, an existing `_수신` folder
  is still used when it is the only one. A value written in the settings is always followed

### 0.10.2 — 2026-11-24

- The README install line and the manifest's repository URL point to `sky-born/research-plugins`

### 0.10.1 — 2026-11-23

- The preset `solder-thesis.json` is described as an example preset (tag rules unchanged)

### 0.10.0 — 2026-11-23

- Scopus is called through one implementation, `lib/scopus.py` — `scopus_search.ps1` and `make_launcher.py` (which built a double-click launcher) are removed.
  Where direct calls are blocked, run the same `papertool.py scopus` command in a terminal on a computer that has the key
- `scopus-merge` does not clean up launcher files. `--keep-launcher` is accepted and does nothing
- `scopus-tidy` remains for launcher files that 0.9 or earlier left in the index folder
- `README.md` uses the current name instead of `paper-index-tool` and has a one-line install
