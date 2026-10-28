"""Read-only Windows release consistency checks; never build or publish a package."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path, PurePosixPath
import posixpath
import re
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.check_doc_links import anchors, links
from product_version import windows_version
from release_policy import clean_revision, selected_files
from release_tools import digest, verify_archive


def check_payload_links(files):
    """Resolve against the selected payload, not files present in a checkout."""
    directories = {str(parent) for name in files for parent in PurePosixPath(name).parents}
    for source, data in files.items():
        if PurePosixPath(source).suffix.lower() not in {".md", ".markdown"}:
            continue
        for target, line in links(data.decode("utf-8-sig")):
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue
            decoded = unquote(parts.path, errors="strict")
            name = (posixpath.normpath(decoded.lstrip("/")) if decoded.startswith("/")
                    else posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
                    if decoded else source)
            if name not in files and name not in directories:
                raise ValueError(f"{source}:{line}: package link target is absent: {target}")
            if parts.fragment and PurePosixPath(name).suffix.lower() in {".md", ".markdown"}:
                fragment = unquote(parts.fragment, errors="strict")
                if fragment not in anchors(files[name].decode("utf-8-sig")):
                    raise ValueError(f"{source}:{line}: package Markdown anchor is absent: {target}")


def assignment(path, name):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    values = [ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise ValueError(f"Expected one {name} declaration in {path.name}")
    return values[0]


def check_installer(root, version):
    script = (root / "distribution/install.ps1").read_text(encoding="utf-8-sig")
    for variable, expected in (("pulsePayload", version),
                               ("pulseRecovery", assignment(root / "manage.py", "RECOVERY_VERSION"))):
        matches = re.findall(r"^\$" + variable + r"\s*=.*codex-pulse-([^'\s\\/]+)-payload\.zip'", script, re.MULTILINE)
        if matches != [expected]:
            raise ValueError(f"Installer {variable} does not match its authoritative version")


def check_public_guides(root):
    versions = []
    prefix = "https://github.com/Mr-Elk/codex-pulse/"
    for name in ("README.md", "README.en.md"):
        targets = [target for target, _ in links((root / name).read_text(encoding="utf-8"))]
        published = [target.removeprefix(prefix + "releases/tag/v") for target in targets
                     if target.startswith(prefix + "releases/tag/v")]
        if not published:
            raise ValueError(f"{name} needs a versioned public download link")
        expected = prefix + f"blob/v{published[0]}/BETA_GUIDE.md"
        guides = [target for target in targets if target.endswith("BETA_GUIDE.md")]
        if not guides or any(target != expected for target in guides):
            raise ValueError(f"{name} must pin its public guide to the public download version")
        versions.append(published[0])
    if versions[0] != versions[1]:
        raise ValueError("Chinese and English README public download versions differ")


def check_source(root, *, require_clean=False):
    root = Path(root).resolve()
    version = windows_version(root)
    counts = {}
    for profile in ("runtime", "development"):
        files = selected_files(root, include_tests=profile == "development")
        check_payload_links(files)
        counts[profile] = len(files)
    check_installer(root, version)
    check_public_guides(root)
    revision = clean_revision(root)
    if require_clean and revision is None:
        raise ValueError("Release preflight requires a clean Git checkout at its own root")
    return {"platform": "windows", "version": version, "files": counts, "source_revision": revision}


def check_archive(root, archive, *, profile="runtime"):
    if profile not in {"runtime", "development"}:
        raise ValueError("Unknown Windows payload profile")
    root = Path(root).resolve()
    revision = clean_revision(root)
    if revision is None:
        raise ValueError("Archive comparison requires a clean source checkout")
    manifest = verify_archive(archive)
    if (manifest.get("format") != 2 or manifest.get("platform") != "windows"
            or manifest.get("profile") != profile or manifest.get("source_revision") != revision):
        raise ValueError("Archive profile/platform/source revision differs from the checked source")
    if manifest["version"] != windows_version(root):
        raise ValueError("Archive version differs from plugin.json")
    expected = selected_files(root, include_tests=profile == "development")
    hashes = {name: digest(data) for name, data in expected.items()}
    if manifest["files"] != hashes:
        raise ValueError("Archive files or bytes differ from the explicit source package plan")
    with zipfile.ZipFile(archive) as package:
        check_payload_links({name: package.read(name) for name in manifest["files"]})
    return {"platform": "windows", "profile": profile, "version": manifest["version"],
            "source_revision": revision, "archive_sha256": digest(Path(archive).read_bytes()),
            "file_count": len(hashes)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--profile", choices=("runtime", "development"), default="runtime")
    args = parser.parse_args(argv)
    try:
        result = check_source(args.root, require_clean=args.require_clean or args.archive is not None)
        if args.archive is not None:
            result = check_archive(args.root, args.archive, profile=args.profile)
    except (OSError, ValueError, SyntaxError, zipfile.BadZipFile) as error:
        print(f"Release consistency failed: {error}", file=sys.stderr)
        return 1
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Consistency checks passed. This does not establish release or manual acceptance readiness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
