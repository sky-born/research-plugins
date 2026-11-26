# Working rules — research-plugins

This is the **source repository** of a skill marketplace shared by Claude Code and Codex.
It lists what to follow when you open this folder and work in it. Installation and usage are in `README.md`.

| Item | Value |
|---|---|
| Repository | `sky-born/research-plugins` (GitHub, public) |
| Marketplace name | `research-plugins` |
| Plugins | `plugins` in `.claude-plugin/marketplace.json` is the source of the list |
| Release | `python scripts/release.py` (`check` · `try` · `bump` · `publish`) |
| Install · update | `python bootstrap/bootstrap.py` (`install` · `update` · `status`) |

**Manuscript content never goes into this repository.** Only shared rules and tools that work for any paper belong here.
Facts, paths and numbers of a specific paper go to that project's `CLAUDE.md`.

## One source for both apps

- `plugins/<name>/skills/` is the shared source for Claude Code and Codex. Do not make per-app copies of the content.
- Read the current app's `AGENTS.md`/`CLAUDE.md` and the procedure files they name.
  Do not assume a document meant for the other app was loaded automatically.
- Name, version and description come from `.claude-plugin/plugin.json`.
  `python scripts/sync_codex_manifests.py` generates `.codex-plugin/plugin.json` and
  `.agents/plugins/marketplace.json`. Generated files are not edited by hand.
- Both apps install and update with `python bootstrap/bootstrap.py install` / `update`.
  Use `--app codex --local` only to try a working clone in Codex before a release. Never edit the installed cache.
- User approval, write scope and source protection are never relaxed through per-app registration data.
  Check the actual file access and which runners and tools exist, and pick only the way of running that fits that environment.

---

## 0. There are three clones — first check which one you opened

**Only the working clone may be edited** — Claude Code overwrites the marketplace cache and the installed plugins on the next update
("Three clones" in `README.md`). Anything under `.claude\plugins\` is not the working clone.

```bash
git rev-parse --show-toplevel     # if this path is under .claude/plugins/, do not touch it
```

The working clone's location differs per computer — see the environment record outside the repository (§3); to make one, and for why it never
sits in a cloud-sync folder, see "Installing" and "Changing and releasing" in `README.md`.

**The working clone on another computer may hold uncommitted changes.**
When you start, look at `git status` and `git log --oneline -1`, and settle any difference from the remote first.

---

## 1. A change is finished only when it is released

**Editing files alone reaches no computer**, because automatic updates do not run (§4). Edit, raise the version, `try`, `publish`,
then update each computer — the version rule and the steps are in "Changing and releasing" in `README.md`.

**Commit and push only when the user says so.** Stop after editing and report.

**Write commit messages as one subject line where possible.** Add one short sentence only when the subject does not show the purpose (why). Keep the subject within 72 characters, like `<plugin> v<version>: one-line summary`.
Record what changed in a plugin at the top of that plugin's section in `CHANGELOG.md` as `### <version> — <date>`, and only what someone who uses or updates the plugin needs to know.
`CHANGELOG.md` has one `##` section per plugin in `marketplace.json` and nothing else — changes outside the plugins are described by their commit subject alone.
Do not add `…-by:` trailers such as `Co-Authored-By` — the README states that AI tools are used.
`check` stops when a raised version has no entry or when `CHANGELOG.md` has a section that is not a plugin. `publish` stops on a trailer or a body of two or more paragraphs, and warns about a long subject or body.
**The repository holds no work records.** Documents describe the current state, and `CHANGELOG.md` describes changes, not how they came about; dates appear only in version headings.
The why of a change goes in the commit's one sentence, and work history stays outside the repository.

**Every `README.md` is in English, and a `README.ko.md` beside it is its Korean edition** (the repository root and each plugin). When you change one, change the other too.
`check` compares each pair's heading structure · code blocks (except comments and `<placeholders>`) · link targets.
**Everything else in this repository is written in English, so a reader who knows no Korean can follow all of it.** Korean appears only as data — inside code spans, or in strings the tools match in or write into project files. `check` stops on Korean in Markdown prose, Python comments, names or docstrings outside a code span, and on a Korean string in plugin or script code unless it sits in a module-level `LEGACY*` table (older spellings the tools still read, each entry glossed in English) or is a `가-힣` character range.

**Keep a script's help (`--help`) to the minimum it needs.**

**Pre-release checks** — what `python scripts/release.py check` covers is listed under "Steps" in `README.md`. What it does not cover is `try` and
**`python -X utf8 scripts/preview_projects.py <sibling project> …`**
(runs the new tools on a **copy** of a real project's tracker files to see whether the differences match what was announced — it never writes to the original. If you changed `grammar_baseline.py`, `--grammar`
also runs the grammar_baseline scenario on a copy of the manuscript — for a project with no `grammar` key in its settings, add `--set grammar=<JSON>`). If you edit managed files
(the list in `new-manuscript/managed_files.json`) again after `bump`, rebuild the hash list with `python -X utf8 scripts/tool_hashes.py` and
commit it with them — `check` verifies it is current. Copies in existing projects are brought up to date with `new-manuscript/update_tools.py` after the release.

To add or remove a plugin, follow "Adding a plugin" in `README.md` —
the `plugins` array and the `renames` table in `marketplace.json`. The install script reads that list, so nothing else needs to match.

---

## 2. Writing documents — no environment facts in the text

**Documents in this repository are read and edited on several computers.** A path or a measured value from the computer you sit at,
written into the text, becomes false on another computer, and fixing it there makes it false in the other direction.

**The rule itself is in `research-writing`'s `references/environment.md`, on keeping environment facts apart from invariant facts.**
Only how it applies to this repository is written here.

- **Invariant facts** (command names, procedures and their order, the version rule, concepts) go in the text as they are.
- **Environment facts** (paths, drive letters, the value of `$HOME`, runner names, whether credentials exist, injected environment variables)
  never go in the text as values. **Replace them with a command that finds them, or failing that, put one line in the environment record outside the repository (§3).**
- **Never delete existing lines of an environment record.** They are for other computers; that a line does not hold on this computer
  does not mean it is wrong.
- **Give each measured value the place and the date it was measured.** Leave computers you have not measured as **unchecked**.
  Do not fill cells with guesses.

---

## 3. Environment facts live outside the repository

**This repository records no per-computer values (user folder, working-clone location, runner paths and versions, how credentials are stored).**
Each owner keeps them in an environment record outside the repository and adds lines there for a new computer.
The owner's workspace rules say where the owner's record is.
A session that cannot see that record does not guess values; it checks them as below.

| To find out | How |
|---|---|
| Whether the open folder is the working clone | `git rev-parse --show-toplevel` — not if it is under `.claude/plugins/` (§0) |
| The `claude` executable and its version, registered marketplaces, installed versions | `python bootstrap/bootstrap.py status` |
| Whether the repository is reachable without a login prompt | `GIT_TERMINAL_PROMPT=0 git ls-remote <repository URL> HEAD` |
| Installed plugin folders (Git Bash) | `ls -d "$USERPROFILE/.claude/plugins/cache/<marketplace name>/"*/*/` |
| The personal deny list of the public scan | `git config research-plugins.denylist` — without it, `check` runs only the generic patterns and warns |

On every computer:

- **Do not use `~` in Git Bash.** On some computers `$HOME` is not the user profile, so `~/.claude/...` resolves to a path that does not exist.
  On computers where `$HOME` matches the profile it happens to work, so checking on one computer alone does not reveal the problem.
  The form that works everywhere is `$USERPROFILE` (`$env:USERPROFILE` in PowerShell).
- **The release and install scripts are Python, so the commands are the same on all three operating systems.** The scripts use the Python that ran them,
  the `claude` found in the order `--claude` → `CLAUDE_CODE_EXECPATH` → PATH → the executable inside the desktop app, and `codex`
  found in the order `--codex` → PATH → the executable inside the Codex app.
- **On macOS, call them with `python3`.** On computers where `python` is a shell alias, it does not resolve inside scripts.

---

## 4. Updates are manual — they do not arrive on their own

**It is not true that a new version arrives by itself once registered and installed.** The reason and the commands are in one place, "Updating" in `README.md`.
Only what to follow when editing this repository is written here.

- **After a release, update each computer that needs the change and reopen the session** ("Updating" in `README.md`).
- **Do not try automation again** (the owner's decision; why is under "Updating" in `README.md`).

**A leftover upload (`My Uploads`) hides the CLI install of the same name** — while the upload is in `rpm`, the skill list
stays on the old version, and once the upload folder is gone it switches to the CLI install. Delete the upload.
Which session has what attached is answered by `cat "$APPDATA/Claude/local-agent-mode-sessions"/*/*/rpm/manifest.json`.

---

## 5. Text at the boundary

**File and folder names are compared, stored and used as keys in NFC; a file found on disk is opened by the name the listing returned; a name a tool creates is written in NFC.**
macOS and Drive mirrors on it return Korean names in NFD and open either spelling; Linux and NTFS keep the code points as given, so an NFD file does not open by its NFC name there.
ASCII data looks the same in every form, so a test without Korean names cannot catch a slip.

- **One definition** — `shared/textio.py` (NFC keys, listings with the name on disk, lookup by key, the Hangul class). Install units cannot import from one another,
  so `python scripts/sync_shared.py` copies it byte for byte into each that needs it (paper-index `lib/textio.py`, research-writing `tools/_textio.py`).
  Edit the canonical file and run the script — never edit a copy. `check` stops when a copy differs.
- **`check` also stops** (`boundary_problems` in `scripts/release.py`) on a text-mode `open` · `read_text` · `write_text` in plugin code without an explicit encoding,
  on a `가-힣` range in a unit that has a text module (use its `HANGUL`), and on a folder listing in paper-index outside its text module.
- **Tests that need Korean or NFD names create them at run time** — file names in the repository stay ASCII.
