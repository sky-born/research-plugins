# -*- coding: utf-8 -*-
r"""guard_write.py — Claude Code hook (PreToolUse · PostToolUse). Protects the shared files of a manuscript project.

    guard_write.py pre     right before Edit · Write · Bash · PowerShell — ① refuses a Write that overwrites an existing completion record `E*.md` or the generated index
                                                    ② refuses writes to shared files while the sync check (_sync.py) has unconfirmed ERRORs
                                                    ③ keeps the version before an Edit · Write as a local snapshot (for the later difference)
                                                    ⑤ refuses an Edit · Write that adds a new open-item ID row by hand — `new_pending.py` in the tools folder assigns numbers
                                                       (only when that tool is in the project · scope `_config.allocation_scope`)
                                                    ⑥ right before an Edit · Write of a shared file, waits briefly while a tool holds the write lock
                                                       (does not block — the hook finishes before the Edit, so it cannot hold the lock itself)
    guard_write.py post    right after the same tools — for a shared file: snapshot · fingerprint · record of "lines this computer wrote" (shell tools: only files whose fingerprint changed)
                                        ④ if table rows of a tracker file are broken (split rows etc.), tells the model and the user in that turn (does not block)
    (without an argument: pre — compatible with old registrations)

Where it runs — both are the same file.
  · the plugin's installed `hooks/hooks.json` registers `${CLAUDE_PLUGIN_ROOT}/skills/new-manuscript/hooks/guard_write.py` (primary) —
    the installed copy's latest code runs whatever state the project copy on a stale mirror is in.
  · the project's `.claude/settings.json` registers `.claude/hooks/guard_write.py` (managed copy) (secondary) — for environments without the plugin hook.
  With both present, a tool call is handled once (marker `hook_seen/<tool_use_id>` in the state folder).
Project detection — for Edit · Write it walks up **from the target file's path**, for Bash · PowerShell from cwd, looking for `.manuscript/project.json` (or `.writing/`).
Without one it exits 0 at once and has no effect on other projects. The check module is looked up in `../tools/_sync.py` next to this file (plugin layout) →
`_sync.py` in the project's tools folder (`tools_dir` in the settings).
In a project that uses the old default (Korean) names without settings, it blocks every Edit · Write except to the settings file and gives the values to add to the settings as the reason.

I/O — reads JSON from standard input (tool_name, tool_input, cwd, tool_use_id) and writes to standard output only when it blocks:
  {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}
or, when it reports table defects after a write, {"systemMessage": …, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": …}}.
The exit code is always 0; an error in the script itself goes to stderr and exits 1 (non-blocking — fail-open).
**It never exits 2** — in the hook protocol 2 means block, so a defect in the script must not block every write.
Standard input is read as bytes and decoded as UTF-8 — when Python on Windows reads it as cp949, Korean paths are garbled and the checks miss.
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_RELS = (os.path.join('.manuscript', 'project.json'), os.path.join('.writing', 'project.json'))


def find_root(start):
    if not start:
        return None
    p = os.path.abspath(start)
    if os.path.isfile(p):
        p = os.path.dirname(p)
    while True:
        for rel in CONFIG_RELS:
            if os.path.isfile(os.path.join(p, rel)):
                return p
        up = os.path.dirname(p)
        if up == p:
            return None
        p = up


def _raw_config(root):
    for rel in CONFIG_RELS:
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            try:
                return json.load(io.open(p, encoding='utf-8'))
            except (OSError, ValueError) as e:
                sys.stderr.write('guard_write: could not read %s: %s\n' % (rel, e))
            break
    return {}


def decide_overwrite(cfg, root, data):
    """A Write that overwrites a completion record or the generated index — the reason if it must be blocked, otherwise None."""
    if data.get('tool_name') != 'Write':
        return None
    fp = (data.get('tool_input') or {}).get('file_path') or ''
    if not fp:
        return None
    rec_dir, prefix, index = cfg.records_dir, cfg.raw['tracker'].get('record_prefix', 'E'), cfg.record_index_file
    target = os.path.abspath(fp if os.path.isabs(fp) else os.path.join(root, fp))
    try:
        rel = os.path.relpath(target, root)
    except ValueError:
        return None
    if rel.startswith('..'):
        return None
    rel = rel.replace(os.sep, '/')
    rec_pat = re.escape(rec_dir.replace(os.sep, '/').strip('/')) + '/' + re.escape(prefix) + r'\d+\.md'
    if re.fullmatch(rec_pat, rel) and os.path.exists(target):
        return ('Completion record %s already exists. Records are never overwritten — change only what needs fixing with Edit, '
                'and create new items under the next number with %s (`tracker-workflow.md` "Concurrent editing — the user may be editing the same file in another window").' % (rel, cfg.tool('new_record.py')))
    if rel == index.replace(os.sep, '/') and os.path.exists(target):
        return ('%s is generated by a tool. Do not write it by hand; regenerate it with %s.' % (rel, cfg.tool('index_records.py')))
    return None


def decide_legacy(root, data, message):
    """A project that uses the old default names without settings — the reason to block an Edit · Write that is not to the settings file, otherwise None."""
    if data.get('tool_name') not in ('Edit', 'Write', 'MultiEdit'):
        return None
    fp = (data.get('tool_input') or {}).get('file_path') or ''
    target = os.path.abspath(fp if os.path.isabs(fp) else os.path.join(root, fp))
    if any(os.path.normcase(target) == os.path.normcase(os.path.join(root, rel)) for rel in CONFIG_RELS):
        return None
    return message


def decide_new_ids(cfg, root, sync, tool, ti, rel):
    """An Edit · Write that adds a new open-item ID by hand — the reason if it must be blocked, otherwise None. A tool assigns numbers inside the lock (so that two
    sessions do not pick the same number). The decision is `Sync.hand_added_ids` (the scope and the definition of a new ID live there only). A project that does not
    have the numbering tool yet (its copies were not updated) is not blocked — otherwise there would be no way to add items. An old `_sync.py` also passes."""
    find = getattr(sync, 'hand_added_ids', None)
    if find is None or not os.path.isfile(os.path.join(root, cfg.tools_dir, 'new_pending.py')):
        return None
    if tool == 'Write':
        text = ti.get('content') or ''
    elif tool == 'MultiEdit':
        text = '\n'.join((e or {}).get('new_string') or '' for e in (ti.get('edits') or []))
    else:
        text = ti.get('new_string') or ''
    new = find(rel, text)
    if not new:
        return None
    letter = re.match(r'[A-Z]+', new[0]).group(0)
    return ('Tried to add the new open item %s by hand. A tool assigns the numbers, so that two sessions do not pick the same number. '
            'Write the row to a one-line file with `%s?` as its ID, run `<py> -X utf8 %s <that file>`, then use the number it prints '
            '(`tracker-workflow.md` "Concurrent editing — the user may be editing the same file in another window").' % (' · '.join(new), letter, cfg.tool('new_pending.py')))


def _load_sync(root):
    """(_config, _sync) modules — the plugin layout (`../tools`) first, otherwise the project copy (`tools_dir` in the settings, else `tools`,
    else any folder directly under the root that holds both modules — so an old project's tools folder is found without naming it)."""
    dirs = [os.path.join(os.path.dirname(HERE), 'tools')]
    dirs += [os.path.join(root, d) for d in (_raw_config(root).get('tools_dir'), 'tools') if d]
    try:
        dirs += sorted(os.path.join(root, d) for d in os.listdir(root) if not d.startswith('.'))
    except OSError:
        pass
    for tools in dirs:
        if os.path.isfile(os.path.join(tools, '_sync.py')) and os.path.isfile(os.path.join(tools, '_config.py')):
            if tools not in sys.path:
                sys.path.insert(0, tools)
            mods = []
            for name in ('_config', '_sync'):
                spec = importlib.util.spec_from_file_location(name, os.path.join(tools, name + '.py'))
                m = importlib.util.module_from_spec(spec)
                sys.modules[name] = m
                spec.loader.exec_module(m)
                mods.append(m)
            return mods[0], mods[1]
    return None, None


def deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                         "permissionDecision": "deny",
                                                         "permissionDecisionReason": reason}}, ensure_ascii=True))


def notice_tables(sync, rels):
    """After a write — if table defects (split rows etc.) remain in a tracker file, reports them in that turn (does not block). additionalContext for the model,
    systemMessage for the user. An old `_sync.py` (no table_report) or a fault in the check is skipped silently — fail-open."""
    try:
        probs = sync.table_report(rels)
    except Exception as e:
        sys.stderr.write('guard_write: error in the table check, skipped: %r\n' % (e,))
        return
    if not probs:
        return
    msg = ('Table rows in a tracker file are broken — one item per line, and | inside a cell is \\| (`tracker-workflow.md` "Table row format — one item per line"). '
           'If this write caused it, fix it now: ' + ' / '.join('%s %s' % (r, d) for r, d in probs[:6]))
    sys.stdout.write(json.dumps({"systemMessage": msg,
                                 "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                                ensure_ascii=True))


def run(mode, data):
    tool = data.get('tool_name')
    ti = data.get('tool_input') or {}
    if tool in ('Edit', 'Write', 'MultiEdit'):
        fp = ti.get('file_path') or ''
        root = find_root(fp if os.path.isabs(fp) else os.path.join(data.get('cwd') or os.getcwd(), fp)) \
            or find_root(data.get('cwd') or os.getcwd())
    elif tool in ('Bash', 'PowerShell'):
        root = find_root(data.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    else:
        return 0
    if root is None:
        return 0

    cfg_mod, sync_mod = _load_sync(root)
    if sync_mod is None:
        return 0
    legacy = getattr(cfg_mod, 'LegacyNames', None)
    try:
        cfg = cfg_mod.load(root)
    except BaseException as e:                   # LegacyNames is a SystemExit — tools stop on it; the hook uses it as the reason
        if legacy is None or not isinstance(e, legacy):
            raise
        reason = decide_legacy(root, data, str(e)) if mode == 'pre' else None
        if reason:
            deny(reason)
        return 0
    if mode == 'pre':
        reason = decide_overwrite(cfg, root, data)
        if reason:
            deny(reason)
            return 0

    sync = sync_mod.Sync(cfg)
    marker = '%s_%s' % (mode, data.get('tool_use_id') or hashlib.sha1(json.dumps(ti, sort_keys=True).encode('utf-8')).hexdigest()[:16])
    if sync.hook_seen(marker):
        return 0

    if tool in ('Edit', 'Write', 'MultiEdit'):
        fp = ti.get('file_path') or ''
        target = os.path.abspath(fp if os.path.isabs(fp) else os.path.join(root, fp))
        nfc = getattr(cfg_mod, 'nfc', None) or (lambda s: s)     # paths are compared in NFC — the same file even when the input (NFC) and the file system (macOS NFD) differ
        try:
            rel = os.path.relpath(nfc(target), nfc(root)).replace(os.sep, '/')
        except ValueError:
            return 0
        if rel.startswith('..') or not sync.is_shared(rel):
            return 0
        if mode == 'pre':
            reason = sync.guard(tool, rel) or decide_new_ids(cfg, root, sync, tool, ti, rel)
            if reason:
                deny(reason)
                return 0
            wait = getattr(sync, 'wait_write_lock', None)        # missing in an old `_sync.py`
            if wait and not wait():                              # while the tidy tool or similar is writing, wait briefly for the release — never block if it takes too long
                sys.stderr.write('guard_write: the write lock was not released; letting the write through without waiting\n')
            sync.before_write(rel)
        else:
            sync.after_write(rel)
            notice_tables(sync, [rel])
        return 0

    # Bash · PowerShell — the command is not parsed: before, guard only when a shared file name appears in the command; after, only files whose fingerprint changed
    if mode == 'pre':
        open_ = sync.unacked()
        if not open_:
            return 0
        cmd = ti.get('command') or ''
        names = {os.path.basename(r) for r in sync.shared_files()} | {cfg.records_dir}
        if any(n and n in cmd for n in names):
            deny(sync.guard(tool))
        return 0
    notice_tables(sync, sync.after_bash())
    return 0


def main(argv):
    mode = (argv[1] if len(argv) > 1 else 'pre').lower()
    if mode not in ('pre', 'post'):
        sys.stderr.write('guard_write: mode must be pre or post: %r\n' % mode)
        return 1
    try:
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, 'buffer') else sys.stdin.read().encode('utf-8')
        data = json.loads(raw.decode('utf-8-sig')) if raw.strip() else {}
    except (ValueError, UnicodeDecodeError) as e:
        sys.stderr.write('guard_write: could not read the input JSON: %s\n' % e)
        return 1
    try:
        return run(mode, data)
    except Exception as e:  # a defect must not block all writes — non-blocking warning
        sys.stderr.write('guard_write(%s): error during the check, letting it through: %r\n' % (mode, e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
