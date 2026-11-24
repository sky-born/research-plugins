# -*- coding: utf-8 -*-
r"""update_tools.py — brings the managed files (tools · location syntax · hook) of an existing manuscript project in line with the canonical copies.

The source is **the plugin copy that contains this file** — before a release run the working clone's, after a release the installed one's.
The managed files are listed in `managed_files.json`, and the hashes of the canonical history are in `tool_hashes.json` (both in this folder).

Usage  (`<py>` is this computer's Python 3 — `python` on Windows, `python3` on macOS)
    <py> -X utf8 update_tools.py <project>                       verdicts only (default, = --check)
    <py> -X utf8 update_tools.py <project> --apply               replaces canonical versions that differ
    <py> -X utf8 update_tools.py <project> --apply --force tools/index_records.py   also replaces a locally edited file (after a backup)
    <py> -X utf8 update_tools.py <project> --apply --add tools/_location.py         adds a missing file
    <py> -X utf8 update_tools.py --scan <folder> [--depth N]        status table of the projects below

Verdicts — one per file. Hashes are taken of the content with line endings normalized to LF (so that line-ending differences on macOS or in sync
copies are not mistaken for local edits).
    same                        same as the canonical copy (if only line endings differ: "same · line endings differ" — --apply aligns it to the canonical bytes)
    older canonical version vX  a version found in the canonical history (--apply replaces it)
    locally modified            not in the canonical history (only with --force <dst>; the original goes to .manuscript/tools_backup/<date>/ first)
    missing                     not in the project (only with --add <dst> — the tool set is not installed into projects that do not use it)
    old name                    present only under its 0.12-or-earlier name (`LEGACY_TOOL_NAMES` in `tools/_config.py`) — a canonical version is moved to the new name by --apply;
                                a locally modified copy only with --force <dst> (after a backup)

`{tools_dir}` in dst is the tools folder in that project's settings. For a project that uses the old default (Korean) names without settings, the tool shows
the values to add to the settings and refuses --apply — this tool never writes the settings file (the session shows the values to the user, then writes them with Edit).
Also reported, without changes — settings keys that rely on defaults · whether the hook registration (.claude/settings.json) matches the example.

Format — a project whose tracker anchors still use the pre-0.14 Korean spellings is migrated in the same run (`migrate_format.py`): the check
mode previews it, and --apply rewrites the anchors once every managed tool copy is current, then rebuilds the generated files with the
project's tools (`index_records.py` · `tidy_tracker.py --apply`). The new tool copies write English only, so tools and format move together.
Exit codes — 0 all same · 1 some files differ, or the format needs migrating (or still does after --apply) · 2 argument or input error ·
old names without settings
"""
import argparse, datetime, hashlib, io, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import _config                                      # noqa: E402  — the loader of this plugin copy
import migrate_format                               # noqa: E402  — the anchor rewrite of this plugin copy


def _utf8_console():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def norm_hash(data):
    """sha256 with line endings normalized to LF — the same definition as tool_hashes.json."""
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def load_manifest():
    m = json.load(io.open(os.path.join(HERE, 'managed_files.json'), encoding='utf-8'))
    p = os.path.join(HERE, 'tool_hashes.json')
    hist = json.load(io.open(p, encoding='utf-8')) if os.path.isfile(p) else {'files': {}}
    return m, hist


def plugin_version():
    p = os.path.join(os.path.dirname(os.path.dirname(HERE)), '.claude-plugin', 'plugin.json')
    try:
        return json.load(io.open(p, encoding='utf-8')).get('version', '?')
    except (OSError, ValueError):
        return '?'


# ---------------------------------------------------------------- verdicts
def project_names(project):
    """(tools folder, old names to add to the settings {…} or {}) — a project that has not written its old names into the settings is judged by its old tools folder."""
    cfg = _config.load(project, strict=False)
    pins = _config.legacy_pins(project, cfg.raw_file)
    return pins.get('tools_dir') or cfg.tools_dir, pins


def _verdict(sb, db, known):
    """(verdict, note) — same · same · line endings differ · older canonical version · locally modified."""
    if norm_hash(sb) == norm_hash(db):
        return ('same' if sb == db else 'same · line endings differ'), ''
    if norm_hash(db) in known:
        return 'older canonical version', 'v' + ' · v'.join(known[norm_hash(db)])
    return 'locally modified', 'content not in the canonical history'


def classify(project, manifest, hist):
    """[(dst, verdict, note, src path, dst path, old-name copy)] — verdict is 'same' 'same · line endings differ' 'older canonical version' 'locally modified' 'missing' 'old name'.
    The old-name copy is None or (path, is locally modified). The note of 'old name' is the verdict of that copy."""
    tools_dir = project_names(project)[0]
    out = []
    for item in manifest['files']:
        rel = item['dst'].replace('{tools_dir}', tools_dir)
        src = os.path.join(HERE, *item['src'].split('/'))
        dst = os.path.join(project, *rel.split('/'))
        old_name = _config.LEGACY_TOOL_NAMES.get(item['src'])      # its 0.12-or-earlier name, if any
        path = os.path.join(os.path.dirname(dst), old_name) if old_name else None
        if not os.path.isfile(src):
            out.append((rel, 'canonical copy missing', item['src'], src, dst, None)); continue
        sb, known = io.open(src, 'rb').read(), hist['files'].get(item['src'], {})
        old_v, old_note = _verdict(sb, io.open(path, 'rb').read(), known) if path and os.path.isfile(path) else (None, '')
        old = (path, old_v == 'locally modified') if old_v else None
        if os.path.isfile(dst):
            v, note = _verdict(sb, io.open(dst, 'rb').read(), known)
            out.append((rel, v, note, src, dst, old))
        elif old:
            out.append((rel, 'old name', '%s — %s%s' % (old_name, old_v, (' ' + old_note) if old_v == 'older canonical version' else ''),
                        src, dst, old))
        else:
            out.append((rel, 'missing', '', src, dst, None))
    return out


def config_report(project):
    """Settings keys that rely on defaults — keys missing from the settings file, for which the tools use `_config.DEFAULTS`."""
    raw, path = {}, None
    for rel in (_config.CONFIG_REL, _config.CONFIG_REL_OLD):
        p = os.path.join(project, rel)
        if os.path.isfile(p):
            path = p
            try:
                raw = json.load(io.open(p, encoding='utf-8'))
            except ValueError as e:
                return None, ['Could not read the settings file: %s' % e]
            break
    if path is None:
        return None, ['No settings file — every value is a default']
    missing = []
    if 'kind' not in raw:
        missing.append('kind')
    for sec, keys in _config.DEFAULTS.items():
        if not isinstance(keys, dict):
            if sec not in raw:
                missing.append(sec)
            continue
        if sec == 'sync':
            # sync settings normally run on defaults — one line instead of listing every key
            n = sum(1 for k in keys if k not in (raw.get(sec) or {}))
            if n:
                missing.append('sync (keys on defaults: %d%s)' % (n, '' if 'sync' in raw else ' — no section'))
            continue
        for k in keys:
            if k not in (raw.get(sec) or {}):
                missing.append('%s.%s' % (sec, k))
    return os.path.relpath(path, project), missing


def sync_gate(project, apply_, override):
    """S10 — sync check right before applying (S1 freshness · S2 record continuity · S5 conflict copies). Writing canonical copies onto a stale mirror can be the
    first write of an overwrite. With an ERROR (S2) applying is refused (passes only with --sync-override). WARNs (S1 · S5) are shown and it proceeds — the drive
    snapshots before and after the update and the hash comparison (only older canonical versions are replaced) are the safety net. For verdicts only, it just shows them."""
    try:
        import _sync                              # the check of this plugin copy (the installed one) — current code even when the project copy is old
    except ImportError as e:
        print('  sync      could not load the check module (%s) — skipped' % e)
        return True
    try:
        findings = _sync.Sync(_config.load(project)).check('tools')
    except Exception as e:                            # a fault in the check must not block the update — report it and pass
        print('  sync      error during the check (%r) — skipped' % (e,))
        return True
    bad = [f for f in findings if f.level in ('ERROR', 'WARN')]
    if not bad:
        print('  sync      no problems (S1 freshness · S2 record continuity · S5 conflict copies)')
        return True
    for f in bad:
        print('  sync      ! ' + f.line())
    if apply_ and not override and any(f.level == 'ERROR' for f in bad):
        print('  → Evidence that the mirror went back to an old version (ERROR), so applying is refused. Check that the drive is up to date and run again, or, '
              'with the user\'s confirmation, add --sync-override.')
        return False
    if apply_ and any(f.level == 'WARN' for f in bad):
        print('  → Only WARNs, so proceeding (snapshots before and after the update and the hash comparison are the safety net).')
    return True


def hook_report(project, manifest):
    ex = os.path.join(HERE, *manifest.get('settings_example', 'hooks/settings.example.json').split('/'))
    tg = os.path.join(project, *manifest.get('settings_target', '.claude/settings.json').split('/'))
    if not os.path.isfile(tg):
        return 'missing'
    try:
        want = json.load(io.open(ex, encoding='utf-8')).get('hooks')
        have = json.load(io.open(tg, encoding='utf-8')).get('hooks')
    except (OSError, ValueError) as e:
        return 'unreadable (%s)' % e
    if have is None:
        return 'not registered — merge in the hooks block of settings.example.json'
    return 'same' if _without_status(have) == _without_status(want) else 'differs — compare with the example and align it by hand'


def _without_status(value):
    """The hooks block without `statusMessage` — it is display text, so a project keeps any wording it has."""
    if isinstance(value, dict):
        return {k: _without_status(v) for k, v in value.items() if k != 'statusMessage'}
    if isinstance(value, list):
        return [_without_status(v) for v in value]
    return value


def print_report(project, rows, cfg, hook):
    print('project   %s' % project)
    print('canonical %s (research-writing %s)' % (HERE, plugin_version()))
    w = max(len(r[0]) for r in rows) if rows else 10
    for dst, verdict, note, _s, _d, old in rows:
        if old and verdict != 'old name':
            note = (note + ' · ' if note else '') + 'old-name copy also present (%s%s)' % (os.path.basename(old[0]), ' · locally modified' if old[1] else '')
        print('  %-*s  %s%s' % (w, dst, verdict, ('  ' + note) if note else ''))
    path, missing = cfg
    if path is None:
        print('  settings  ' + missing[0])
    elif missing:
        print('  settings  %s — keys that rely on defaults (%d): %s' % (path, len(missing), ', '.join(missing)))
        print('            (this tool never writes the settings file. Show the needed values to the user, then write them with Edit)')
    else:
        print('  settings  %s — no keys rely on defaults' % path)
    print('  hooks     ' + hook)


# ---------------------------------------------------------------- applying
def backup(project, rel, path):
    day = datetime.date.today().isoformat()
    folder = os.path.join(project, _config.TOOLS_BACKUP, day)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    base = os.path.basename(rel)
    for i in range(1, 100):
        cand = os.path.join(folder, base if i == 1 else '%s.%d' % (base, i))
        try:
            fd = os.open(cand, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, 'wb') as f:
            f.write(io.open(path, 'rb').read())
        return cand
    raise SystemExit('Could not find a free backup name: %s' % folder)


def apply(project, rows, force, add):
    """An old-name copy is deleted after the canonical copy is written under the new name — an old copy that is not a canonical version (locally modified) only after a backup."""
    changed, left = [], []
    for dst, verdict, note, src, dpath, old in rows:
        old_path, old_local = old if old else (None, False)
        if verdict == 'canonical copy missing':
            continue
        if verdict == 'missing' and dst not in add:
            left.append((dst, verdict, 'added only with --add')); continue
        if (verdict == 'locally modified' or old_local) and dst not in force:
            why = 'the old-name copy is locally modified, so ' if old_local and verdict != 'locally modified' else ''
            left.append((dst, verdict, why + 'replaced only with --force')); continue
        if verdict == 'locally modified':
            print('  backup    %s → %s' % (dst, os.path.relpath(backup(project, dst, dpath), project)))
        if old_local:
            print('  backup    %s → %s' % (os.path.relpath(old_path, project), os.path.relpath(backup(project, old_path, old_path), project)))
        if verdict != 'same':
            d = os.path.dirname(dpath)
            if not os.path.isdir(d):
                os.makedirs(d)
            shutil.copyfile(src, dpath)
            if norm_hash(io.open(dpath, 'rb').read()) != norm_hash(io.open(src, 'rb').read()):
                raise SystemExit('Hash differs after writing: %s' % dst)
            changed.append((dst, verdict))
        if old_path:
            os.remove(old_path)
            changed.append((os.path.relpath(old_path, project).replace(os.sep, '/'), 'old-name copy removed'))
    for dst, verdict in changed:
        print('  replaced  %-30s (%s)' % (dst, verdict if verdict.endswith('removed') else verdict + ' → canonical'))
    for dst, verdict, why in left:
        print('  kept      %-30s %s — %s' % (dst, verdict, why))
    return left


# ---------------------------------------------------------------- scan
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', 'archive', '.manuscript', '.claude',
             _config.LEGACY_DEFAULTS['sync']['snapshot_dir'].split('/')[0]}      # the old archive folder name


def find_projects(folder, depth):
    folder = os.path.abspath(folder)
    out = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        level = 0 if rel == '.' else rel.count(os.sep) + 1
        if os.path.isfile(os.path.join(root, '.manuscript', 'project.json')) \
                or os.path.isfile(os.path.join(root, '.writing', 'project.json')) \
                or os.path.isfile(os.path.join(root, '.claude', 'hooks', 'guard_write.py')):
            out.append(root)
        if level >= depth:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
    return out


def scan(folder, depth, manifest, hist):
    projects = find_projects(folder, depth)
    if not projects:
        print('No projects found: %s (depth %d)' % (folder, depth)); return 1
    rc = 0
    for p in projects:
        rows = classify(p, manifest, hist)
        tools_dir, pins = project_names(p)
        tool_dsts = {item['dst'].replace('{tools_dir}', tools_dir) for item in manifest['files'] if item['src'].startswith('tools/')}
        counts = {}
        for _d, v, *_ in rows:
            counts[v.split(' ')[0]] = counts.get(v.split(' ')[0], 0) + 1
        summary = ' · '.join('%s %d' % (k, v) for k, v in counts.items())
        name = os.path.relpath(p, folder) or '.'
        # "missing" in a project that does not use the tool set (hook only) is not a difference — nothing is installed there.
        if not any(v != 'missing' for d, v, *_ in rows if d in tool_dsts):
            print('%s\n    no tool set — hook only (files %s) | hooks %s' % (name, summary, hook_report(p, manifest)))
            continue
        fmt = format_state(p) if not pins else '?'
        print('%s\n    files %s | hooks %s | format %s%s' % (name, summary, hook_report(p, manifest), fmt,
                                                           ' | old names not in the settings — add them before applying' if pins else ''))
        if pins or fmt in ('ko', 'mixed') or any(v != 'same' for _d, v, *_ in rows):
            rc = 1
    return rc


def format_state(project):
    """'en' · 'ko' · 'mixed' · 'none' — the tracker anchors (_config.project_format)."""
    try:
        return _config.project_format(_config.load(project))[0]
    except (SystemExit, OSError, ValueError):
        return '?'


def migrate_and_rebuild(project, tools_dir):
    """--apply's format step: rewrite the anchors, then rebuild the generated files with the project's own (now current) tools.
    Returns True when the project ends with English anchors."""
    import subprocess
    rc, lines, written = migrate_format.migrate(project, True)      # refuses on an open non-S9 ERROR; drops the S9 record afterwards
    for line in lines:
        print('  ' + line)
    if rc != 0:
        print('  format    not migrated' + (' — confirm the open ERRORs with the user first' if rc == 3 else
                                             ' — run again (the migration is idempotent)'))
        return False
    if written:
        print('  format    rewritten: ' + ', '.join(written))
    ok = True
    for tool, args, fine in (('index_records.py', [], (0,)), ('tidy_tracker.py', ['--apply'], (0, 1))):   # tidy: 1 = warnings only
        path = os.path.join(project, tools_dir, tool)
        r = subprocess.run([sys.executable, '-X', 'utf8', '-B', path] + args, cwd=project,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-3:]
        print('  rebuild   %s%s (rc=%d)%s' % (tool, (' ' + ' '.join(args)) if args else '', r.returncode,
                                            ''.join('\n            ' + l for l in tail)))
        ok = ok and r.returncode in fine
    state = format_state(project)
    print('  format    now %s' % state)
    if not ok:
        print('  rebuild   not finished — fix what the tool reported, then run the tidy tool (or this command) again')
    return ok and state in ('en', 'none')


# ---------------------------------------------------------------- entry
def main(argv=None):
    _utf8_console()
    ap = argparse.ArgumentParser(description='Brings the managed files of an existing project in line with the canonical copies.')
    ap.add_argument('project', nargs='?', help='project root (or use --scan)')
    ap.add_argument('--check', action='store_true', help='verdicts only (default)')
    ap.add_argument('--apply', action='store_true', help='replace canonical versions that differ')
    ap.add_argument('--force', action='append', default=[], metavar='DST', help='also replace a locally edited file (after a backup)')
    ap.add_argument('--add', action='append', default=[], metavar='DST', help='add a missing file')
    ap.add_argument('--scan', metavar='FOLDER', help='status table of the projects below')
    ap.add_argument('--depth', type=int, default=3)
    ap.add_argument('--sync-override', action='store_true', help='apply even with an ERROR in the sync check (S10) — only after the user confirms')
    a = ap.parse_args(argv)
    manifest, hist = load_manifest()
    if a.scan:
        return scan(a.scan, a.depth, manifest, hist)
    if not a.project:
        ap.print_usage(); return 2
    project = os.path.abspath(a.project)
    if not os.path.isdir(project):
        print('Project folder missing: %s' % project); return 2
    rows = classify(project, manifest, hist)
    force = [x.replace('\\', '/') for x in a.force]
    add = [x.replace('\\', '/') for x in a.add]
    print_report(project, rows, config_report(project), hook_report(project, manifest))
    pins = project_names(project)[1]
    if pins:
        print('  old names ' + _config.legacy_message(pins).replace('\n', '\n            '))
        if a.apply:
            print('Not applied — add the values above to the settings and run again.')
        return 2
    ok = sync_gate(project, a.apply, a.sync_override)
    plans = migrate_format.plan(_config.load(project))
    needs_format = any(p[4] for p in plans)
    for line in migrate_format.report(plans):
        print('  ' + line)
    if not a.apply:
        same = all(v == 'same' and not old for _d, v, _n, _s, _p, old in rows)
        return 0 if same and not needs_format else 1
    if not ok:
        return 1
    print('Applying')
    apply(project, rows, force, add)
    rows2 = classify(project, manifest, hist)
    bad = [(d, v) for d, v, _n, _s, _p, old in rows2 if v != 'same' or old]
    print('after     ' + ('all same' if not bad else 'differences left — ' + ', '.join('%s(%s)' % x for x in bad)))
    if needs_format:
        tools_dir = project_names(project)[0]
        # an existing copy that is not current blocks (it would write Korean over English anchors); a tool the project never installed does not
        tool_bad = [d for d, v in bad if d.startswith(tools_dir + '/') and v != 'missing']
        if tool_bad:
            # old tool copies would rewrite the generated files in Korean over English anchors — tools and format move together
            print('  format    not migrated — these tool copies are not current: %s (replace them first, e.g. --force after checking)'
                  % ', '.join(tool_bad))
            return 1
        if not migrate_and_rebuild(project, tools_dir):
            return 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
