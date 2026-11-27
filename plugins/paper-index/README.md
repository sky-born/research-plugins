# paper-index

English | [Korean](README.ko.md)

A tool that indexes a PDF literature library and searches its full text.
It is not tied to a field: change only the library path and the tag preset to use it anywhere.

**The source library is read-only.** The index and the full-text cache are built as copies in a separate folder.

## Why it is built this way

Reference managers (ReadCube, Zotero and others) either search only titles and abstracts, or rename
every file whenever you move to the cloud or download again. This tool deals with both problems directly.

- **It caches the full text and searches there.** It finds evidence sentences that are not in the abstract.
- **It re-matches files by content when file names change** (`resync`).
- **It restores PDFs whose font encoding is broken and whose characters are shifted** (`repair`).

## Installation

With Claude Code 2.1.275 or later, this one line registers the marketplace and installs the plugin.

```
/plugin install paper-index --marketplace sky-born/research-plugins
```

For older versions, Codex, and updates on several computers, follow the [README](../../README.md) at the repository root.
Claude Code and Codex use the same `skills/paper-search/` source. Do not copy the skill and the tools and maintain them separately.

You need only Python 3 and `pdftotext` (poppler-utils, or the xpdf one that Git for Windows ships — the tools ask either for UTF-8 output when they fill the full-text cache). No extra Python packages are used.
`python3` in this document is an example. Replace it with the `python`, `python3` or `py -3` you confirmed
in the current environment, or with the Python path the app provides. On Windows, add `-X utf8` and quote paths.
Find the tools relative to the directory of `paper-search/SKILL.md` that the app registered.
For detailed run examples, see the [guide to environments, moving and verification](skills/paper-search/references/portability.md).

```bash
# Ubuntu/Debian
sudo apt install poppler-utils
# macOS
brew install poppler
```

## Getting started

```bash
cd <new project folder>
python3 <tool path>/papertool.py init "/path/to/PDF Library" --name "My library"
python3 <tool path>/papertool.py index          # extract full text + build the index
python3 <tool path>/papertool.py tags-auto      # draft tags (when there is no preset)
python3 <tool path>/papertool.py search "keyword"
```

The `paperindex.config.json` that `init` creates is the whole configuration. Later commands find this file
automatically by walking up from the current folder.
If there are several configurations or a shared one, give `--config "<the configuration you confirmed>"` **before** the subcommand.

The `manifest.json` and `corpus.txt` of the earlier Codex `research-pdf-library` are a different index format.
**Existing caches and settings are not converted or overwritten automatically.** A `paperindex.config.json` that is already verified
can be reused. If you need a new build, use a separate output folder outside the source and the existing index.
Installing or updating the skill does not rebuild the PDF index.

## Commands

| Command | What it does |
|---|---|
| `init <library>` | Create the configuration file |
| `index [--limit N]` | Extract full text → metadata → tags → build `papers_index.{json,md,csv}` |
| `reindex` | Add only new files. **Existing manual corrections are kept** |
| `resync` | Re-match paths after file names change (name normalisation → content comparison) |
| `repair` | Restore the full text of PDFs with broken encoding |
| `tags-auto` | Draft a tag preset from the corpus document frequencies |
| `search <words> ...` | Full-text search of the library (owned papers). **The depth is adjustable** |
| `doctor` | Check for missing, duplicate and broken files |
| `scopus "<query>"` | Search Scopus and compare the results with the owned papers automatically |
| `scopus-merge <file>` | Compare a saved Scopus result with the owned papers (no network needed) |
| `scopus-sift <file>` | Filter a saved Scopus result with a regular expression (offline, no API call) |
| `oa-fetch <file>` | Download the **missing open-access** papers of a saved Scopus result into a staging folder (`_oa_inbox`) and make their full text. You can also chain it onto `scopus` and `scopus-merge` with `--fetch-oa`. Nothing is written to the library |
| `scopus-tidy` | Move the run files that version 0.9 or earlier left in the index folder into `_scopus/_done/` |

Search options: `--or` (OR search) · `--tag ENIG` · `--year 2019-2026` · `-n 5` (number of snippets) · `-c 200` (context length).
A search term is a regular expression and ignores case. The full text, the search term and the index title are character-normalised before comparison (PDF ligature `ﬂ` → `fl` · `µ` → `μ` · `℃` → `°C`,
`lib/textnorm.py`). The cache files are not modified.

`doctor` checks file paths and counts only. **It does not detect a change in the content of a PDF at the same relative path**,
so it does not guarantee that the existing cache is current. The separate `verify_index.py` checks the size, mtime and SHA-256 of all source files,
the index mapping and the active cache, and writes only a new JSON record. Use it to compare the source before and after a build or update, and to verify
a second run with no changes. Procedure and limits are in the [full verification guide](skills/paper-search/references/portability.md#full-verification-after-building-or-updating).

### Search depth

The scan always covers everything, so the statistics (number of papers hit, number of occurrences) are exact, and **only the output** is truncated by depth.

| Option | Output | Use it for |
|---|---|---|
| `--count-only` | One line of statistics | "Is this phrase used often?" |
| `--depth quick` | 3 papers in detail + a list of 10 | Checking terms, phrases and sentences |
| `--depth focus` (default) | 8 papers in detail + a list of 20 | Verifying claims and citation evidence |
| `--depth full` | All hits | An exhaustive survey, checking "nothing has been reported" |

`--max-docs N` · `--brief-docs N` · `-n` · `-c` override single items of a preset.
`--stop-after N` ends the scan itself early (the statistics become lower bounds, so do not use it to report frequencies).

## Configuration (`paperindex.config.json`)

```jsonc
{
  "name": "My library",
  "library": [                      // if you list several candidates, the first existing path is used
    "C:\\Users\\me\\Documents\\Papers",
    "/mnt/papers"
  ],
  "index_dir": ".",                 // '.' means the folder that holds this file
  "preset": "solder-thesis.json",   // looked up in presets/. Leave empty for no tags
  "min_tag_score": 4,               // threshold for assigning a tag
  "max_tags": 5,
  "oa_staging": "_oa_inbox",            // staging folder where --fetch-oa puts OA PDFs (relative to index_dir). Not the library
  "scopus": {                       // optional — leave it out to use the defaults below. Unknown keys and values are warned about and ignored
    "count": 25,                    // number of results per scopus call (--count overrides)
    "page_size": 25,                // page size of --all. Raise it only when the key can fetch larger pages (maximum 200)
    "view": null,                   // default: try COMPLETE and fall back to STANDARD if refused (--view overrides)
    "sort": null                    // Scopus sort value (--sort overrides)
  }
}
```

`library` can be a list because the same folder looks different depending on the environment
(the host's Windows path / the mount path in the agent's shell).

## Tags — presets and automatic generation

Tags are an axis for narrowing a search. Two methods work together.

1. **Presets** (`presets/*.json`) — hand-written rules that carry field knowledge. They group by concept and are accurate.
   `presets/solder-thesis.json` is an example (low-temperature solder, interfacial reactions, electronic packaging; 20 tags).
2. **Automatic generation** (`tags-auto`) — extracts technical terms with high document frequency from the library's full text and drafts a preset.

In a new field, the recommended flow is to **draft with automatic generation, edit by hand, then save it as a preset**.

```bash
papertool.py tags-auto --top 20        # creates index/tags.auto.json
#  → edit by hand and save as presets/mydomain.json
#  → set preset in the config to "mydomain.json" and run index again
```

Preset format:

```jsonc
{
  "name": "mydomain",
  "description": "...",
  "tags": {
    "<tag name>": ["<regex 1>", "<regex 2>"],
    ...
  }
}
```

A tag is assigned when the total number of regex hits exceeds `min_tag_score`. The order of `tags`
becomes the order of the topic sections of the index document.

## When file names change

```bash
papertool.py doctor     # if it reports "Paths missing"
papertool.py resync     # re-match: unchanged paths → name normalisation → content comparison
papertool.py reindex    # add newly created files and extract any missing cache
```

`resync` first keeps every entry whose file is still there, then matches the rest by the normalised name
(suffixes such as `_1` removed), and only then by **the beginning of the cache text**. A renamed paper keeps its own
full-text cache under the new name. Matches made by a name key that several files share are listed for checking.
An entry that does not match is treated as deleted from the source and removed from the index; `papers_index.json` is
copied to `_backup/` before such a change. An unused cache is not deleted; it is moved to `_fulltext/_obsolete/`.

## PDFs with broken encoding

Some conference PDFs have no ToUnicode CMap in the embedded font, so extraction returns a string of shifted characters.
`repair` finds them automatically, restores the code points, and splits words that ran together using **a vocabulary
taken from the same library** (`lib/wordsplit.py` — no separate dictionary is needed).

A restored copy is for searching. Sections that mix subset fonts are not fully restored, so **cite from the original PDF**.

## Scopus integration (optional)

Searching the owned papers alone cannot tell you which papers you missed. With the Scopus Search API, the tool scans
the whole index and **separates owned from missing papers automatically**.

### Setting the API key — keep it only in environment variables

Do not write the key in a configuration file or in code. This tool reads it only from environment variables.

**Windows**

1. Search the Start menu for **Edit environment variables for your account**
2. **User variables** → **New**
3. Variable name `ELS_API_KEY`, variable value: the key you were issued
4. If you received an institutional token separately, add `ELS_INST_TOKEN` the same way
5. **Quit completely** and restart the terminal or app

**macOS / Linux** — add `export ELS_API_KEY="..."` to `~/.zshrc` or `~/.bashrc`

`ELS_API_KEY` / `ELS_INST_TOKEN` are names that Elsevier-family tools share.
The script never puts the key in a URL or on the command line; it sends it only in the `X-ELS-APIKey` header
([Elsevier authentication documentation](https://dev.elsevier.com/tecdoc_api_authentication.html)).

> **Know the limits.** A user environment variable keeps the key out of Git and chat, but it is not
> encrypted storage. Other processes that run with the same user permissions can read it.

### Usage

```bash
papertool.py scopus "TITLE-ABS-KEY({Sn-Bi-In} AND solder) AND PUBYEAR > 2015" --count 25
```

The result is saved to `<index>/_scopus/<name>.{json,md}`, and a table compared with the owned papers is printed with it.
The DOI in the table is a clickable link (`https://doi.org/…`), and an `OA` column is added.

With `--fetch-oa`, the tool **keeps the search scope unchanged**, looks up only the missing open-access papers in OpenAlex,
downloads them into the staging folder (`oa_staging`, default `_oa_inbox`), and makes their full text in `_oa_inbox/_text/` (`OA ✔`).
If the configuration has no `oa_staging` and only the default folder of version 0.10 and earlier, `_수신` (meaning "received"), exists, that folder is used as it is.
To do it later on a saved result, run `oa-fetch <file.json>`. The staging folder is not the library, so move the PDFs you keep
with your reference manager and then run `reindex`. Subscription papers are not downloaded.
**The same DOI is downloaded only once** — even if the result name (`--name`) or the query differs, and even if another computer downloaded it,
a file already in the staging folder is not downloaded again; the tool points to that file. What was downloaded is recorded in the staging folder's
list of received files, `_manifest.json` (DOI → file). The order of decisions and the list format are in the header of `lib/oafetch.py`.

### In an environment with no network

In places where outside access is restricted, such as an agent sandbox, the call does not work. Then the `scopus` command
**does not crash**; it gives the one line to run in the terminal of a computer that has the key set. If you make
the result file there with the same command, comparing it with `scopus-merge <file>` works without a network.
`lib/scopus.py` is the only implementation that calls Scopus.

### Common Scopus query syntax

| Purpose | Example |
|---|---|
| Title, abstract, keywords | `TITLE-ABS-KEY(solder AND reliability)` |
| Exact phrase | `TITLE-ABS-KEY({flux-driven ripening})` |
| Author | `AUTHOR-NAME(Tu, K.N.)` |
| Journal | `SRCTITLE("Journal of Alloys and Compounds")` |
| Year | `PUBYEAR > 2018`, `PUBYEAR IS 2024` |
| DOI | `DOI(10.1234/example.2024.001)` |

**Page size.** The upper limit of results per request depends on the view and the service level of the key. According to Elsevier's
documentation it is 25 for COMPLETE and 200 for STANDARD, but depending on the level, even STANDARD gives HTTP 400
`Exceeds the maximum number allowed for the service level` above 25. So the tool uses 25 by default
(configuration `scopus.count` · `scopus.page_size`), and when this 400 occurs it fetches the same page again with 25 results and warns.
Raise `page_size` only after you confirm that the key can fetch larger pages. To fetch everything, use `--all`
(up to 5,000 results — above that, split by year); to skip some results, use `--start`.

## Citation check (optional)

`templates/citation-check/` holds a template that compares the citations in a manuscript with the index.
Change only the citation format in its config and it works in any project. See its README for details.

## Limits — know them before you use the tool

- **Title, author and journal are automatically extracted values.** Check them against the original PDF before confirming a citation.
- **Files whose name differs from their content are common.** Citing from the file name alone leads to a wrong citation.
  Check the section `## Needs attention` of `papers_index.md`.
- Only the surname of the first author is recorded. Check co-authors in the original.
- Paper IDs (`P001` and up) are **renumbered** by year and author each time the index is regenerated.
- The full-text cache is a copy. Do not write a `.txt` file as the source of a citation.

## Folder structure

```
skills/paper-search/
  papertool.py                 CLI entry point
  verify_index.py              verification of the source snapshot and the index (reads the source and index only)
  lib/                         config · extract · meta · tagging · decode · wordsplit · render · resync · searching · scopus · oafetch
  presets/solder-thesis.json   preset for the low-temperature solder and interfacial reaction field
  templates/citation-check/    manuscript citation-check template
  SKILL.md                     usage instructions for agents (distributed with the plugin)
```
