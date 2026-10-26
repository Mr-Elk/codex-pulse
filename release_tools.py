"""Local deterministic packages, verified upgrades and recoverable file rollback."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import time
import uuid
import zipfile

EXTRA_FILES = {"UI_RULES.html", "MACOS.md", "QUOTA_VALIDATION.md", "README.en.md", "LICENSE", "CONTRIBUTING.md", "VALIDATION.md", "README.md", "CHANGELOG.md", "BETA_GUIDE.md", "RELEASE_NOTES.md", "plugin.json", "index.html", "launch.cmd", "回退上一版本.cmd"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def package_files(root):
    files = []
    for file in root.rglob("*"):
        relative = file.relative_to(root)
        if file.is_symlink():
            raise ValueError(f"Symlink cannot be packaged: {relative}")
        if not file.is_file() or "__pycache__" in relative.parts:
            continue
        if (len(relative.parts) == 1 and (file.suffix in (".py", ".ps1", ".cpp") or file.name in EXTRA_FILES)) or relative.parts[0] in ("assets", "skills"):
            files.append((relative.as_posix(), file.read_bytes()))
    return sorted(files)


def build_archive(root, output, include_tests=True):
    root, output = Path(root), Path(output)
    plugin = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "codex-pulse"
    developer_files={"build_native.ps1","native_backdrop.cpp","rollback.ps1","回退上一版本.cmd"}
    files = {name: data for name, data in package_files(root)
             if include_tests or (not name.startswith("test_") and name not in developer_files)}
    manifest = {"name": plugin["name"], "version": plugin["version"],
                "files": {name: digest(data) for name, data in files.items()}}
    files["release-manifest.json"] = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    verify_archive(output)
    return manifest


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate package entries")
        canonical = set()
        for name in names:
            relative = PurePosixPath(name)
            if (not relative.parts or relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name
                    or any(part.rstrip(" .") != part or re.search(r'[<>:"\\|?*\x00-\x1f]',part)
                           or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',part)
                           for part in relative.parts)):
                raise ValueError("Invalid package path")
            key = name.casefold()
            if key in canonical:
                raise ValueError("Ambiguous Windows package paths")
            canonical.add(key)
        if any(parent.as_posix().casefold() in canonical for name in names
               for parent in PurePosixPath(name).parents if parent != PurePosixPath('.')):
            raise ValueError("A package file is also used as a directory")
        if not {"release-manifest.json","plugin.json"} <= set(names):
            raise ValueError("Package metadata is missing")
        manifest = json.loads(archive.read("release-manifest.json"))
        if (not isinstance(manifest,dict) or manifest.get("name") != "codex-pulse"
                or not isinstance(manifest.get("files"),dict)
                or set(names) != set(manifest["files"]) | {"release-manifest.json"}):
            raise ValueError("Package manifest differs from files")
        for name, expected in manifest["files"].items():
            if digest(archive.read(name)) != expected:
                raise ValueError(f"Package checksum mismatch: {name}")
        plugin = json.loads(archive.read("plugin.json"))
        if (not isinstance(plugin,dict) or
                (plugin.get("name"), plugin.get("version")) != (manifest["name"], manifest.get("version"))):
            raise ValueError("Package version mismatch")
        return manifest


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("File escaped the selected plugin directory")
    return path


def install_archive(archive_path, target, backup_root):
    manifest = verify_archive(archive_path)
    target = Path(target).resolve()
    existing = target / "plugin.json"
    if existing.exists() and json.loads(existing.read_text(encoding="utf-8")).get("name") != "codex-pulse":
        raise ValueError("Destination belongs to another plugin")
    backup = Path(backup_root).resolve() / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    records = []
    for name, new_hash in manifest["files"].items():
        file = inside(target, name)
        old_hash = None
        if file.exists():
            data = file.read_bytes()
            old_hash = digest(data)
            saved = inside(backup / "files", name)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(data)
        records.append({"name": name, "old_sha256": old_hash, "new_sha256": new_hash})
    record = {"target": str(target), "version": manifest["version"], "files": records}
    record_file = backup / "rollback.json"
    record_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    written = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for item in records:
                file = inside(target, item["name"])
                file.parent.mkdir(parents=True, exist_ok=True)
                written.append(item)
                file.write_bytes(archive.read(item["name"]))
                if digest(file.read_bytes()) != item["new_sha256"]:
                    raise OSError(f"Write verification failed: {item['name']}")
    except Exception:
        for item in reversed(written):
            file = inside(target, item["name"])
            if item["old_sha256"] is None:
                file.unlink(missing_ok=True)
            else:
                file.write_bytes(inside(backup / "files", item["name"]).read_bytes())
        raise
    return record_file


def rollback(record_file, dry_run=False):
    record_file = Path(record_file).resolve()
    record = json.loads(record_file.read_text(encoding="utf-8"))
    target, backup = Path(record["target"]).resolve(), record_file.parent
    paths = []
    for item in record["files"]:
        file = inside(target, item["name"])
        if not file.exists() or digest(file.read_bytes()) != item["new_sha256"]:
            raise ValueError(f"File changed after upgrade; preserving it: {item['name']}")
        saved = inside(backup / "files", item["name"])
        if item["old_sha256"] is not None and (not saved.exists() or digest(saved.read_bytes()) != item["old_sha256"]):
            raise ValueError(f"Original backup differs: {item['name']}")
        paths.append((item, file, saved))
    if not dry_run:
        for item, file, saved in reversed(paths):
            if item["old_sha256"] is None:
                file.unlink()
            else:
                file.write_bytes(saved.read_bytes())
    return {"target": str(target), "files": len(paths), "dry_run": dry_run}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build")
    build.add_argument("source", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--runtime-only", action="store_true")
    verify = actions.add_parser("verify")
    verify.add_argument("archive", type=Path)
    install = actions.add_parser("install")
    install.add_argument("archive", type=Path)
    install.add_argument("--target", type=Path, required=True)
    install.add_argument("--backup-root", type=Path, required=True)
    restore = actions.add_parser("rollback")
    restore.add_argument("record", type=Path)
    restore.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        result = build_archive(args.source, args.output, include_tests=not args.runtime_only)
    elif args.action == "verify":
        result = verify_archive(args.archive)
    elif args.action == "install":
        result = {"rollback_record": str(install_archive(args.archive, args.target, args.backup_root))}
    else:
        result = rollback(args.record, args.dry_run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
