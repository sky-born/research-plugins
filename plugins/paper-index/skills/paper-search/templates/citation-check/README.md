# citation-check — template to compare manuscript citations with the owned papers

English | [Korean](README.ko.md)

It extracts the citations from a manuscript, compares them with the literature index, and reports them as **owned / needs checking / missing**.

Citation management differs by field and journal, so it is not built into the tool itself.
Only **the mechanical part is kept here, and the format is moved into a config.** In a new project,
start by copying this folder and editing `config.example.json`.

## Usage

```bash
cp -r templates/citation-check <project>/citation-check
cd <project>/citation-check
cp config.example.json citecheck.config.json
# edit citecheck.config.json for your project
python3 citecheck.py --out citation_check.md
```

## Only three things need editing

| Item | Description |
|---|---|
| `papers_index` | Path to the `papers_index.json` that `papertool.py` made |
| `manuscripts` | Glob of the manuscript files. Several are allowed |
| `citation_patterns` | Regular expressions for the citations. Use the named groups `num` / `author` / `title` |

Example regular expressions for each format are in the comments of `config.example.json`.

## Reading the result

- **Owned** — the index has a matching entry and the similarity is high enough. Even so, check the original PDF before confirming a citation.
- **Needs checking** — there is a candidate, but the similarity is low. It may be a person with the same name, or a truncated title.
- **Missing** — it is not in the library. The citation has not been checked against the full text, so obtain the paper or review the citation again.

## Limits

- Matching is an **estimate** based on the first author and title similarity. Writing the DOI in the citation as well greatly improves accuracy.
- A number-only citation (`[12]`) carries no author or title information. Add the reference list file to
  `manuscripts` and add a pattern for the list entries.
- It does not produce bibliographic formats (BibTeX, journal styles). That is the job of a reference manager.
