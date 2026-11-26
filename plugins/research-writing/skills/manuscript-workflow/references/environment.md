# Environment and communication rules

<!-- toc -->
**Contents**

- Whether the shell reaches the folder depends on the environment — check this first
- Keep environment facts apart from invariant facts
- Communication rules
- Write scope — inside the open project folder
- Handling files — details
- Finding source files
<!-- /toc -->

## Whether the shell reaches the folder depends on the environment — check this first

**What varies is the execution environment, not the computer.** Even on the same computer, the tools of Claude Code and Codex, the connected folders and the write permissions differ. Do not assume from the product name whether access is possible.

| Environment | Shell | Folder access |
|---|---|---|
| Claude Code (desktop · terminal) | The Bash, PowerShell or other tools currently provided | Check the real path and permissions of the connected working folder |
| Codex (app · CLI) | The execution and file tools currently provided | Check the working root and the permitted write scope |

**How to tell** — read the session's tool descriptions and the connected working root, then check the marker file in the base folder read-only. Resolve paths as relative locations from the project instructions and settings. Do not apply `/sessions/...`, `~/mnt/...` or Claude cache paths to another environment as they are.

**Check execution limits and packages in the current environment.** Follow the tool descriptions or the results of a read-only check for time limits, network, installed packages and file-change features. If saving a file works by staging, compare the latest modification time and content before saving. In other environments, apply the same protection with the editing tools actually provided.
Do not move files or hand the work to another execution environment to get around a permission denial.
Permissions of APIs and connected tools, and shell and file-system sandboxes, each apply separately. Do not read the fact that one tool can reach a file as write permission for another tool.

**Replace `python` in command examples with the Python 3 interpreter you have actually confirmed.** Check which of `python`, `python3`, `py -3` or an interpreter named by the host is available now. Use `-X utf8` in environments that need Korean output. Read Bash line continuation and PowerShell environment variable syntax to match the current shell.
Find skill tools from **the parent folder of the `SKILL.md` you actually read**, and do not guess a version in the cache.

**Do not hard-code an interpreter name in files a tool generates.** If a generated file writes `python` or `python3` as is, it is right on the computer that made it and wrong on the computer that reads it. In the command position, use the placeholder **`<py>`**, and say on the same line or right next to it what to replace it with — Windows `python` · macOS `python3`.
**Choosing one by looking at the OS at generation time is not a solution.** The same file would then flip its content every time it moves between computers, the same problem as leaving line endings to the OS default. The same applies to a tool's usage strings.


## Keep environment facts apart from invariant facts

**The same document is read and edited on several computers.** If you write the facts of the computer you are sitting at into the body as they are, they become false on another computer, and editing them there makes them false in the other direction. Split the statements in a document into two kinds.

| Kind | What | Where |
|---|---|---|
| **Invariant fact** | True when read on any computer — command names, procedures and their order, concepts, rules, what is done and why | Write it in the body as it is |
| **Environment fact** | Changes when the computer, account or execution environment changes — paths, drive letters, the `$HOME` value, the interpreter name (`python`/`python3`), whether the shell reaches the folder, whether credentials exist, environment variables injected into the process | Do not write the value in the body. Handle it in one of the three ways below |

**Handle environment facts in this order. The higher ones are better.**

1. **Turn it into discovery** — do not write the value, write **how to find it**.
   This is best because a new computer needs no change to the document.
2. **Put a list of candidates in a settings file** — if a tool reads the value, keep the candidates as an array and have it use the first one that exists. A new computer **adds** one line.
3. **One line per computer in a table** — only when the two above do not work. There is **one** table per document.

**Do not delete existing lines.** They are for other computers, and that a line does not fit the current computer does not mean it is wrong. For the same reason, do not rewrite the body to fit the current computer.

**Attach where it was measured to anything measured.** Not "confirmed" but
"checked on <computer> (<date>)".
Leave a computer you have not measured **unconfirmed** — do not fill in the cell with a guess.

**When a command fails on one computer**, changing the command in the body to fit that computer is the last resort.
First see whether it can be moved to number 1 (discovery).

## Communication rules

- Reply in the language and register the user or the project guidance sets. Write the manuscript in the language the project sets.
- Separate guesses from confirmed facts. Do not write what is uncertain as if it were certain.
- Do not invent terms. Prefer expressions in common use in the field and the literature.
- Be concise. Cut unnecessary explanation and wordiness.
- After the work, summarize the changes and the verification results.
- Accept abbreviated chemical formulas and compositions as the formal notation.

---

## Write scope — inside the open project folder

- **Limit writing to inside the project folder you are working in.** Everything outside is read-only by default.
- **To write outside, a user instruction or the applicable project instructions must give the target and scope.**
  Also check the real write permission of the tool. Do not edit the rule files first to gain a permission.
- **A sibling project folder belongs to someone else's project.** Being under the same parent folder does not mean permission.
  You may read its material for reference, but do not create or edit files there.
- **The tool repository (the source of plugins and skills) is an exception.** Open it only to change the shared rules or the tools themselves.
  Do not put manuscript content in it.
- **Send temporary files to the scratchpad.** Do not clutter the project folder with temporary output.

---

## Handling files — details

- Files the user provides or names are read-only by default.
  Only reading, text extraction, rendering for internal review and non-destructive analysis are allowed.
- Do not accept, reject or delete tracked changes, comments or strikethroughs in the original.
  They may have been left on purpose, so clean them up **only on an explicit instruction.**
- Do not use recursive deletion, wildcard deletion, git clean or a destructive reset.
  Delete only temporary files the assistant made, and only when the user asks explicitly.
- **If code that modifies a file contains a backslash, do not pass it as a command string** — create a script file with Write and run that file.
  The Bash tool of Claude Code reduces `\\` in a command string to `\` once. This holds inside a quoted heredoc (`<<'PY'`), `-c` and `printf` too,
  so `'\\n'` becomes a real line break and splits a row of a tracker table into two lines. A short command with no backslash may be used as it is. For handling a split row, see `tracker-workflow.md` "Table row format — one item per line".
- **Compare file names in NFC, open them by the listed name.** macOS, and Google Drive mirrors on it, return Korean names in NFD, while settings, indexes and
  typed text hold NFC — a one-off script that lists a folder and compares names, or filters paths by a Korean string, silently misses them.
  Normalize both sides with `unicodedata.normalize('NFC', …)` before comparing, and open a file by the name the listing returned (Linux and NTFS do not open
  an NFD file by its NFC name). A shell whose locale is C (no `LANG`) prints Korean as `??` from tools other than Python — read such output through Python with `-X utf8`.

## Finding source files

A manuscript folder often holds files with several versions.

- Search for the manuscript file and the response file separately.
- Ignore Word owner files that start with `~$`.
- Choose the one with the highest version in the file name (`_v6` > `_v4`), and use the save time only to break ties.
- If the choice is ambiguous, do not guess — **report the candidates and stop.**
- Always cite from the original file. Do not name a cache, an extract, a PDF or a page image as the source.
- If text the user gave in the conversation is newer than the saved file,
  use that text as the base and **report the discrepancy.**
