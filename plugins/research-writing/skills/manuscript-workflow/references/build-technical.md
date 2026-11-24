# docx builds — technical rules

These are the rules a build script must follow when it opens a template (a school-issued file or a journal template) and swaps in the body text. Where the template is, how to find it, and which parts the build changes are set by the project's build script and procedure document (`project-config.md`). What is here applies to every project.

## Word must open the output without prompting

The build does not insert any of the following. If even one is present, Word shows a dialog every time it opens the file.

| Never insert | Where | What Word asks |
|---|---|---|
| `<w:updateFields w:val="true"/>` | `word/settings.xml` | `This document contains fields that may refer to other files. …` |
| `<w:mailMerge>` | `word/settings.xml` | Data source connection · SQL execution |
| External references — `r:link`, relationships with `TargetMode="External"`, INCLUDEPICTURE · INCLUDETEXT · LINK · DDEAUTO fields | `word/document.xml` · `word/_rels/document.xml.rels` | Update linked files |

Embed pictures with `r:embed`. Use only fields that point inside the document: PAGEREF · SEQ · REF.

## The build fills in field results

- The build can compute the numbers for SEQ (figure and table numbers) and REF (references in the text), so it **fills in the result cache.** An empty cache shows as a blank when the file is opened.
- Page numbers (PAGEREF) are a typesetting result, and the build cannot compute them from the text alone. The build writes `0` into the cache, and there are two ways to fill it in.
  The project's procedure document says which way is used and how to switch it off.
  - **Word only computes, and the build writes the values** (when Windows Word can be automated) — the build writes the same content as the output into a temporary folder, opens it in Word without a window and **read-only**, updates all fields in the document until the values stop changing, and closes it **without saving**.
    The build writes the result text it received into the PAGEREF caches. The output is still the file the build wrote, so "The template stays byte-identical; changed parts are only appended" below and the self-check apply unchanged. This is why Word must not save: saving makes Word rewrite format parts such as `settings.xml`, `styles.xml` and the footers, and rename picture parts.
  - **A person updates in Word** (on a computer where automation is not available) — press `Ctrl+A` then `F9` once, right before submission. A rebuild resets the caches to `0`.
- Do not update fields one at a time. That returns values from before pagination is finished (all `1`). Update the whole document at once (COM `Document.Fields.Update()`).
- When calling `Documents.Open` through pywin32, pass the arguments by position — `(path, False, True, False)` are ConfirmConversions, ReadOnly and AddToRecentFiles.
  Named arguments (`ReadOnly=True`) may not take effect. After opening, check `doc.ReadOnly` to confirm the document is read-only.
- Do not use update-on-open (`updateFields`) instead. At that point pagination is not finished, so every page number becomes `1`, and the prompt above appears.

## The table of contents leaves page numbers blank, and the build measures overflow

This applies to builds that make each table-of-contents entry a single paragraph (title → right-aligned leader tab → PAGEREF). In this form, for an entry whose title fills the whole line, the page number sticks to the end of the title, runs into the right margin, and the dots disappear. It stays invisible while the cache is the single character `0` and shows only after the page numbers are filled in with two or three digits.

- Give the table-of-contents paragraphs a **right indent** to reserve space for the page number. The title wraps inside that indent, and only the dots and the page number sit in the outer band (the tab stop stays at the right edge of the body text).
  Set the band width so that at least two dots remain even before the longest page number, and keep it in one constant in the build script.
- A build that fills in page numbers with Word **also measures overflow in that Word calculation.** For each table-of-contents entry, check two things: whether the right edge of the page number goes past the right edge of the body text, and whether, on the same line, there is no room for two dots between the end of the title and the page number. If either one is hit, the build writes the count and the entries on a `!` line and exits with code 1 (the page numbers stay filled in and the file is kept).
- Measure horizontal positions with a **zero-length range** (`doc.Range(pos, pos).Information(…)`). In an indented paragraph this value comes out smaller by the left indent, so add the paragraph's `LeftIndent` when comparing it with the right edge of the body text. The difference between two positions in the same paragraph needs no correction
  (checked with Word 16.0 against PDF glyph coordinates for paragraphs indented 0, 17 and 34 pt). With another Word, check once against PDF glyph coordinates.
- A build in which a person fills in the page numbers (because Word cannot be automated) cannot measure overflow. Report it as "overflow not measured" (do not write 0 cases), and inspect the table of contents by eye after the page numbers are filled in.

## The template stays byte-identical; changed parts are only appended

- Copy the template's parts byte for byte. Change only the body (`word/document.xml`) and what the body needs (picture relationships, content types, missing styles), and **only append** to the existing content of a changed part. Do not touch `word/settings.xml`.
- Keep the list of changed parts as a constant in the build script, and write the same list in its header and in the project's procedure document. If a part outside the list must change, change this rule first.

## Self-check after the build

After writing the output, the build script **opens it again**, measures the following, and on any mismatch writes a `!` line and exits with code 1. The file is kept.

1. Are the parts that differ from the template only the declared list? — a byte comparison per part. Is `word/media/` the only part added?
2. Are there 0 items in the table of the first section?
3. Are there 0 empty result caches in SEQ and REF?
4. If page numbers were filled in, is no `0` or blank left in the PAGEREF caches?

When all is well, it summarizes in one line.

```
self-check  template parts identical (changed parts besides document.xml 3/3 declared) · external references 0 · prompting settings 0 · empty field caches 0 (SEQ 51 · REF 174 · PAGEREF 120) · page numbers filled 120/120
```

The assistant copies this line into the build report. If a `!` appeared, it does not write the output and looks for the cause. The commands for checking by hand are as follows.

```bash
unzip -oq <output>.docx -d chk
grep -c 'updateFields\|mailMerge' chk/word/settings.xml                 # 0
grep -c 'r:link' chk/word/document.xml                                  # 0
grep -o 'TargetMode="External"' chk/word/_rels/document.xml.rels        # normal when nothing is printed
```

## Captions use the Caption style, without `keepNext`

Word draws a **black square** in the left margin of a paragraph that has `keepNext`, `keepLines`, `pageBreakBefore` or `suppressLineNumbers` set.
It is a formatting mark that does not print, but it is distracting on screen.
If `keepNext` is set on figure paragraphs and table captions, every figure shows this square.

- Caption paragraphs use `<w:pStyle w:val="Caption"/>` (added to `styles.xml` at build time).
- Do not put `keepNext` in figure or caption paragraphs.
- Instead, check **by eye in the final layout pass** whether a figure and its caption are split at a page boundary.
  If they are, fix only that spot, and do not bring `keepNext` back globally.
