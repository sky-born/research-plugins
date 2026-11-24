# research-writing

English | [Korean](README.ko.md)

Shared working rules for writing academic papers and dissertations, plus tools that create and maintain manuscript projects.
It holds only rules that apply to any paper. The facts, paths and figures of a specific paper belong in that project's documents.

## Installation

With Claude Code 2.1.275 or later, this one line registers the marketplace and installs the plugin.

```
/plugin install research-writing --marketplace sky-born/research-plugins
```

For older versions, Codex, and updates on several computers, follow the [README](../../README.md) at the repository root.
Claude Code and Codex use the same `skills/` source.

## Requirements

- Python 3 (only the standard library is used). Call it `python` on Windows and `python3` on macOS and Linux.
- **On Windows, Git for Windows (Git Bash).** The hook commands use bash syntax, so the hooks do not run without Git Bash.

## Skills

| Skill | What it does |
|---|---|
| `manuscript` | Entry point of a manuscript session. It decides which kind of manuscript project the open folder is and passes control to that project's procedure |
| `manuscript-workflow` | Shared writing rules — style and expressions to avoid, hedging by evidence grade, confirming a citation, presenting a proposed revision and the user's confirmation, tracking open items, figure technique |
| `new-manuscript` | Creates a new manuscript project in one step, including tools, settings (`.manuscript/project.json`) and tracker file skeletons, and brings an existing project's tool copies up to date with the canonical copy |

Detailed rules are in `skills/manuscript-workflow/references/`, one file per topic
(`style-guide` · `evidence-hedging` · `citation-rules` · `revision-protocol` · `tracker-workflow` · `figure-technical` · `build-technical` · `project-config` · `environment`).

## Hooks

`hooks/hooks.json` calls `skills/new-manuscript/hooks/guard_write.py` before and after Edit, Write, Bash and PowerShell.
It works only inside a manuscript project (a folder that has `.manuscript/project.json`) and ends immediately in any other folder.

- It refuses writes that overwrite an existing completion record or a generated index.
- It refuses registering a new open-item ID without the numbering tool.
- It checks the sync state before writing shared files and leaves a snapshot after writing.
- If a broken row remains in a tracker table, it reports it in that turn (it does not block).

The rules are in `skills/manuscript-workflow/references/tracker-workflow.md`, "Sync — several computers write the shared files".

## Tools that go into a project

`new-manuscript` puts copies into the project's `tools/` folder. The source of the list is `skills/new-manuscript/managed_files.json`,
and `update_tools.py` decides with `tool_hashes.json` whether a copy is the same version as the canonical copy.
The tool list and what each tool does are in `skills/manuscript-workflow/references/project-config.md`, "New projects are made by the `new-manuscript` skill".
