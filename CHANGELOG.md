# Changelog

User-facing changes to each plugin, newest first. Each released version gets a `### <version> — <date>` entry at the top of its plugin's section.
`python scripts/release.py check` stops when a raised version has no entry.

## research-writing

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

### 0.11.0 — 2026-11-24

- The default OA staging folder (`oa_staging`) is `_oa_inbox` instead of `_수신`. Without `oa_staging` in the settings, an existing `_수신` folder
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
