<!-- toc -->
**Contents**

- Writing protocol
  - Role boundary
  - Approval and comparison
  - Applying approved edits and verifying the save
  - Reviewing titles and captions — keep the section's body text alongside
  - Critical review mode
  - Order of work
  - Pre-submission grammar check
<!-- /toc -->

## Writing protocol

### Role boundary

- The assistant proposes wording, structure, logic and items that need verification. The user has final responsibility for experimental results, observations and factual accuracy.
  Hand points that need the user's check back to the user explicitly.
- Do not invent data, values, observations or citations. Mark a missing value as `**XX**` and an unverified reference as `**source not checked**`.
- Reading colour, contrast, morphology, phase identification or crack paths from images is always "interpretation" and must be checked against the user's actual observations and composition analysis.
- Do not present unverified work as verified. Label it as confirmed / under review / literature check needed / awaiting experiment.

### Approval and comparison

- Work sentence by sentence or item by item. Treat items the user has confirmed as locked, and do not touch them again unless asked
  (you still point out problems — the paragraph-flow check below · "Pre-submission grammar check").
- **Only the user declares something confirmed.** Until the user says it is confirmed, do not call any sentence or paragraph the confirmed version.
  Even after applying it to the file, do not call it the confirmed version, confirmed or final; call it the applied version, the current applied state or awaiting review (in the user's language).
  In the `**Status**` line of a completion record, likewise do not write `confirmed` without the user's confirmation.
  Applying text to the file first is fine in itself, but treat that state as a draft that can be reverted at any time.
- **Before changing a manuscript file, find the user's words of confirmation or instruction to apply in this turn's message, and quote them verbatim in your reply.**
  **If there are no words to quote, do not change the file; only propose.** A judgement ("this seems right"), an opinion or an instruction to revise the wording
  is not an instruction to apply. When several items were asked at once, the user's item-by-item answers are not an instruction to apply either.
  This is a check right before acting: find the quotation before you call an editing tool.
- **When you write `confirmed` in the `**Status**` of a completion record, quote verbatim the words in which the user declared it confirmed.**
  Without words to quote, it is not `confirmed` — write `applied (awaiting confirmation)`. "Apply it" or "let's go with this" is
  an instruction to apply, not the user's confirmation. A user's rewording of the text is not confirmation either — apply the reworded text and
  get confirmation again.
- **When you show a paragraph, attach its status.** If the user has not declared a paragraph confirmed, even one already applied to the file,
  write `applied (awaiting confirmation) — E<number>`, and list the open items (D · H) attached to that paragraph on one line with it.
  A paragraph shown without a status reads as the confirmed version, and the user takes it for a finished paragraph.
  Call text the original only when the user has confirmed it. Text applied but not yet confirmed is the current applied state.
- **When you show a paragraph, also send the one manuscript file that contains it** (in environments that have a way to send files to the user).
  An excerpt in the reply alone does not let the user see the neighbouring paragraphs and the notes at the end of the file side by side.
  Send only that one manuscript file. Send comparison tables, completion records and tracker files only when the user asks.
  If you already sent it in the same session and its content has not changed since, do not send it again; just point to it with a link.
  If applying a change altered the file, send it once more after the change.
- **A "confirmed paragraph" means only a paragraph the user declared confirmed in the sequential review now under way.**
  A section is polished **by confirming it one paragraph at a time, going down ¶1 → ¶2 → ¶3**.
  So the confirmed paragraphs are **the ones above the paragraph you are working on now**.
  **Paragraphs further down are not confirmed paragraphs, even if a completion record carries an item number for them** — before the sequential review reached them,
  only odd spots in them were fixed in passing while other paragraphs were being worked on, so **you may change them.**
  **Test** — if that completion record item **rewrote the whole paragraph** and the user declared it confirmed then and there, it is confirmed;
  if it was a side effect of other work, it is not. If unclear, go by whether the sequential review has reached that paragraph.
- **The "next paragraph" is the next one only after the previous paragraph is confirmed.** If the previous paragraph is `applied (awaiting confirmation)` or
  has open items attached, do not move on; present that paragraph first. When the user names a section or
  asks for the "next paragraph", scan that section's paragraphs from the start, take **the first unconfirmed paragraph** as the starting point,
  and present from that paragraph on, with recommended revisions. If there is a reason to present a later paragraph first, state the reason
  and note that the earlier paragraph is still open.
- **What makes a "paragraph to revise" is whether the user has confirmed it, not my work history.**
  A paragraph I have already touched comes **first** if the user has not confirmed it, and paragraphs I have not yet touched
  come after. Do not read it as "paragraphs my revisions have not reached yet".

  | Rank | Status | Meaning |
  |---|---|---|
  | **1** | `applied (Exx)` · `applied (awaiting confirmation)` · `partly confirmed` | In the file, but **not confirmed by the user.** Start here |
  | **2** | Not reviewed — paragraphs the sequential review has not reached | When no rank-1 paragraph is left |
  | — | `confirmed` | Pass over |

  Projects made before 0.14 write these status words in Korean — the older spellings are in `_config.LEGACY_SPELLINGS`; read them the same way (`tracker-workflow.md` "Format tokens").
  Until such a project is migrated, write status words in the spelling its files already use; after migrating, write English.

  Among paragraphs of the same rank, present the one with the lower paragraph number first.
  **When presenting a paragraph awaiting confirmation, do not make a new proposed revision** — put the previous wording and the currently applied wording
  side by side and list **only the points the user must decide to confirm it**. The purpose is to let the user confirm the proposal already made,
  not to make a new one. The previous wording is in that item's completion record; if it is not there,
  take it from the latest output (the built `.docx` and the like).
- **When presenting a revised sentence, always show the current text directly above it.** Do this by default without waiting to be asked.
- The baseline is the text the user most recently provided or approved.
- Present sentences within the whole paragraph so that flow, scope and consistency can be seen together.
- Before changing a sentence, read the sentences before and after it and the whole paragraph. Check whether it naturally continues the subject or referent the previous sentence introduced, and that the observation → interpretation order, antecedents, transitions, repetition and the strength of the following sentence's claim are not unintentionally reversed or weakened.
- **Before proposing a revision of one paragraph, read the paragraphs before and after it and check the flow. If something is wrong, raise it before the proposed revision.**
  Points to check — ⓐ is the same argument repeated in two paragraphs ⓑ does a preview or conclusion sentence come before the body it introduces
  ⓒ does the antecedent of a referring phrase (`this proposition`, `the kinetic explanation`) actually exist in the previous paragraph ⓓ do two paragraphs end with the same words.
  **Point it out even if the previous paragraph is already `confirmed`.** Because paragraphs are confirmed one at a time, a repetition that was not visible when the previous paragraph was confirmed
  shows up only after the next paragraph is confirmed. Make a change only when the user instructs it, and
  when changing a confirmed version, do not edit the existing item; replace it under a new number.
- Mark only the parts changed from the baseline with backtick code spans (`...`). **Do not mark them in bold** —
  in the Claude Code terminal, bold only changes brightness and gets lost in the text. Code spans get a background and
  show in every app, so **do not change the marking by environment.**
  If you rewrote a whole paragraph, give the full text instead of marking each piece, and say so.
  State deleted or moved text separately. Make no unmarked edits.
- When offering alternatives, explain the differences in hedging strength, nuance and trade-offs, and apply the chosen approach consistently to similar cases.
- Minimal intervention. Keep existing statements that can be defended, and do not pull in a large amount of new logic to save one sentence.
- Keep the whole consistent. When a new conclusion is confirmed, find conflicting statements, leftover terms, numbering and duplicated text, **report them first**, then fix them.

### Applying approved edits and verifying the save

- Right before writing, confirm **the base root, the target file and the approved scope**. Reread the project's latest guidance and the related
  tracker items, and recheck the target paragraph and its surrounding context in the actual file.
- Edit the source agreed with the user. When a built DOCX or PDF and its source are separate,
  **change the source the project designates**, and do not overwrite the output directly.
- Apply the smallest exact change. If the expected existing wording is missing, appears in several places so that the target
  cannot be told apart, or the file has changed since you last read it, report the mismatch before writing.
  Preserve changes by other sessions and by the user; do not force-overwrite or run destructive Git clean-ups.
- After saving, **reread from disk** and check the number of occurrences of the approved wording and that the required deletions took place.
  Also check that headings, paragraph boundaries, citations, comments and adjacent sentences are intact.
- Record substantive manuscript changes with the tracking sources and tools the project defines.
  Preserve existing IDs and the user's wording, and if you updated a record, reread that item too.
- Whether to build and where the output goes follow the project procedure. During an ongoing sentence review,
  put off unnecessary builds; when you build, keep a comparable previous version within the approved output scope.
  After building, check the structure and the actual page layout, and do not report verification you did not perform as done.
- At the end, report the changed files, the exact scope, the reread verification, whether you built, and what remains unverified.

### Reviewing titles and captions — keep the section's body text alongside

A title cannot be judged on its own. The test is "does the title say only what is established within its section", so the evidence is in the body text.
Give the four items below **in one reply** — do not send the title, the full body text, the flow and the review separately.

1. **Send that manuscript file first** (in environments that have a way to send files). Write the line numbers under review in the caption.
   **For a figure caption, also send the figure file** — a caption is text that describes the figure, so it cannot be checked without it.
   For a table caption, lay out the table's content in the reply.
2. **Put the title and the full body text of its section side by side on one screen.** Label each paragraph with `¶n` and its line number; for notes that are not printed,
   say so and give only a summary. **Do not substitute a table of gists.**
3. **Give the gist of each paragraph together with the section's line of argument.** For each paragraph, one or two lines on what it says, and how the paragraphs
   follow one another — what they start from and what they narrow down to. For a sentence whose support lies in citations or convention rather than in the body text, note that too.
   On that basis, summarise in one line "what the section actually does", then give the review result and candidate titles.
4. **Go one section at a time.** Do not show the titles of several sections together in a list.

### Critical review mode

On request, take the view of a sceptical reviewer and find unsupported assumptions, citation–claim mismatches, indefensible sources, overstated scope
and internal contradictions. Regardless of mode, report serious flaws before adoption, and do not dilute concrete problems and needed fixes
with general praise.

### Order of work

1. Items whose facts are settled
2. Items that need a literature check
3. Items on a new mechanism that need hedging
4. Items awaiting experiments

If experiments are the bottleneck, work in parallel on text that can be completed independently.
Do the integrated discussion in the Discussion after the individual items are stable. The grammar of the whole manuscript is checked separately before submission (see "Pre-submission grammar check" below).

End work that spans several sessions with a handoff covering confirmed points, reference formatting, the style level, and the remaining items and their order.

### Pre-submission grammar check

Before any English text goes out, check the whole text once for **grammar only** — a submission · revised version · proofs · dissertation chapter,
and the response letter and cover letter that go with it. Do this separately from the review of content and evidence.

- **Timing** — after the last content change, before the final build. If content changes after the check, recheck only the changed paragraphs — which paragraphs changed
  is not left to memory; `tools/grammar_baseline.py changed` decides (see **Baseline** below).
  At the stage where corrections are made on the editorial office's file (proofs), the user transfers the proposed revisions into that file.
- **Scope** — all English in the files that go out (body · abstract · titles · captions · text in tables · response letter · cover letter).
- **What to check** — preposition and complement pairing (the forms a verb, noun or adjective takes) · articles · adverb position within verb phrases · hyphenated compounds (a hyphen for a modifier
  before a noun, none when used as a noun) · parallel structure · agreement in number. Term choice and meaning are not checked, but the prepositions, complements, articles and number a term takes are.
- **Check confirmed paragraphs too.** Point out problems whether or not a paragraph is confirmed. For how changes are made, see "Approval and comparison".
- **Classification** — put each finding in one of three classes. The single test is "can you name how the original relates to the standard form".
  The standard form is standard English grammar and standard collocation (the preposition and complement forms a dictionary or grammar book gives for that word).
  - `error` — you **can name** the standard form the original departs from. Give that form in the reason. If you can name the standard form, "merely awkward" ·
    "merely less common" · "examples of use exist" are no reason to downgrade it to `style`.
  - `style` — you can say, with reasons, that the original **is also** a standard form, and you choose another form for journal or publisher convention or for smoothness.
  - `error?` (a possible error) — you think the original is wrong but **cannot name** the standard form it departs from. Do not downgrade it to `style` or drop it; state in the reason
    what is uncertain.
  - For hyphens, only a breach of the two cases under **What to check** (a modifier before a noun · use as a noun) is `error`. Other joining or spacing (compound verbs ·
    predicative position and the like) varies by dictionary and publisher, so it is `style`.
- **Output** — for each paragraph, use this document's form for proposed revisions (current text · revised text · reason, with changed strings in code spans). Show `error` · `error?`
  first for the user to decide, and show `style` separately as a group, for information only.
- **Baseline** — record the fingerprints of the text the model has actually checked in `.manuscript/grammar_baseline.jsonl`, and recheck only units not in the baseline (changed paragraphs · new paragraphs).
  Code works out what changed and compares against the source text; the model checks only the grammar of the units selected. Units, scope and settings: `project-config.md` "`grammar` — the scope of the pre-submission grammar check".
  - Only the very first baseline is recorded once, on the user's word — `init --confirm "<the user's words>"`. After that, do not run `init` again, and do not delete or edit the baseline.
  - Get the units to check with `changed --out`. The packet (the text shown and its fingerprints) is created next to the baseline file in `grammar_packets/`, named by time and computer name.
    Once every unit in a packet is decided, delete the packet — undecided units are picked again by the next `changed`, so deleting it at any time misses nothing.
  - **Record units with no findings right after checking them** with `clean --packet <packet> --ids …` (or `--all-except <flagged id …>`).
  - **Record units with findings the moment the decision is made** — if it is left as is, `resolve --packet <packet> --id <id> --keep`;
    if it is to be changed and the change has been applied, `resolve --packet <packet> --id <id> --replace <original> <revision> …`. The latter records only when the replaced text matches a unit of the current manuscript
    character for character; otherwise it shows the difference and records nothing.
  - Do not record undecided units — they come up again as changed units in the next `changed`. Only the packet's fingerprints are recorded, so if someone changed a paragraph
    while you were checking it, that paragraph comes up again too.
  - The baseline file is not a sync shared file — the sync check reports conflict copies made when two computers write to it in turn, and if a mark is lost, the unit
    simply comes up again; nothing is missed.
- **Checking candidates** — before showing the candidate table (`| ID | location | \`original\` → \`revision\` | … |`), run `verify <candidate file>` to check that the original text is at its location (file · `L<number>`)
  character for character. Rows whose location cannot be read (`not compared`) and locations without a line number (`partly compared`) produce warnings,
  and the exit code is 0 only when every row is `match`.
- **Applying** — put changes into the manuscript only after the user's instruction to apply ("Approval and comparison").
- **Avoid list** — for each `error` · `error?` expression the user decided to fix, add a row to the avoid list (`style-guide.md` "Usage").
- **Do not decide by searching for usage examples** — `style-guide.md` "Usage".

---
