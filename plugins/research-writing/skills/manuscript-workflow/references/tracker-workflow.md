# Tracking open items — file structure and life cycle

<!-- toc -->
**Contents**

- Files split by role — only one is read every session
- Finding an item takes two steps — never read a file end to end
- Item life cycle — a change of status moves the item to another file
- Triggers — a fixed set of values
- Focus — kept by the assistant
- Concurrent editing — the user may be editing the same file in another window
- Sync — several computers write the shared files
- Target and location syntax — the location table and the reverse index are built from it
- Table row format — one item per line
- Format tokens — English written, the old Korean spellings read
- Category letters of the open-item tables — set by the project
- Ending a session
- One source for the working rules
<!-- /toc -->

This structure keeps track of **what is not finished yet** in manuscript work that spans several sessions.
File names and locations differ per project — the actual names and paths (relative to the root; a subfolder such as `tracking/tracker_index.md` also works) are set by the project settings (`tracker` in `.manuscript/project.json`) or
the project guidance (`CLAUDE.md` · `AGENTS.md`, or a shared document that guidance names). This document calls the files by their **role**.

## Files split by role — only one is read every session

If everything goes in one file, it must be read end to end every session, and it soon grows past 40 KB and becomes a burden to read.
The key is **separating the index from the bodies**.

| Role | Content | When to open |
|---|---|---|
| **Index file** | Rules, standing constraints, location table (section → items), trigger table, what to do now | **Read in full at the start of every session** |
| **Pending file** | Bodies of open items | After getting the ID from the index, **only that item** |
| **Record index** | Reverse index of completion records — by section and by ID | When looking up a past decision |
| **Completion records** | Bodies of completed items. **One file per item** | After getting the ID from the index, **only that one file** |
| **Proposals file** | Proposals waiting for a decision on adoption | When touching a section a proposal concerns |
| **Literature file** | Literature library · checking the reference list | Before confirming a citation |

**Do not write the index by hand.** The tidying tool generates it from the bodies.

## Finding an item takes two steps — never read a file end to end

```bash
# Open items — what is pending now
# 1) In the location table of the index file:   ch3.md 3.2.5 -> D35 · H12
# 2) Read only that row
grep -n '^| D35 |' <pending file>

# Completed — what was decided in the past, and why
# 1) In the by-section reverse index of the record index:   ch3.md 3.2.1 -> E101 · E104
# 2) Read only that one file
cat <records folder>/E104.md
```

## Item life cycle — a change of status moves the item to another file

```
waiting / in progress / on hold  ->  applied (E<number>)  ->  done (<date>) / closed (<date>)  ->  completion record
└────────────── stays in the list ──────────────┘      └──────────────── leaves the list ─────────────────┘
```

- `applied` means the text is in the file but **the user has not confirmed it yet**. It stays in the list.
- A status that still leaves work to do, such as `done (visual check needed)`, also stays in the list.
  **A status value that contains `needed` or `waiting` means the item is open.** Write the status word first — the tools read the head of the cell.
- **The moment the user declares it confirmed is the moment to archive it.** Change it to `done (<date>)` on the spot and move it at once.
- **Proposals do not move to completion records.** For a dropped proposal, only set its status to `closed` in the proposals file;
  the tidying tool drops proposals whose status is `done` or `closed` from the list.
- Projects made before 0.14 write these words in Korean; the tools read both (see "Format tokens").

Whether the user has confirmed something is decided by `revision-protocol.md` "Approval and comparison".

## Triggers — a fixed set of values

Each item records **when to bring it up again**. Free-text values cannot be built into a table, so
choose only from **the list fixed for the project**. The list lives in the project settings.

- Needed in every project: `when working on the section` · `user decision` · `when data is available` · `before final submission` · `now`
- Different per project: conditions tied to the review and submission schedule

**Only items whose trigger is `now` appear in the "do now" section.** A project keeps the list in its settings as written —
older projects list the Korean spellings of the five, and the tools treat the two spellings of each as the same trigger.

## Focus — kept by the assistant

Focus **copies the bodies of the items** attached to the chapter you are working on **into the index file** (its section "Chapter in progress").
You then no longer need to reopen the pending file each time you move to another section.

| When | What |
|---|---|
| The user names a chapter | Turn focus on for that chapter |
| **You are about to edit that chapter's manuscript while focus is on another chapter** | Switch without comment |
| The user says the chapter is finished | Turn it off or switch to the new chapter |
| **The focus date is old and the current work has nothing to do with that chapter** | Switch or turn it off |

**Report it in one line** — `Focus on for Ch.3 (8 items attached)`.
Do not paste command lines into the reply, and do not ask the user to "turn it on".
**Do not turn it off automatically at the end of a session** — it is better for the next session to pick up the same chapter.
**Judge whether it is old from the date on the first line of the block.**

The focus block is a **copy**. To change an item, change the source (pending file, proposals file) —
anything written in the focus block is erased on the next run. An item attached to two chapters appears **in the focus of both**.

## Concurrent editing — the user may be editing the same file in another window

**Reread a tracker file right before editing it by hand.** If it differs from what you saw before but the spot you meant to change is unchanged, replace only that string and go on;
**stop and tell the user only when that spot has changed or is gone.**
If any file changed after the tidying tool read it, the tool **saves nothing**, rereads from the start and tries once more.

**Five rules — the order and the form of the commands are the safeguard.** Two sessions that take the next number at the same moment can
overwrite each other's completion record. Rule 2 below and the last paragraph are enforced with tools and a hook.

1. **Creating is the check.** Create a new file with **a single command that does not overwrite**, such as `(set -C; cat draft > target)`.
   Checking the name first and writing in a separate call is not a check. The Write tool overwrites an existing file even if this session does not know about it.
2. **The tool assigns the number; write that number into other documents only after the file exists.** Create a completion record with
   `python tools/new_record.py <body file>` — the number the tool assigns goes into the `E?` of the body's first line `# E? — <title>`,
   and if that number already exists the tool moves on to the next one. Write references **using the number the tool prints**. References written
   the other way round must all be traced back and fixed if creation fails.
   **New open items work the same way.** Give `python tools/new_pending.py <row file>` a one-line file whose ID cell is written as `<letter>?`, such as `D?`;
   inside the write lock the tool rereads the file, fills in the next number, appends the row to the bottom of that letter's table and prints the number. The scope is the letter
   tables of the pending file and the proposals table (`_config.allocation_scope`); items of the literature file and branch numbers (`D35-1`) are entered by hand.
3. **Change existing files only by string replacement (Edit).** Rewriting a whole file with Write erases other sessions' changes.
4. **Right before deleting or moving a folder, check `find <folder> -newer <file seen at survey time>` in the same command.**
   If the output is not empty, leave out only those files, go on, and tell the user.
5. **Do not stop merely because another session is open.** If you see traces of another session (modification times after your survey), reread
   that file and go on; do not ask the user whether the other session has finished. Stop only when the spot you meant to change has changed.
   Run the tidying tool regardless of the number of sessions — if the tool refuses to save (exit code 4), run it once more, and if it refuses again, report it in one line
   and move on to the next task.

**Write lock — held only while writing.** Tools that read and rewrite shared files (tidying · index · open-item numbering tool · `replace_once`) hold one lock
(`_sync.WriteLock`) in the per-computer state folder for the length of that one run. It is an operating-system lock, so it is released by itself if the process holding it dies,
and it is never held for a whole session. The tidying tool's order is "lock → read → compute → check everything for changes since reading → save". The hook only waits briefly
for the lock to be released before an Edit or Write of a shared file; it does not block. The completion-record numbering tool does not take the lock — it secures a number by
"fail if it exists". **While holding the lock, do not call another tool that takes the lock as a child process** (they wait for each other).
What the lock cannot stop — Edit and Write themselves (the hook ends before the Edit, so it cannot hold the lock) · hand edits in an editor · apps without hooks · other computers ·
old versions of tools that do not know about the lock. For these, the check before saving and the checks in "Sync — several computers write the shared files" below back it up.

**Write the completion record once, after the user confirms.** During repeated revisions, neither create nor change completion records,
and hold back status changes in the tracker files as well. Keep the running account of the revisions in the conversation. If the session ends without confirmation, write it once at that point
with the status `applied (awaiting confirmation)`. Updating the record on every revision keeps the window for number collisions open.
**Never reuse an ID.** The IDs of open items (the letter tables of the pending file · the proposals table) are also assigned by the tool (rule 2) — do not pick a number and enter it by hand.

**The layer the harness enforces — the hook.** The rules depend on the model's memory, so there is one more layer. The hook script `guard_write.py`,
at PreToolUse, refuses a Write that would overwrite an existing `records/E<number>.md` or the generated file `tracker_records_index.md`
(it does not block creating a new file or an Edit); refuses an Edit or Write that adds a new open-item ID row by hand (when the numbering tool is in the project · the scope is
the same as the numbering tool's · reviving or moving an ID already known passes); runs the guard and snapshots of "Sync — several computers write the shared files" below before and after Edit · Write · Bash · PowerShell; and after a write
reports in the same turn if a table row in a tracker file is broken ("Table row format — one item per line").
It is registered in two places — `hooks/hooks.json` in the installed plugin (the main one) and the project's `.claude/settings.json` (a backup, made by `new-manuscript`).
To add it to an existing project, or to catch up after the canonical copy changes, use `new-manuscript/update_tools.py` — how it judges, replaces and treats the hook registration is in
`project-config.md` "New projects are made by the `new-manuscript` skill".
In apps that do not run hooks, only the rules remain.

## Sync — several computers write the shared files

When several computers use a project in a cloud sync folder (Google Drive and the like), **a version written on top of a mirror that has not caught up is uploaded later and silently overwrites
the other computer's work.** "Reread right before writing" cannot prevent this when the copy being read is itself stale, and no file inside a stale copy can
prove that it is stale. So there are three layers in code — they use no model tokens; the model's only job is to pass ERRORs on to the user and
get confirmation (WARN is only reported, and work goes on). The engine is `tools/_sync.py`, the command is `tools/check_sync.py`, and the hook is `guard_write.py pre|post`.

**Principles.** ① A structure that turns silent overwrites into **visible conflicts** (one file per item · exclusive creation) is the strongest — completion records use it.
② **The causing side is estimated, the damaged side is exact** — the check before a write is an estimate (time · gaps · conflict copies), so it is closed by the user's confirmation; on the damaged side, invariants
(IDs do not disappear · record numbers are continuous and never shrink · generated files match their sources · lines I wrote are still there) catch the damage exactly.
③ Recovery works **without** the Drive web interface — snapshots after writes. ④ The checking engine lives in **each computer's installed copy** (plugin hook · `update_tools`), and the project copy
is a backup — because a stale mirror does not have the new guard yet either. ⑤ The core checks run without settings (on defaults alone).

**Checks.** The levels are ERROR (blocks writes to shared files — released only by the user's confirmation) · WARN (report it in one status line, accept it with `--accept-warn`, then go on — does not block) · INFO.

| Check | Level | When | What |
|---|---|---|---|
| S1 freshness | WARN | start · `update_tools` | The latest change to the shared files is older than `stale_days` (default 2) — a stale mirror or a gap in work |
| S2 record continuity | ERROR | start · write | A gap in completion-record numbers (except `known_gaps`), or the highest number is lower than this computer has seen |
| S3 reference integrity | ERROR / WARN | start · write | ERROR when a source a generated file points to is missing (record index → record file · index file → open-item ID); WARN when a hand-edited file points to a record above the highest number. In the index file only the **ID cells** of the generated blocks count — the last cell of the location table and the trigger table, the first cell of the do-now table, and the item heading in the focus (`#### <ID> —`). Labels of other documents inside body text such as copied notes (`D4` of a revision plan, `A40` of another project) do not count, so the notes need not be rewritten. If the shape of a block cannot be read, the comparison is skipped with a WARN (rebuild it with the tidying tool). Defined in one place, `_config.list_block_ids` |
| S4 generation stamp | INFO / WARN / ERROR | start | When the stamp of the index file or the record index differs from its sources, tells the **direction** — a source changed **after** generation (forward) is an INFO `to do` that prompts regeneration (the normal state during a session · not a sync warning · status line OK). ERROR (backward · overwrite) when a source has gone back to an older version this computer has seen and its modification time is also earlier than the generated file's. WARN when it is an older version but its modification time is later (it may have been reverted) · the content differs although nothing was edited after generation (an older version overwrote it, or only the generated file arrived first) · a record that existed when the record index was made has changed · records have decreased |
| S5 conflict copies | WARN | start (everything) · write (target folder) | `name 2.md` · `name (1).md` · `conflicted copy` (only when the original is in the same folder) · `__pycache__/` and the archive folder (`archive/`, or its old default name) excluded |
| S6 loss report | WARN | start · `--damage` | The share of **lines this computer wrote** that still survive across the shared files is below `survival_pct` (default 70). Documents that get overwritten (`checkpoint` · `rewrite_ok`), generated files and anchor lines (block markers · generation stamps · `| ID |` header rows — structure the tools own, rewritten by the format migration) excluded |
| S7 ID monotonicity | ERROR | start · write | An open-item, archived, proposal or literature ID this computer has seen has disappeared — lists the missing IDs |
| S8 drive | INFO/WARN | start | Whether the sync program's process is running |
| S9 format | ERROR / INFO | start · write (ERROR) · start (INFO) | ERROR when the tracker files mix English and pre-0.14 Korean anchors — Drive has not caught up, or a tool from an older plugin version wrote here (it blocks shared writes like the other ERRORs; the fix is `update_tools --apply`, which is idempotent). INFO when the project still uses the Korean anchors (not yet migrated). See "Format tokens" |
| S10 before update | refuse / report | `update_tools --apply` | Rechecks S1 · S2 · S5. On ERROR (S2) it refuses to apply the canonical copy (`--sync-override` only after the user's confirmation); WARN (S1 · S5) is shown and the update goes on — Drive snapshots before and after the update and the hash comparison (only older canonical versions are replaced) are the safety net |

**When.** At the start of a session, run `<py> -X utf8 tools/check_sync.py` — one status line (`Sync OK · E12 · last change … · last drive snapshot <computer> … · this computer <computer>`) and
the warnings. **If there is an ERROR, show it to the user and get confirmation before writing shared files.** Once the user confirms, close it with `--ack "<the user's words>"`
(the words are kept in the record · expire after `ack_hours` · the missing IDs and lines are accepted as legitimate deletions) — **never run `--ack`
without the user's confirmation.** **If there are only WARNs, treat the project as synced** — note them in the status line, do not repeat them in later replies, and with `--accept-warn` align the baseline
(the S6 register of written lines · the records and IDs seen for S4 · S7) with the current state, then go on. `--accept-warn` needs no words and refuses
while an ERROR is open — the only way to close an ERROR is `--ack`. On every write the hook reruns the cheap checks (S2 S3 S5 S7), and at the end of a session the tidying tool's `--apply` calls `--end` (boundary snapshot · retention cleanup).
**A confirmation is valid per warning key (check + target number · ID) for `ack_hours`** — it does not block again while the same condition remains in the generated file or folder,
so after confirmation the tidying tool, which rebuilds that generated file, can run. When the condition changes (another number or ID — a new key) it blocks again, and the start check shows a confirmed
ERROR as `[confirmed …]` and exits with code 1. The decision lives in one place, `Sync.ack_of` · `Sync.blocking`, shared by the hook, tidying, index and new-item tools.
The tidying tool does not skip S3 on the index file by itself — when a source has been overwritten by an older version, the index file is the only evidence of the missing IDs, and the tidying tool rebuilds
the index file from that source and writes the pending file too.

**Snapshots and recovery.** Shared files are derived from the settings — tracker files · `checkpoint` · completion records · `*.md` in the manuscript folder · `sync.shared_extra`.
Snapshots go **locally** (`~/.claude/sync-state/<project>/snap/`) on every write, and to **Drive** (`sync.snapshot_dir`,
default `archive/tracker_backup/`) at session boundaries and before and after tidying and `update_tools`. The name `<UTC>_<computer>_<path(/→__)>_<hash8><ext>` differs every time, so another computer cannot overwrite it; the same hash
is not made twice; and snapshots are byte for byte, so line endings are kept. **Retention (session start · end)** — for each file the latest `snapshot_min` (10) are always kept;
this computer's own snapshots older than `snapshot_days` (30, twice that locally) or beyond `snapshot_max` (Drive 20 · local `snapshot_max_local` 100) are deleted oldest first,
and other computers' snapshots older than `snapshot_days_others` (90) are deleted. A file that does not change keeps only one, so the total settles within the number of shared files plus the per-file cap for files that change often.
Restore with `--restore <file> [--at "YYYY-MM-DD HH:MM" | --hash <8 chars>]` (the current version is kept before restoring) · list with `--snapshots <file>`.
Merging (which rows of which version to keep) is a judgement, so it is not automated.

**File-name normalization — macOS.** macOS (Google Drive mirror · HFS+) stores Korean names in NFD, so `os.listdir` results differ from the NFC strings in settings and text.
Opening files works, but **string comparison and import go wrong** — Python's import compares against the folder listing as it is, so `from _location import …`
stops with `ModuleNotFoundError`. Therefore ① `_config` registers a finder that accepts modules with NFD names — **a tool that uses a module with a Korean name imports `_config`
first** ② tools normalize to NFC with `_config.nfc` when they compare names, paths or lines or use them as keys (snapshot names · the set of shared files · hashes of written lines)
③ the state folder name `<name slug>-<root path hash8>` (in one place, `_sync.project_id`) also hashes the root path after normalizing it to NFC — the hook receives the NFC path from standard input,
and a tool run from a shell receives the file system's NFD path, so otherwise the folder splits in two and `--ack` does not reach the hook. A folder made under the old definition is, the first time it is met,
moved to the new name or merged into the new folder (snapshots · written lines · IDs · confirmation records are combined; of the highest numbers seen, the larger is kept).

**Generation stamp.** An HTML comment on the second line of a generated file — deterministic, so two runs give the same result.
Index file `<!-- generated-stamp <pending>=<hash16> <literature>=<hash16> <proposals>=<hash16> -->` · record index `<!-- generated-stamp records/ n=<count> max=<max> sha=<hash16> -->` (older files use the Korean stamp word — read too).
A differing stamp alone cannot tell "the source was edited and not yet regenerated" from "an older version overwrote a newer one", so S4 looks at the **direction** —
for the index file it uses the order of the stamped version and the current version in this computer's snapshot history, or, if that is not enough, the modification times of the source and the generated file (kept by the sync service).
For the record index it recomputes the fingerprint up to the stamp's highest number to tell whether only new records were added (forward) · existing records changed · records decreased.
Forward only needs regeneration, so it is not a sync warning but a single `to do` line, and the status line is OK — the tidying tool at the end of the session clears it.
`new_record.py` rebuilds the record index after creating a record (turn this off with `--no-index`), so forward on the record-index side does not arise.

**The baseline for written lines is "the version this computer saw right before writing".** The difference after a write (deleted lines leave the register, added lines join it) is taken against the snapshot whose hash `before_write` · a session boundary · the previous write
recorded in the state (`seen.json`) — not against the latest snapshot by time. If an older version from another computer was snapshotted later, deleted lines would stay in the register and S6 would
raise false alarms. If the previous version is unknown, only snapshots made by this computer are used.

**Every write path is covered.** Edit · Write go through the hook (before — overwrite refusal · guard · snapshot of the previous version; after — snapshot · fingerprint · written lines). For Bash, afterwards
the fingerprints of shared files (modification time · size) are compared and only changed files are processed; beforehand, the command is blocked only when an unconfirmed ERROR exists and a shared path appears in the command.
**To change a shared file from Python, use `_sync.replace_once(path, old, new)`** — it replaces only when the target occurs exactly once (0 or 2+ occurrences raise ValueError —
this is the optimistic concurrency check) and also handles line endings, snapshots and records. Tidying · index · new item (completion record · open item) · `update_tools` check at start and refuse on ERROR.
Outside the hook — for hand edits in an editor and edits in apps without hooks, the snapshot at the next session start and S6 · S7 catch the damage.

**Hook placement.** To find the project, the hook searches for the settings file **walking upward** — from the target file's path for Edit · Write, from the cwd for Bash — and ends at once if there is none,
so other folders are unaffected. When both the installed hook and the project hook exist, the same tool call is processed only once. Internal exceptions are let through and reported
on stderr (fail-open) — only an unconfirmed ERROR blocks.

**Settings.** `tracker.checkpoint` (the handoff file — it is overwritten, so S6 skips it) · `sync.shared_extra` · `snapshot_dir` · `conflict_patterns` · `exclude` ·
`stale_days` · `snapshot_days` · `snapshot_min` · `ack_hours` · `known_gaps` · `rewrite_ok` · `survival_pct`. Defaults live in one place, `_config.py`.
The computer name is the hostname and can be changed with the first line of `~/.claude/sync-state/computer_id`. The state folder is **outside** the sync folder and
can be moved with `SYNC_STATE_HOME` (for tests and previews).

**What people must do.** When switching computers, close and open only after seeing that the sync program is up to date **at both ends**. Run the check at the start of a session and
show ERRORs to the user. Do not write shared tracker files from an app without hooks.

**Last resort — the sync service's version history.** A version with no snapshot (from before the sync guard was in place) is fetched from the file version history on the service's web site —
without opening the file, download from "Manage versions" the version from **just before** it was overwritten, check its line endings, put it back in place byte for byte, and
register it with `check_sync.py --after-write <file>`. Decide which version is right by comparing the sets of IDs and the date markers.

**Remaining gaps.** On the causing side, "staleness" is an estimate without a second channel, and S1 misses short staleness within a day. Hand edits and apps without hooks are outside the hook.
The one-file-per-item structure (open items) only narrows the damage to one item; if two computers change **the same item**, that item is still overwritten.

## Target and location syntax — the location table and the reverse index are built from it

The `**Target**` of a completion record and the `Location` of an open item or proposal are split into (file, section) pairs by the same syntax (`tools/_location.py`) and become the by-section reverse index of the record index,
the location table of the index file, and the focus. All three use the same definition, so what is found in one is found in the others.

- **Write a file as its full path from the root, in backticks** — `` `manuscript/results.md` `` · `` `manuscript_src/ch3.md` ``. Chapter and reference
  files inside the manuscript folder may be given by name alone (`ch3.md`). A folder ends with `/`. The folder of a path written earlier is the base for names that follow
  (`` `manuscript/intro.md` · `results.md` ``). Every path written in a cell is a location — paths after a "see also" label count too.
- **Put sections right after the path** — `①`–`⑳` (followed by `a`–`z`) · `¶2` · `§3.2.1` · `Figure 3` · `Table 1` · `「section name」`. Separate several sections with `·`;
  write a range with `–`, as in `⑪–⑮`. A bare number joined after a section mark by `·`, `,` or `and` inherits the preceding mark (`Figure 5 · 6`).
  Figure numbers may be flat (`Figure 3`) or chapter-numbered (`Figure 3-2`). An identifier after a code file is a section of that file
  (`` `build_tpl.py` `abstract_src` `` · `` `Chapter.fixed_size` ``). Write identifiers in backticks — a plain word without them counts only
  as a list item (after the file or `·` · `,`, before `·` · `,` or the end), so a remark after a code file is not taken for a section.
- **When you give only a scope without a file**, write one word, such as `all`.
- Add a project's own section notation with the setting `tracker.section_markers` (a list of regular expressions). Files to leave out of the record index go in
  `tracker.record_index_exclude` (globs; a folder ends with `/`) and `manuscript.output_pattern` (build output) —
  this exclusion applies only to the record index, not to the location table (an open item's location is the actual place to change).
- A name that cannot be resolved (a deleted file · outside the project) becomes a row as written, without a warning. A warning is raised only **when the cell is empty, or has a section mark
  with no file to attach it to** — for an open item's location, by the tidying tool on every run; for a completion record's target, by `new_record.py` when it creates the record.
  Old records are checked only with `index_records.py --check-targets` (confirmed records are not changed, so warning on every run would be permanent noise).

```text
journal manuscript   `manuscript/results.md` ③ · ④b · `figures/INDEX.md` Figure 3
                     → results.md ③ / results.md ④b / figures/INDEX.md Figure 3      (inside the manuscript folder, names are shown relative to it)
dissertation         `manuscript_src/ch3.md` §3.2.1 · `build_tpl.py` `abstract_src` · Figure 3-2 caption
                     → ch3.md §3.2.1 / build_tpl.py abstract_src / build_tpl.py Figure 3-2
```

## Table row format — one item per line

An item in a tracker file (pending · proposals · literature · archive table) is **one line**, `| ID | … |`. To write `|` inside a cell, write `\|`.
If a line that does not start with `|` sits directly under a row, GFM draws it as a one-cell row, and the tools, finding no ID, do not see it.
Such a line is the trace of a replacement that inserted `\n` and **split a row into two lines**; if the row is archived in that state, only the tail stays in the pending file.

The tools guard this in three layers. The syntax is defined in one place in `_config.py` (`table_problems`), and the tidying tool, sync and the hook use it.

- **Writing side** — when `_sync.replace_once` changes a `.md` file and the table defects (orphan lines · cell count · trailing `|`) **increase**, it does not write and raises an error.
  Defects already present only produce a warning on stderr. For a deliberate replacement, pass `check_tables=False`.
- **Reading side** — the tidying tool's diagnostics warn about defects with file and line number. A completed row with an orphan line directly below it is **not archived**; the tool warns,
  and if the archive table contains a line that is not a row, archiving is skipped. The separator line under the archive table's header is preserved, and restored if missing.
  A `|` line whose first cell looks like an ID but that cannot be read as an open-item row (a decorated ID `| **A1** |` · a row outside a category section or before the `| ID |` header) also gets a warning —
  such rows appear neither in the index file nor in the sync comparison (S3 · S7). The shape of an ID is defined in `_config.row_like_id`.
- **Hook** — after Edit · Write · Bash · PowerShell, if a tracker file still has defects, it reports them in the same turn (without blocking).

**When a warning appears.** Join an orphan line back before the trailing `|` of the row above (it was one row), or delete it if its content is already in a completion record or the archive table —
decide which by looking at the row with the same ID in the archive table and at the completion record. For a cell-count mismatch, change the `|` inside the cell to `\|`.
`|` lines whose ID cannot be read (detail tables in the literature file and the like) are not checked.

**To avoid causing this**, do not pass code that changes a file as a command string when it contains backslashes (`environment.md` "Handling files — details").

## Format tokens — English written, the old Korean spellings read

The strings the tools find in or write into project files — block markers, generation stamps, column names, record fields, status words,
the `now` trigger, the focus line, placeholders and the grammar-baseline keys — have one table, in `tools/_config.py`, with an English spelling
and the spelling of projects made before 0.14 (Korean). **The tools write English and read both, forever.**

| Kind | Written |
|---|---|
| Block markers | `standing-F` · `location-table` · `trigger-table` · `now` · `focus` · `archive-body` · `archived-list:X` · `H-locations` |
| Generation stamp | `<!-- generated-stamp … -->` |
| Columns | `Item` · `Location` · `Trigger` · `Status` · `Note` · `Proposal` · `Basis` |
| Record fields | `**Completed**` · `**Target**` · `**Status**` |
| Status words | `applied (awaiting confirmation)` · `confirmed` · `closed` · `done` · `waiting` · `needed` … |
| Trigger | `now` and the four shared defaults |
| Focus line | `**Working chapter** chN` |

Projects made before 0.14 spell all of these in Korean. The older spellings are listed, each with its meaning in English, in the legacy section
of `tools/_config.py` (`LEGACY_SPELLINGS` — together with the old default file names `LEGACY_DEFAULTS` and old tool names `LEGACY_TOOL_NAMES`).

- **The format of a project is what its anchors say** — the markers, stamps and `| ID |` header rows of the tracker files (`_config.project_format`). There is no settings key.
  The writing tools (tidying `--apply` · index · new items) refuse a project whose anchors are still Korean or mixed (exit 5); diagnosis keeps working.
- **Migrating an older project** — `update_tools.py <project>` previews it; with `--apply` it updates the tool copies, rewrites the anchors (`migrate_format.py`: marker lines,
  stamp lines and the known column names of `| ID |` header rows — unknown column names stay) and rebuilds the generated files. It is idempotent, takes the write lock,
  and keeps Drive snapshots before and after. **Update the plugin on every computer first** — an older tool that meets English anchors rebuilds the record index with empty
  fields and adds a Korean stamp (S9 then reports the mix).
- **What the migration leaves as written** — completion records, archive rows, status and trigger values, headings and prose, the grammar baseline and `project.json`.
  These are history or people's words; the tools read both spellings of them.
- **Until a project is migrated, write values in the spelling its files already use** (status words, triggers, record fields) — its tool copies are still the older ones.
  After migrating, write English. The trigger list in the settings stays as the project wrote it; the two spellings of a default trigger count as the same trigger.

## Category letters of the open-item tables — set by the project

In the pending file each `## X. <title>` section is one table; the letter `X` must be in the setting `tracker.movable_prefixes`, and row IDs start with that letter
(`A12`). This format is all the tools look at — **the number and meaning of the letters are up to the project.** The initial default is four (A waiting on an outside condition ·
B to fix when a later chapter is settled · C formatting · D style), but "when" is already covered by the trigger column and "where" by the location column, so a project
where the letters have nothing to do may keep A alone.

**Reducing the letters.** First archive the closed rows with the tidying tool's `--apply`; then move the open rows, **with their IDs unchanged**, to a remaining section and delete the title and the empty table of the section being removed.
**Keep** the letter list in the settings and the `<!-- archived-list:X -->` block — so the sync check (S7) keeps recognising old IDs and archive-trace lines
keep being made (the block is found anywhere in the file). New items get numbers under the remaining letters; a removed letter is never issued again.

**When there are zero open items.** If the tidying tool reads zero open items, it first checks the table structure. If the pending file has category sections, the category sections and the proposals file
have a `| ID |` header, and there is neither a line that looks like a row but cannot be read nor a defect in those tables, the tool treats it as **truly zero** (the last row was deleted or everything was archived) and
rebuilds the index file's location table and trigger table with headers only, the do-now section with its notice text, and an active focus with zero items — so the index file does not keep pointing at missing IDs
and leave an S3 ERROR. If anything is off, it treats it as a **read failure**, warns with the reason, and leaves the index file's generated blocks and generation stamp as they are —
it does not delete remaining items because of a format problem, and by not stamping it lets S4 keep reporting that the index file is stale. Fix the reason and run it again.

**Keep only the current state and what remains in the notes cell.** Put the running history under the table in `### <ID> details`, and send pieces closed by a decision to completion records.
Notes are copied verbatim into the focus block, so as history piles up, the index read every session exceeds its size limit.

## Ending a session

Do not force a fix for what cannot be fixed now (an unsettled schedule, an unsettled later chapter, page numbers and the like); record it.

- Newly found open items → register them at the bottom of the matching category table in the **pending file** with `tools/new_pending.py` (the tool assigns the number — rule 2 of "Concurrent editing — the user may be editing the same file in another window").
  Write the file and the section together in `Location` (the location table is built from this value — "Target and location syntax — the location table and the reverse index are built from it" above), and use one of the fixed values for `Trigger`.
  **Do not write bodies into the index file** — anything written by hand in the auto-generated parts is erased.
- Items you finished → create a new completion record file and regenerate the record index. **Move the original item to the archive table.**
  Keep the original ID when moving it. Do not leave completed items in the open-item tables.
- **Do not rewrite files from scratch.** Keep existing items and IDs; only add and update.

Finally, run the tidying tool. It does not fix what needs a person's judgement (duplicate or missing IDs, index mismatches, unknown status values,
an index file over its size limit); it **only warns**. Running it twice must give the same result.

## One source for the working rules

Keep the body of the project rules in one place. If an existing project's canonical copy is `CLAUDE.md`, keep it,
and when Codex needs an `AGENTS.md`, make it a thin entry guide that tells the reader to read the canonical copy and the procedure document.
Do not copy the same manuscript rules into both. Preserve the user's instructions in an existing `AGENTS.md`.

**When the user names a file, they mean that file.** Do not reinterpret a request to change `AGENTS.md` as a change to
`CLAUDE.md`. If the shared canonical copy needs a change, first separate the actual target and scope.

**Write only rules. Send history to completion records and open items to the pending file.**

| Kind | Test | Destination |
|---|---|---|
| **Rule** | Does it change what I do now? | The shared rules document the project names |
| **History** | Is it why something came to be — a past path, a discarded method, the result of a one-off check? | Completion record |
| **Open item** | Is it work not yet finished? | Pending file |

- **Delete a discarded method instead of keeping it as "do not use".** The completion record takes what was deleted.
- **If a general rule already prevents it, do not repeat the special case.**
- **Do not split the same history across two sections.**
- **A state found by a check at one point in time is not a rule.** It soon goes stale. Write it in a completion record with the date.
