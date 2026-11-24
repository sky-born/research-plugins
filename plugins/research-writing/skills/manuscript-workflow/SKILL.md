---
name: manuscript-workflow
description: Shared working rules for writing academic papers and dissertations — style rules and expressions to avoid, hedging by evidence grade, rules for confirming citations, the protocol for proposing revisions and for the user's confirmation, the structure for tracking open items, and figure rules. Use it when writing or revising manuscript sentences, when handling reviews and revisions, when checking grammar before submitting a manuscript or a response letter, and when organising the hand-over between sessions. Shared by Claude Code and Codex; project-specific files, paths and domain facts come from the applicable AGENTS.md · CLAUDE.md and the procedure document they name.
---

# Shared rules for manuscript work

**This is about "how to work".** What a project covers — chapter layout, file names,
domain facts, citations it must not use — is in **that project's guidance and procedure documents**.
Follow the host's instruction priority and the user's latest instructions; project rules come before this shared skill.

## Check first

1. **Have you read the project documents this task needs?** The project guidance's reading guide (§2 of a generated `CLAUDE.md`) names them for each task,
   the procedure document (`procedure`) included, and none of them is loaded by itself. If the base root is unconfirmed, confirm it first with the `manuscript` entry procedure.
2. **Which project is this?** Sibling folders may hold other manuscripts.
   A different folder is **a different paper**. Never move sentences from one to the other.
3. **Before changing a manuscript file** — find the user's instruction to apply it in this turn's message.
   Without one, do not change the file; only propose (`references/revision-protocol.md`).
4. **Is this a review only?** "Review it", "check it" and "take a look" are read-only — being able to open a file is no permission
   to change it, and neither the manuscript nor the tracker files are changed.

## Reference documents — read only the one you need

| File | When |
|---|---|
| `references/revision-protocol.md` | **Always before changing manuscript sentences and before submitting a manuscript or a response letter.** Role boundary, the user's confirmation, how to present proposed revisions, paragraph-by-paragraph review, title and caption review, critical review mode, the pre-submission grammar check |
| `references/style-guide.md` | When writing or polishing sentences. Tense · sentence structure (semicolons · gapping · conjunctive adverbs) · abbreviations · consistent terms, plus expressions to avoid and their replacements |
| `references/evidence-hedging.md` | When describing observations, interpretations and causes. The hedging table by evidence grade |
| `references/citation-rules.md` | When adding or confirming a citation |
| `references/figure-technical.md` | When making figures or putting them into a document. Transparent backgrounds · what figures must not carry |
| `references/build-technical.md` | **When writing or changing a docx build script, and when verifying its output.** Output that opens without prompting · field caches · page-number slots and overflow in the table of contents · keeping template parts · the self-check after a build · caption style |
| `references/tracker-workflow.md` | When registering or archiving open items, when ending a session, and **when another session uses the same folder** (the five concurrent-editing rules · write lock · tools that assign record and open-item numbers · the hook that blocks Write · the target · location syntax · format tokens, English and the older Korean spellings) |
| `references/environment.md` | When deciding whether the shell reaches a folder, **when writing paths or environment values into a document**, write scope, communication rules |
| `references/project-config.md` | When adding the tools to a new project. The `.manuscript/project.json` schema |

**Three of them apply almost always** — `revision-protocol` · `style-guide` · `evidence-hedging`.
Read them first for any work on manuscript sentences.

## The three rules broken most often

They are in `references/revision-protocol.md` "Approval and comparison": only the user declares something confirmed ·
every proposed revision shows the current text directly above it · read the neighbouring paragraphs before revising one.

## Project settings

The values the tools need to fit a project (chapter list, tracker file names, trigger values) live in
`.manuscript/project.json`. **Without it the tools run on defaults** — the schema and how to set it up are in
`references/project-config.md`, and the files to copy are in `templates/`.
