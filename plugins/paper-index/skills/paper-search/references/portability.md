# Environments, moving an existing index and verification

## Running the same source in each app

The skill text, `papertool.py`, `lib/` and the reference files are one shared source. Registration differs between a
Claude Code plugin and the Codex install procedure. Follow the instructions at the repository
root for installing and updating, and do not edit an installed copy or another app's cache directly.

1. Confirm the actual directory of this `SKILL.md` that the app reports.
2. Confirm that `papertool.py` and `lib/` are both in that directory.
3. Confirm the Python 3 to run and `pdftotext`. The Python command name, install paths, shell, network,
   environment variables and connected folders are facts of each computer and session. Use only what is installed.
4. Read the source and index paths and the search scope from the project's `AGENTS.md` or `CLAUDE.md`.
   Do not assume any file was loaded automatically. The app's higher-level instructions and the user's request take precedence.

PowerShell example (replace `<...>` with the confirmed paths):

```powershell
$PaperTool = Join-Path '<registered paper-search directory>' 'papertool.py'
$PaperConfig = '<confirmed paperindex.config.json>'
Get-Command python,python3,py,pdftotext -ErrorAction SilentlyContinue
python -X utf8 "$PaperTool" --help
python -X utf8 "$PaperTool" --config "$PaperConfig" doctor
python -X utf8 "$PaperTool" --config "$PaperConfig" search --depth quick 'keyword'
```

Bash example (when `python3` is confirmed to be Python 3):

```bash
TOOL='<registered paper-search directory>/papertool.py'
PAPER_CONFIG='<confirmed paperindex.config.json>'
command -v python3
command -v pdftotext
python3 -X utf8 "$TOOL" --help
python3 -X utf8 "$TOOL" --config "$PAPER_CONFIG" doctor
```

If `pdftotext` is not on PATH, the path of the installed executable can be set as `pdftotext` in the config.
Do not change arbitrary system settings because an interpreter was not found. The tool's `search` works from the existing
cache alone, but PDF extraction needs `pdftotext`. Do not mix the shells' `$variable` and line-continuation syntax.

## Moving an existing index

| Format | Files | Handling |
|---|---|---|
| Earlier Codex `research-pdf-library` | `manifest.json`, `corpus.txt`, per-paper extracted text | Kept where it is. Usable for existing lookups |
| Shared `paper-search` | `paperindex.config.json`, `papers_index.{json,md,csv}`, `_fulltext/` | Reuse a verified existing config, or build anew in a separate location |

The two formats differ in metadata and cache structure. Renaming files, or running the new tool over the existing index
folder, is not a migration. Do not replace `corpus.txt` with a new config automatically.
Installing or updating the skill is no permission to rebuild the actual PDF index or delete an earlier cache either.

If a new build is needed, choose an empty output folder outside both the existing index and the source, read the existing config,
then use a new config file name. `init` can overwrite an existing config, so do not reuse the same name.
When changing a preset, save it in a path the project owns and point to it from the config. Do not edit the installed `presets/`.

`reindex` adds only new relative paths. **There is currently no detection, by SHA-256, of changed content
at the same path.** If the source differs from the earlier verification record, the freshness of the existing full-text cache cannot be confirmed.
Plan a separate rebuild that keeps the existing manual corrections and cache, and if the scope of the needed output changes is unclear,
settle that scope first. Do not conclude that content is current from `doctor`'s path and count checks alone.

## Full verification after building or updating

`verify_index.py` uses only the Python standard library. It only reads the source and the index and creates only the new JSON
record you name. It does not overwrite existing records and does not write reports into the source or the installed skill.
It stops if the source and the index or the OA staging folder overlap. It records the relative path, size, mtime and SHA-256 of every
PDF, so it takes time on a large library. Do not repeat this procedure for every ordinary search.

1. Confirm that syncing of the source has settled and save a **pre-work snapshot** in a work folder outside the source.
2. Run the needed `index`, `reindex`, `resync` or `repair`. `repair` works on the extraction cache.
   The first `reindex` after a tool update may also rewrite values older versions wrote in Korean, after copying the JSON to
   `_backup/` ("When new PDFs are added" in `SKILL.md`). That change is expected; the rerun in step 4 must change nothing.
3. Check the paths with `doctor`, then use `verify` to check the whole source set, the index mapping, whether each active cache exists and is not empty,
   duplicate mappings, and entries with short full text or a note, and to compare the source records before and after the work.
4. With no source change, take another snapshot and run the same update command once more.
   For a new build, `index` must extract 0 more papers, and `reindex` must add 0 new ones.
   Use `verify --require-index-unchanged` to confirm that the contents of the active JSON and text caches are also unchanged.
5. Run one relevant search and check representative evidence against the source PDFs. Report every error and
   `extraction_exceptions`. If there are extraction exceptions, do not say the full text of every paper was verified.

Below is a PowerShell example with new record names. Choose the actual update command to fit the state of the source.

```powershell
$PaperCheck = Join-Path (Split-Path "$PaperTool") 'verify_index.py'
python -X utf8 "$PaperCheck" --config "$PaperConfig" snapshot --out '<work folder>/source-before.json'
python -X utf8 "$PaperTool" --config "$PaperConfig" reindex
python -X utf8 "$PaperCheck" --config "$PaperConfig" verify --before '<work folder>/source-before.json' --out '<work folder>/source-after.json'
python -X utf8 "$PaperCheck" --config "$PaperConfig" snapshot --out '<work folder>/rerun-before.json'
python -X utf8 "$PaperTool" --config "$PaperConfig" reindex
python -X utf8 "$PaperCheck" --config "$PaperConfig" verify --before '<work folder>/rerun-before.json' --require-index-unchanged --out '<work folder>/rerun-after.json'
```

Keep apart the fact that the tool's tests passed and **verification that the sources of the actual library did not change**.
Two identical snapshots mean no source change was detected between them. If an old cache existed before the build,
that is no evidence the cache is current. In the final report, record the actual scope checked, the commands, the input and output paths,
the total count, the exceptions, the result of the second run, and the fact that no write to the source was issued.
