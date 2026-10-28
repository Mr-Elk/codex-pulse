"""Assemble or verify a local Windows candidate. No upload, install or publication."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.check_release import assignment, check_archive, check_payload_links, check_source
from release_policy import check_dependencies, read_input
from release_tools import build_archive, digest, verify_archive

DLL = "assets/native/pulse_backdrop_x64.dll"
NATIVE_SOURCES = ("native_backdrop.cpp", "build_native.ps1")
TOOLS = ("manage.py", "release_tools.py", "release_policy.py", "product_version.py",
         "runtime_state.py", "acceptance_report.py")
SMOKE_CHECKS = ("load_exports", "create", "resize", "destroy")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def baseline_files(root, installer):
    lock = json.loads(read_input(root, "distribution/windows-baselines.json"))
    raw = Path(installer).read_bytes()
    if lock.get("schema") != 1 or digest(raw) != lock["installer_sha256"]:
        raise ValueError("Public baseline installer checksum differs from the locked input")
    if (lock["recovery_version"] != assignment(root / "manage.py", "RECOVERY_VERSION")
            or lock["recovery_payload_sha256"] != assignment(root / "manage.py", "RECOVERY_SHA256")):
        raise ValueError("Recovery lock differs from the install controller")
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        for kind, directory in (("upgrade", ""), ("recovery", "recovery/")):
            version = lock[kind + "_version"]
            name = lock["prefix"] + directory + f"codex-pulse-{version}-payload.zip"
            if names.count(name) != 1:
                raise ValueError(f"Baseline {kind} payload is missing or duplicated")
            data = archive.read(name)
            if digest(data) != lock[kind + "_payload_sha256"]:
                raise ValueError(f"Baseline {kind} payload checksum mismatch")
            manifest = verify_archive(io.BytesIO(data))
            if manifest["version"] != version:
                raise ValueError(f"Baseline {kind} payload version mismatch")
            result[kind] = data
    return lock, result


def check_amd64_dll(data):
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Native component is not a PE DLL")
    offset = struct.unpack_from("<I", data, 60)[0]
    if (offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0"
            or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664
            or not struct.unpack_from("<H", data, offset + 22)[0] & 0x2000
            or struct.unpack_from("<H", data, offset + 24)[0] != 0x20B):
        raise ValueError("Native component must be an AMD64 PE32+ DLL")


def build_evidence(root, revision, native_receipt, smoke_receipt, test_log):
    dll = read_input(root, DLL)
    check_amd64_dll(dll)
    native = json.loads(Path(native_receipt).read_text(encoding="utf-8-sig"))
    smoke = json.loads(Path(smoke_receipt).read_text(encoding="utf-8-sig"))
    source_hashes = {name: digest(read_input(root, name)) for name in NATIVE_SOURCES}
    if (native.get("schema") != 1 or native.get("source_revision") != revision
            or native.get("platform") != "windows-x64" or native.get("dll_sha256") != digest(dll)
            or native.get("source_hashes") != source_hashes):
        raise ValueError("Native build evidence does not match this source and DLL")
    for field in ("compiler_version", "sdk_version"):
        if not isinstance(native.get(field), str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", native[field]):
            raise ValueError(f"Native evidence lacks a concrete {field}")
    if native.get("signature_status") not in ("Valid", "NotSigned"):
        raise ValueError("Native signature status requires investigation")
    if (smoke.get("schema") != 1 or smoke.get("source_revision") != revision
            or smoke.get("dll_sha256") != digest(dll) or smoke.get("platform") != "windows-x64"
            or smoke.get("checks") != dict.fromkeys(SMOKE_CHECKS, True)):
        raise ValueError("Real native smoke check is missing or belongs to another build")
    if type(smoke.get("windows_build")) is not int or smoke["windows_build"] <= 0:
        raise ValueError("Native smoke evidence lacks its Windows build")
    log = Path(test_log).read_bytes()
    text = log.decode("utf-8-sig")
    counts = re.findall(r"(?m)^Ran ([1-9][0-9]*) tests? in [0-9.]+s\s*$", text)
    if len(counts) != 1 or text.strip().splitlines()[-1] != "OK":
        raise ValueError("Windows full regression must finish OK without skips")
    regression = json.loads(Path(test_log).with_name("regression.json").read_text(encoding="utf-8"))
    if (regression.get("schema") != 1 or regression.get("platform") != "windows-x64"
            or regression.get("source_revision") != revision or regression.get("dll_sha256") != digest(dll)
            or regression.get("count") != int(counts[0]) or regression.get("result") != "OK"
            or regression.get("log_sha256") != digest(log)):
        raise ValueError("Windows regression receipt does not match this source, DLL and log")
    if not isinstance(regression.get("python"), str) or not re.fullmatch(r"3\.[0-9]+\.[0-9]+", regression["python"]):
        raise ValueError("Windows regression receipt lacks its Python version")
    # Export only known evidence fields. Build paths and raw logs remain local.
    return {
        "native": {key: native[key] for key in ("schema", "source_revision", "platform", "dll_sha256",
                    "source_hashes", "compiler_version", "sdk_version", "signature_status")},
        "smoke": {key: smoke[key] for key in ("schema", "source_revision", "platform", "dll_sha256", "checks", "windows_build")},
        "regression": {key: regression[key] for key in ("schema", "source_revision", "platform", "dll_sha256",
                       "count", "result", "log_sha256", "python")},
    }


def bundle_files(root, source, baseline, payload, evidence):
    version = source["version"]
    lock, old = baseline_files(root, baseline)
    if version in (lock["upgrade_version"], lock["recovery_version"]):
        raise ValueError("New candidate needs a version distinct from the preserved baselines")
    files = {f"codex-pulse-{version}-payload.zip": payload,
             f"recovery/codex-pulse-{lock['recovery_version']}-payload.zip": old["recovery"],
             "install.ps1": read_input(root, "distribution/install.ps1"),
             "acceptance/README.md": read_input(root, "distribution/ACCEPTANCE.md")}
    tool_files = {name: read_input(root, name) for name in TOOLS}
    check_dependencies(tool_files)
    files.update({"tools/" + name: data for name, data in tool_files.items()})
    for name in ("BETA_GUIDE.md", "RELEASE_NOTES.md", "LICENSE"):
        files[name] = read_input(root, name)
    for target, source_name in (("README.md", "INSTALLER_README.md.in"),
                                ("安装内测版.cmd", "install-candidate.cmd.in"),
                                ("acceptance/收集验收结果.cmd", "collect-acceptance.cmd.in")):
        text = read_input(root, "distribution/" + source_name).decode("utf-8")
        text = text.replace("{{version}}", version)
        if "{{" in text or "}}" in text:
            raise ValueError(f"Unresolved installer template: {source_name}")
        files[target] = (text.replace("\r\n", "\n").replace("\n", "\r\n") if target.endswith(".cmd") else text).encode("utf-8")
    files["build-evidence.json"] = encoded(evidence)
    files["acceptance/RESULTS.json"] = encoded({
        "schema": 1, "version": version, "source_revision": source["source_revision"],
        "payload_sha256": digest(payload), "published": False,
        "results": dict.fromkeys(("fresh_install", "running_beta10_upgrade", "rollback_beta6",
                                  "reupgrade", "preferences_and_history", "native_visuals",
                                  "composer_and_desktop", "sleep_wake", "mixed_dpi", "second_machine"), "not_run"),
    })
    check_payload_links(files)
    return files


def verify_candidate(root, archive, baseline, native_receipt, smoke_receipt, test_log):
    root = Path(root).resolve()
    source = check_source(root, require_clean=True)
    evidence = build_evidence(root, source["source_revision"], native_receipt, smoke_receipt, test_log)
    with zipfile.ZipFile(archive) as bundle, tempfile.TemporaryDirectory(prefix="pulse verify ") as directory:
        names = bundle.namelist()
        payload_name = f"codex-pulse-{source['version']}-payload.zip"
        if names.count(payload_name) != 1 or names.count("candidate-manifest.json") != 1:
            raise ValueError("Candidate package metadata or payload is missing/duplicated")
        payload = bundle.read(payload_name)
        saved = Path(directory) / "payload.zip"
        saved.write_bytes(payload)
        check_archive(root, saved)
        expected = bundle_files(root, source, baseline, payload, evidence)
        if len(names) != len(expected) + 1 or set(names) != set(expected) | {"candidate-manifest.json"}:
            raise ValueError("Candidate wrapper has missing or unexpected files")
        for name, data in expected.items():
            if bundle.read(name) != data:
                raise ValueError(f"Candidate wrapper differs from its declared input: {name}")
        manifest = json.loads(bundle.read("candidate-manifest.json"))
        if manifest != candidate_manifest(source, expected):
            raise ValueError("Candidate wrapper manifest differs from the checked source")
    return {"version": source["version"], "source_revision": source["source_revision"],
            "sha256": digest(Path(archive).read_bytes()), "file_count": len(expected),
            "manual_acceptance": "not_run", "published": False}


def candidate_manifest(source, files):
    return {"schema": 1, "platform": "windows-x64", "version": source["version"],
            "source_revision": source["source_revision"], "published": False,
            "files": {name: digest(data) for name, data in sorted(files.items())}}


def build_candidate(root, output, baseline, native_receipt, smoke_receipt, test_log):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Candidate output already exists; choose a new directory")
    source = check_source(root, require_clean=True)
    evidence = build_evidence(root, source["source_revision"], native_receipt, smoke_receipt, test_log)
    baseline_files(root, baseline)  # Fail before creating an output for invalid old assets.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pulse candidate ", dir=output.parent) as directory:
        payload = Path(directory) / "payload.zip"
        build_archive(root, payload, include_tests=False)
        check_archive(root, payload)
        files = bundle_files(root, source, baseline, payload.read_bytes(), evidence)
        files["candidate-manifest.json"] = encoded(candidate_manifest(source, files))
        with output.open("xb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                bundle.writestr(entry, data)
    return verify_candidate(root, output, baseline, native_receipt, smoke_receipt, test_log)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inputs", "build", "verify"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--native-receipt", type=Path)
    parser.add_argument("--smoke-receipt", type=Path)
    parser.add_argument("--test-log", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "inputs":
            lock, _ = baseline_files(args.root.resolve(), args.baseline)
            result = {"verified": True, "upgrade_version": lock["upgrade_version"],
                      "recovery_version": lock["recovery_version"]}
        else:
            if not all((args.archive, args.native_receipt, args.smoke_receipt, args.test_log)):
                parser.error("build/verify requires --archive, --native-receipt, --smoke-receipt and --test-log")
            operation = build_candidate if args.action == "build" else verify_candidate
            result = operation(args.root, args.archive, args.baseline, args.native_receipt, args.smoke_receipt, args.test_log)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Candidate check failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
