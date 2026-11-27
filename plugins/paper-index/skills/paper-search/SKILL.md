---
name: paper-search
description: Indexes a PDF literature library and searches its full text. Searches the owned papers, Scopus and the web together and labels each result by where it came from ([Owned] · [Scopus · OA fetched] · [Scopus] · [Web]). Use for requests such as "find papers on this", "check whether there is evidence for this", "search the literature", "update the index", "I added new PDFs" or "the file names changed".
---

# paper-search — literature search and indexing

Indexes a PDF literature library down to the full text and searches it.
It is not tied to any field. Each library needs only one config file (`paperindex.config.json`).

**Never modify the source library.** Only read it and extract text.

## Finding the tools

Use `papertool.py` in the same folder, taking as the base the **registered skill directory** this `SKILL.md` was read from.
Claude Code and Codex use the same content and tools; only the install location differs.
If the skill path the app gives cannot be confirmed, find this skill in the install list or a connected folder.
Do not search other apps' caches and pick the first file found, and do not search the whole disk.

First read [Environments, moving an existing index and verification](references/portability.md) to confirm the Python 3 interpreter and the
project config. Replace `python` in the commands below with **the confirmed Python 3 interpreter**
(`python`, `python3`, `py -3` or a path the app gives). Do not assume the interpreter name from the operating system alone.
On Windows, add `-X utf8` when checking output that contains Korean or other non-ASCII text, and quote every path.

Look for the config in this order: a path the user gives, the project's `AGENTS.md` or `CLAUDE.md`, a confirmed
`paperindex.config.json`. The tool can also search upward from the current folder, but with a shared profile or several configs,
**put `--config "<confirmed config file>"` before the subcommand**.
Confirm the chosen source path and index path, and keep the source and output folders apart.
The registered tool can be called from anywhere, but access to the source, config and cache must be confirmed in each environment.

The `manifest.json` and `corpus.txt` of the earlier `research-pdf-library` differ from the new format.
Do not convert or overwrite old configs and caches automatically. Reuse an existing `paperindex.config.json` if it has been
verified; if a build in the new format is needed, do it in a separate output location.

---

## A-0. How deep to dig — decide before searching

**Decide the depth before choosing where to search.** Look only as far as the question needs.
Laying out every matching paper with its text is **waste** for most questions.
The scan covers everything anyway, so "n of N papers" statistics are exact at any depth.
What the depth decides is **how many papers' text gets opened**.

| Depth | When | Command |
|---|---|---|
| **Quick check** | Whether an expression or term is actually used (usage, frequency). **Questions a few representative cases answer** | `--depth quick`; `--count-only` if only the frequency is needed |
| **Focused search** | Claims in the paper, citation evidence, reviewer replies. **Questions that need the original text checked within a limited scope** | `--depth focus` (default) |
| **Exhaustive search** | When the user **explicitly** asks for a systematic or exhaustive survey, or when checking a **claim of absence or novelty** such as "first", "none" or "not reported" | `--depth full` |

### Quick check — stop here

- "Is this expression common in the field?", "Is there a paper that uses this term this way?"
- Checking the spelling convention of a term (`Ni3Sn4` vs `Ni₃Sn₄`)
- Checking only whether "our library covers this concept"

**Start term and expression questions with `--count-only`.** One line such as "Searched 40 papers · matched 28 of them (70%) · 152 occurrences in total"
already answers "is it common?". If usage examples are wanted, look at 2–3 representative papers with `--depth quick` then.
**Paper counts answer only usage.** For "Is this expression correct?" or "Does it sound natural?", show usage examples but judge the grammar separately —
the principle is in `research-writing` `style-guide.md` "Usage".
**Pulling out the text of every paper here answers a question nobody asked.**

### Focused search — the default

- Checking whether a sentence in the manuscript has evidence
- Checking numbers, conditions and experimental results against the original text
- Finding evidence papers for a reply to a reviewer

Shows the top 8 papers with text, then the next 20 as one-line entries.
**Pick only what is needed from that list** and look again, narrowed with `--max-docs`, `--tag` or `--year`.
Do not open everything from the start.

### Exhaustive search — only when asked

- "Survey all the literature on this topic", "Check without missing any"
- Checking before writing "this composition has not been reported" / "this study is the first"
- Updating the missing-papers list, citation check (citation-check)

**Do not check claims of absence or novelty shallowly.** A "none" conclusion comes only from an exhaustive survey.
Use `--depth full` and add spelling variants with `--or`.
If the local search finds 0, go on to Scopus and confirm there is none outside either before the conclusion stands.

### When unsure

**Start shallow and go deeper.** Running shallow and deepening if needed costs little,
but opening everything from the start cannot be undone. The last line of the output gives the number of papers not shown,
so you can judge whether to look further. Ask the user in one line: **"There are n more papers — shall I go through them?"**

If the scan time itself is a problem in a very large library, cut the scan with `--stop-after N`.
The statistics then become lower bounds, so **do not use it when reporting frequencies or ratios.**

---

## A. Where to look — local first, the rest by judgement

There are three places to search. **Always look locally first.** The others are used by judgement, not automatically.
If the user or applicable higher-level or project instructions set a search scope, that scope takes precedence.

| Source | Strong at | When |
|---|---|---|
| **Local index** | Full text. Evidence sentences that are not in the abstract | Default. Holdings, checking evidence, citation check |
| **Scopus** | Bibliographic accuracy. DOI, authors, year, journal, citation count | Systematic literature surveys, confirming references, finding missed papers |
| **Web search** | Standards, technical data, grey literature, recent news | What Scopus does not have. JEDEC/IPC standards, manufacturer data, blogs |

### Local only — do not look elsewhere

- **When the holdings themselves are the question** — "Do I have this?", "Update the missing-papers list",
  "Check that every cited paper is in there", "I think I added them all, please check"
- Matching the manuscript's citations against the library (citation-check)
- Checking index state, duplicates, file names, full-text extraction
- Finding evidence sentences or numbers in the text of a paper already known
- When the user limits the scope to owned papers

Searching outside for such requests **answers a question nobody asked**. Do not do it.

### When to go to Scopus

- When a topic must be **covered comprehensively** — "Survey the literature on this topic", "Did I miss any papers?"
- When the **bibliographic details** of references must be confirmed (DOI, volume and issue, year)
- When a specific author, journal or year range must be scanned exactly
- When importance must be gauged by citation count
- When something is not local and you must check "whether it exists outside"

### When to go to the web

- Outside the scope of Scopus — **standards (JEDEC, IPC, ASTM), manufacturer datasheets, conference announcements, news**
- When Scopus returns 0 or the topic is poorly covered by academic indexes
- When one quick fact check is enough

### When in doubt

Run the local search first and **decide from the result.** If the local search answers it, stop there;
if more seems needed, **add one line: "Shall I search Scopus too?"**
Do not run everything in advance and pad the results. If unsure, asking once before starting is better.

### Step 1 — local search

```bash
cd "<index folder>"
python -X utf8 "<tool>/papertool.py" search "Ni3P" "fracture"        # AND, default depth focus
python -X utf8 "<tool>/papertool.py" search --or "Scheil" "nonequilibrium"
python -X utf8 "<tool>/papertool.py" search --tag "ENIG" "shear"
python -X utf8 "<tool>/papertool.py" search --year 2019-2026 "Sn-Bi-In"

# depth control
python -X utf8 "<tool>/papertool.py" search --count-only "significantly"      # paper and occurrence counts only
python -X utf8 "<tool>/papertool.py" search --depth quick "in situ"           # 3 representative papers
python -X utf8 "<tool>/papertool.py" search --depth full --or "Sn-Bi-In" "SnBiIn"   # everything
python -X utf8 "<tool>/papertool.py" search --max-docs 2 -n 5 -c 200 "cuboid" # individual settings
```

`--depth` is a preset; `--max-docs`, `--brief-docs`, `-n` and `-c` override single items.
`--tag` matches part of a tag name, ignoring case, and also accepts a tag's old name (the preset's `renamed`, below in B).

Search terms are regexes and ignore case. Full text and search terms are compared after **character normalization** (`lib/textnorm.py`) —
PDF ligatures (`reﬂow` · `Eﬀect`) become `reflow` · `Effect`, `µm` becomes `μm`, `℃` becomes `°C`, and en dashes and hyphen variants become `-`.
The cache files stay as extracted, so **grepping `_fulltext/` directly misses words with ligatures** (write `re(fl|ﬂ)ow` and the like).

**Add spelling variants.** `Sn-Bi-In` / `SnBiIn`, `Ni3Sn4` / `Ni 3 Sn 4` (an en dash `Sn–Bi–In` is found by `Sn-Bi-In` through normalization).
Text extracted from PDFs can differ from the original in hyphens, subscripts and spaces.
**If a multi-word phrase finds 0, try again with the words one at a time.**
Documents whose encoding was restored can have words run together, so phrase searches can fail.

### Step 2 — Scopus (only when judged necessary)

**Results come with abstracts.** The tool asks for the COMPLETE view (abstract, all authors, author keywords) by default
and falls back to STANDARD (bibliographic data only) automatically if the key has no access. Read the
`Per-entry abstracts` section of the saved `.md` (`항목별 초록` in files saved by older versions) and **select by content** —
do not pick by title or citation count alone.

**Just run it first.** On a computer where the key is set and the network is reachable (local Claude Code, for example),
results come right there. Network and environment-variable access differ by environment.
Only when direct calls are blocked and the tool prints the note in (a) below, switch to the two-step route.

```bash
# On success, results right away. In a blocked environment, a note says what to run where
python -X utf8 "$TOOL" scopus "TITLE-ABS-KEY(Sn-Bi-In AND solder)" --count 25 --fetch-oa
```

`--fetch-oa` **does not change the search scope.** After matching all the results, it fetches only the missing open-access papers
into the staging folder and makes their full text (below, "Open-access papers are fetched and read in full"). Add it by default.

**(a) An environment where direct calls are blocked — build the query and ask the user to run it.**

Ask the user to run the same command **in a terminal on a computer where the key is set**. The note the tool prints when blocked
contains the one line to paste. The key goes into no file — it is read from the environment variable at run time.

```bash
python -X utf8 "<tool>/papertool.py" scopus "TITLE-ABS-KEY(...)" --count 25 --name <name>
```

The result is saved in `<index>/_scopus/<name>.json`; match that file with (b) below.

**Write the query in exact Scopus syntax for the user.** Do not make the user memorize the syntax.

- Fields: `TITLE-ABS-KEY(...)`, `TITLE(...)`, `AUTHOR-NAME(...)`, `SRCTITLE(...)`, `DOI(...)`
- Operators: `AND` `OR` `AND NOT`; phrases as `{exactly this phrase}` or `"loose phrase"`; truncation with `*`
- Ranges: `PUBYEAR > 2018`, `PUBYEAR IS 2024`
- Example: `TITLE-ABS-KEY({Sn-Bi-In} AND solder) AND PUBYEAR > 2015`

### Multi-component systems (alloys, compounds) — an AND skeleton of elements, not a list of phrases

Researchers write compositions in many ways — element order, hyphen type, inserted numbers (`A-40B-10C`), run together (`ABC`), spelled-out names.
Chasing one spelling as a phrase always misses papers. Do this instead.

1. **Skeleton — unambiguous element symbols joined with AND, plus a context word.** `TITLE-ABS-KEY(A AND B AND solder*)`.
   Scopus tokenizes punctuation like spaces, so reordering, hyphen types and inserted numbers are all caught automatically.
2. **Leave symbols that are also English words out of the query** — they filter out almost nothing anyway.
   These are `In` (= the preposition in), `As`, `At`, `Be`, `No`, and every one-letter symbol (B C H I K N O P S U V W Y).
3. **Resolve ambiguous elements after fetching, with `scopus-sift`.** Abstracts always carry the spelled-out name or formula tokens,
   so a regex restores the precision. `--require` is **case-sensitive by default** — required for element-symbol patterns
   (turn it off with `-i`). Catch subscript markup (`X<inf>2</inf>O<inf>3</inf>`) with `X<`.
4. **Cover papers that only write compositions run together.** Add permutations of the whole system and the **binary subsets**
   to the skeleton query with OR — without the binary run-together forms, papers that treat two binary systems together are lost.
5. **Also run a spelled-out-name query for the ambiguous elements, and merge.** TITLE-ABS-KEY also searches the index terms (INDEXTERMS), but sift
   looks only at the title, abstract and author keywords, so **entries caught only through index terms drop out in sift** — the spelled-out query fills that gap.
   Merge the results by DOI/EID.
6. **Traps** — several wildcard phrases in one query give HTTP 500. Mixing wildcards into a large OR query shrinks the results
   **without warning** (run supplementary queries separately and merge). Phrases that begin with an ambiguous symbol clash with the preposition and bring in
   floods of unrelated papers. To check that a specific composition exists, use the exact phrase (`TITLE-ABS-KEY("A 19B 19C")`).
7. **Procedure at scale.** First send a small count to see the total, then fetch with `--all` (pagination limit 5,000 results —
   split by year beyond that). If the key refuses large pages (HTTP 400), the tool fetches again with 25, so no manual splitting is needed.
   Each call uses 1 of the quota, so a sweep of a few hundred results is no burden.

**Keep system-specific regexes, measurements and example commands in that project's literature file.** Do not write them in this document.

**(b) If the user has made the result file, match it.** This works without a network.

```bash
python -X utf8 "$TOOL" scopus-merge "<index>/_scopus/<name>.json"
```

The Scopus results are matched against the owned papers automatically, and a table shows **which are already owned and which are not**
(DOI match first, otherwise title similarity). The results are saved in `_scopus/<name>.{json,md}`,
and for a file fetched with COMPLETE the `.md` ends with a `Per-entry abstracts` section.
Result files keep what they were written with; files from older versions have Korean headings and notes, and the tools still read them.

If launcher files that versions 0.9 and earlier made in the index folder (`Scopus검색_*.bat`, "Scopus search" · `.query.txt`) remain,
`papertool.py scopus-tidy` moves those that have a result JSON to `_scopus/_done/` (to `_scopus/_실행완료/`, "run done", instead, if that folder
already exists). The current version makes no launcher files.

**Never let the user type the API key into the chat** (G-0). The key stays only in an environment variable on the user's computer.
If there is no key or the network is blocked, the tool only prints a note and ends quietly — it does not crash.

### Open-access papers are fetched and read in full

`--fetch-oa` (or `oa-fetch <file.json>` on saved results) asks OpenAlex about the missing entries and, if there is an
open-access PDF, saves it in the **staging folder** (config `oa_staging`, default `<index>/_oa_inbox`) and
makes its full text as `_oa_inbox/_text/<DOI>.txt`. The table marks it `OA ✔`, and the file path is added under
`Per-entry abstracts`.

- **Read the full text of what was fetched before reporting.** Grep `_text` to confirm evidence sentences, and report them apart from
  entries seen only through abstracts (step 4).
- **The staging folder is not the library.** It is not indexed either. The user moves PDFs worth keeping into the library with their own
  reference manager and runs `reindex`. **The tool does not move them** — that could break the reference manager's
  sync, so it is the user's decision. Once a paper is moved and taken in, its matching `_text` file is moved to
  `_text/_obsolete/` on the next run.
- **The same DOI is fetched only once.** What another `--name`, another query or another computer fetched is not fetched again either
  if it is in the staging folder; only `oa_file` and `oa_text` are filled (output "Already staged: N papers"). What was fetched is recorded in
  `_oa_inbox/_manifest.json` (the fetch manifest), and the module docstring of `lib/oafetch.py` is the authority on the decision order and the format.
  If a copy `<name>_1.pdf` with identical content appears, that is a tool defect; report it to the user before deleting anything.
- At most 30 papers per run (`--oa-limit`), 3–5 seconds between downloads, and only addresses OpenAlex gave.
  Subscription papers are not touched.
- In an environment where the network is blocked, the tool only prints a note and still saves the results. Fetch later with `oa-fetch`.
- The citation source is the original PDF. Do not cite `_text` as the source (G).

### Missing papers that are not open access — shortlist by abstract and ask for the download

There is no way to fetch the full text of subscription papers through the API. **The API's part ends at the abstract**; the full text
is downloaded by the user in a browser (institutional subscription or proxy) and put into the library.
**If the project has a download-list tool, use it** — check the project's `AGENTS.md` or `CLAUDE.md`.

1. Read the `Per-entry abstracts` section and pick **only the papers that actually contribute to the question**.
   If there are hundreds of results, filter with `scopus-sift` first, then read.
2. Present the chosen missing papers as a **download request list** — each with a DOI link and one line on the reason
   confirmed from the abstract. If there are many, split them by priority.

   ```
   - [ ] Yao (2026). Barrier effect of Sn-Bi-In ... Mater. Sci. Eng. A.
         https://doi.org/10.1016/j.msea.2026.149916
         Reason: quantitative comparison of the thermomigration resistance of Sn-Bi-In — candidate evidence for §x.x
   ```

   If the list has to last beyond the session, save it in the same format in `download_requests.md` in the index folder.
   If the index folder already has `다운로드요청.md` ("download requests", the name older versions used), keep appending to that file instead.
3. When the user says the PDFs are in the library, take them in with `reindex` and remove the fetched entries from the list.
   From then on, the full-text search (step 1) finds those papers.

### Step 3 — web search (standards, technical data and other material outside Scopus)

Use the web search and page-fetch tools the current app provides. Use what is actually registered, such as Claude's `WebSearch` or `web_fetch`
or Codex's web tools, and do not assume another app's tool names.

### Step 4 — report

Mark each paper with an evidence level: **`full-text verified` / `abstract-only` / `metadata-only` / `inaccessible`**.
Do not mark it `full-text verified` just because the extracted text was found.
Check sentences, numbers, tables and figures to be confirmed against the original PDF, and keep the PDF page order apart from the printed page numbers.
If Scopus really has no abstract, it is `metadata-only`.

Report only what was run. **Do not make excuses for sources not searched.**
If several sources were searched, label the source.

- **[Owned]** — in the library. `P0xx` ID + file path + evidence sentence snippet
- **[Scopus · OA fetched]** — not owned, but fetched into the staging folder with `--fetch-oa`. The **evidence sentence** confirmed in `_text`
  and the file name. State that it is not yet in the library
- **[Scopus]** — indexed but not owned. Title, authors, year, journal, DOI, citation count.
  If there is an abstract, add one line on **why this paper fits the question, as confirmed from the abstract**
- **[Web]** — other sources. Give the URL

Owned papers first, outside ones after. If an owned paper supports the same evidence, do not replace it with an external one.
For results with a `※` note, pass the note on to the user as it is.

---

## B. Indexing a library for the first time

Choose a new config and output location outside the source, then prepare the pre-work snapshot of the
[full verification procedure](references/portability.md#full-verification-after-building-or-updating). Do not overwrite an existing config or cache.

```bash
python -X utf8 "<tool>/papertool.py" init "<library path>" --name "<name>"
python -X utf8 "<tool>/papertool.py" index          # full-text extraction takes time
```

Agent shells limit the time of one call. If `index` reports "N left",
**run the same command again**. It continues where it stopped. (Adjustable with `--limit`.)

Without a tag preset, the tags are empty. Make one like this.

```bash
python -X utf8 "<tool>/papertool.py" tags-auto --top 20   # draft from the corpus
```

Refine the draft with the user, save it as `presets/<field>.json`, put it in the config's `preset`, then
run `index` again. **Do not adopt automatically generated tags as they are** — journal names and common
expressions slip in. Always show them to the user and get confirmation.

**To rename a tag later, keep the old name in the preset's `renamed`** (`"renamed": {"<old name>": "<new name>"}`, format in
`lib/tagging.py`). The next `reindex` rewrites the old name in the existing entries, and `search --tag` accepts either name.
The bundled `solder-thesis.json` lists its earlier Korean tag names there. A tag's regex list may also hold Korean words (such as `도금`, "plating")
so that it matches Korean-language titles.

## C. When new PDFs are added

Before and after building or updating, run the [full verification procedure](references/portability.md#full-verification-after-building-or-updating).
Do not update on every search request. With an already verified index and an unchanged source, just search.

```bash
python -X utf8 "<tool>/papertool.py" reindex
```

Existing entries (including manual corrections) are kept and only new files are added.
Any missing full-text cache, of a new file or of an existing entry, is extracted; PDFs that cannot be extracted are listed,
and an existing entry with a restoration note that was extracted again needs `repair`.
**The first `reindex` after an update can change existing entries too:** values that older versions wrote in Korean
(the `untagged` tag, the notes `repair` writes, journal names guessed from a DOI) and tag names the preset's `renamed` retires
are rewritten in English, exact matches only. Before that write, `papers_index.json` is copied once to
`_backup/papers_index_<date>.json` and one line reports the count; hand-written notes and edited values stay as they are.
The next run changes nothing.
**A change in the content of a PDF at the same path is not detected automatically.** If the size, mtime or SHA-256 differs from the earlier
verification record, the cache may be stale. Plan a separate rebuild that keeps the existing index and manual corrections,
and do not report the index as updated by `reindex` alone.
OA PDFs fetched into `_oa_inbox` become `reindex` targets **only after the user moves them into the library**.
Until then they are not in the index and are read only through `_oa_inbox/_text`.

**If the library folder does not exist, `doctor`, `index`, `reindex`, `resync` and `repair` stop.**
This prevents a quiet run over "0 source papers" when none of the candidate folders exists. `search` keeps working from the cache alone
but prints a one-line warning. `doctor` prints the chosen library path on its first line and warns if the source has fewer than half as many
papers as the index. In that case `reindex` does not proceed without `--force` — this prevents files from the wrong folder,
or from an unfinished sync, from being added as new papers.

## D. When file names change — this happens often

Reference managers add and remove `_1`/`_2` suffixes, or download everything again when switching to the cloud.

```bash
python -X utf8 "<tool>/papertool.py" doctor    # if it reports "Paths missing"
python -X utf8 "<tool>/papertool.py" resync    # unchanged paths → name normalization → content
python -X utf8 "<tool>/papertool.py" reindex   # add new files, extract missing caches
```

`resync` keeps a renamed paper's own full-text cache under the new name and copies `papers_index.json` to `_backup/`
before it drops or renames entries. Check the IDs it lists as "matched by a name key that several files or entries share"
against their PDFs before relying on those entries.

**Confirm the library is stable before working.** Take a hash of the file list twice, 20 seconds apart,
and check that they match. If not, a sync is in progress; wait before starting.

Both records can be made with the bundled `verify_index.py snapshot`, which lets you compare the relative path, size, mtime and SHA-256
in `sources`. Keep the records in a work folder outside the source, and if they differ, check again after the sync finishes.

## E. When the full text is garbled

```bash
python -X utf8 "<tool>/papertool.py" repair
```

Finds PDFs whose font encoding is off, shifts the code points back, and splits words that ran together.
The restored text is for searching. Some documents are not fully restored; check the entry's `※` note.

## F. Citation check (only on request)

To match a manuscript's citations against the index, copy `templates/citation-check/` into the project and
edit the citation regexes in `citecheck.config.json` to fit that project's format.
Citation formats differ by project, so **do not choose one yourself; confirm it with the user**.

---

## G-0. Handling the API key — no exceptions

- **Do not take the key in the chat.** If the user starts to type it, stop them and explain how to set the environment variable.
- **Do not write the key into any file** — not `paperindex.config.json`, scripts, logs or result files.
  The tool reads it only from the environment variables `ELS_API_KEY` / `ELS_INST_TOKEN`.
- **Do not put the key in a URL or a command-line argument.** Send it only in the `X-ELS-APIKey` header.
  In a query string it stays in shell history and proxy logs.
- When quoting an error message, check that the key is not in it. The tool masks it automatically.
- Do not retry `401`, `403` or `429` repeatedly until the user approves or the access or quota state changes.
  If access is still blocked after the tool's limited-view fallback, report the access limit and use another available search route.
- Environment variables keep the key out of Git and the chat, but **they are not encrypted storage.** Other processes running
  with the same user's rights can read them. If the user asks, say so plainly.

## G. Always

- **The source folder is read-only.** Do not create, modify, rename, move or delete files.
- **Titles, authors and journals in the index are automatically extracted.** Do not confirm references from the index alone.
  Find the evidence sentence in the full-text cache, then **check against the original PDF** before confirming the citation.
- **The citation source is the original PDF.** Do not cite the full-text cache (`.txt`) as the source.
- **Some files have names that do not match their content.** Check the `Needs attention` section of `papers_index.md` first
  (`주의 필요 항목` in an index last written by an older version).
- **Paper IDs are renumbered every time the index is regenerated.** Do not trust IDs from an earlier conversation; check them again.
- **Decide the depth first (A-0).** Do not pull out the text of every paper to check an expression or term.
  But always check claims of absence or novelty ("none", "first") with `--depth full`.
- If a search finds 0, report it as is. Do not make anything up. But it may be due to spelling variants or the limits of phrase
  search, so split the terms and try once more before concluding.
