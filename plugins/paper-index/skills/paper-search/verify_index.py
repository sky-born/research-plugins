#!/usr/bin/env python3
"""Read-only source/index checks; writes only a new, explicitly named JSON report.

This does not rebuild caches or prove that existing text matches a changed PDF.
Use source snapshots taken before and after a build, then a no-change rerun.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

# Keep running this read-only helper from creating files in the installed skill.
sys.dont_write_bytecode = True
from lib import config, extract


def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def digest(path):
    before = path.stat()
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"File changed while being read: {path}")
    return {"size": after.st_size, "mtime_ns": after.st_mtime_ns, "sha256": sha.hexdigest()}


def state(cfg):
    library = Path(cfg["library"]).resolve()
    paths = {key: Path(value).resolve() for key, value in config.paths(cfg).items()}
    if not library.is_dir():
        raise ValueError(f"Source library does not exist: {library}")
    for key in ("index_dir", "oa_staging"):
        if inside(paths[key], library) or inside(library, paths[key]):
            raise ValueError(f"Source and {key} must be separate: {library} / {paths[key]}")
    sources = {}
    for rel in extract.scan(str(library)):
        source = (library / rel).resolve()
        if not inside(source, library):
            raise ValueError(f"Source link escapes the selected library: {rel}")
        sources[rel] = digest(source)
    if set(extract.scan(str(library))) != set(sources):
        raise ValueError("Source listing changed during snapshot; retry after synchronization.")

    issues, exceptions = [], []
    index_state = None
    index_count = 0
    if not paths["json"].is_file():
        issues.append("papers_index.json is missing")
    else:
        rows = json.loads(paths["json"].read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("papers_index.json must contain a list")
        index_count = len(rows)
        relative_paths = [row.get("rel", "") for row in rows]
        for rel, count in Counter(relative_paths).items():
            if count > 1:
                issues.append(f"Duplicate source mapping ({count}): {rel}")
        for rel in sorted(set(sources) - set(relative_paths)):
            issues.append(f"Source missing from index: {rel}")
        for rel in sorted(set(relative_paths) - set(sources)):
            issues.append(f"Indexed source not found: {rel}")
        cache_hashes = {}
        cache_owners = {}
        for row in rows:
            rel, text_name = row.get("rel", ""), row.get("txt", "")
            target = (paths["fulltext"] / text_name).resolve()
            if not text_name or not inside(target, paths["fulltext"]):
                issues.append(f"Invalid cache path: {rel}")
                continue
            if target in cache_owners:
                issues.append(f"Shared cache for different index rows: {cache_owners[target]} / {rel}")
            cache_owners[target] = rel
            if not target.is_file():
                issues.append(f"Missing cache: {rel}")
                continue
            cache_hashes[text_name] = digest(target)["sha256"]
            body = target.read_text(encoding="utf-8", errors="replace")
            if not body.strip():
                issues.append(f"Empty cache: {rel}")
            if len(body) < 500 or row.get("note"):
                exceptions.append({"source": rel, "chars": len(body), "note": row.get("note", "")})
        index_state = {"json_sha256": digest(paths["json"])["sha256"], "cache_sha256": cache_hashes}
    return {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "library": str(library),
        "index_dir": str(paths["index_dir"]),
        "sources": sources,
        "source_count": len(sources),
        "source_bytes": sum(item["size"] for item in sources.values()),
        "index_count": index_count,
        "index_state": index_state,
        "issues": issues,
        "extraction_exceptions": exceptions,
    }


def save_new(data, target, library):
    target = Path(target).resolve()
    if inside(target, Path(library)):
        raise ValueError("Reports must be stored outside the source library")
    if inside(target, Path(__file__).resolve().parent):
        raise ValueError("Reports must be stored outside the installed skill")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Verified paperindex.config.json path")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--out", required=True, help="New source/index snapshot JSON")
    verify = commands.add_parser("verify")
    verify.add_argument("--before", required=True)
    verify.add_argument("--out", required=True, help="New verification report JSON")
    verify.add_argument("--require-index-unchanged", action="store_true")
    args = parser.parse_args()
    current = state(config.load(args.config))
    if args.command == "verify":
        before = json.loads(Path(args.before).read_text(encoding="utf-8"))
        for key in ("library", "index_dir"):
            if before.get(key) != current[key]:
                current["issues"].append(f"Different {key} from baseline")
        previous_sources = before.get("sources")
        if not isinstance(previous_sources, dict):
            raise ValueError("Baseline has no valid source records")
        changes = [rel for rel in sorted(set(previous_sources) | set(current["sources"]))
                   if previous_sources.get(rel) != current["sources"].get(rel)]
        current["source_changes"] = changes
        current["sources_unchanged"] = not changes
        if changes:
            current["issues"].append("Source records changed; review every source_changes entry")
        if args.require_index_unchanged:
            unchanged = bool(before.get("index_state")) and before["index_state"] == current["index_state"]
            current["index_unchanged"] = unchanged
            if not unchanged:
                current["issues"].append("Active index JSON or text cache changed on no-change rerun")
        current["ok"] = not current["issues"]
    save_new(current, args.out, current["library"])
    summary = {key: current[key] for key in (
        "library", "source_count", "source_bytes", "index_count", "issues", "extraction_exceptions")}
    summary["report"] = str(Path(args.out).resolve())
    if "ok" in current:
        summary["ok"] = current["ok"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if args.command == "verify" and not current["ok"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f"Verification stopped: {error}")
