import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from release_tools import build_archive, digest, install_archive, rollback, verify_archive


def write_fixture_spec(source, runtime, development=()):
    """Prepare a tiny, explicitly declared test payload; no real application data."""
    version = json.loads((source / "plugin.json").read_text())["version"]
    for name, text in {
        "LICENSE": "Test fixture license\n",
        "README.md": f"# Codex Pulse {version}\n[Guide](BETA_GUIDE.md)\n",
        "BETA_GUIDE.md": f"版本：{version}。\n",
        "RELEASE_NOTES.md": f"# {version}\nTest fixture only.\n",
    }.items():
        (source / name).write_text(text, encoding="utf-8")
    (source / "distribution").mkdir(exist_ok=True)
    spec = {
        "schema": 1, "platform": "windows", "version_source": "plugin.json",
        "runtime": sorted(set(runtime) | {"plugin.json", "LICENSE", "README.md",
                          "BETA_GUIDE.md", "RELEASE_NOTES.md", "distribution/windows-package.json"}),
        "development": list(development), "optional_runtime": [], "templates": {},
        "version_documents": {"BETA_GUIDE.md": r"^版本：([^。\s]+)",
                              "RELEASE_NOTES.md": r"^# ([^\s]+)"},
    }
    (source / "distribution/windows-package.json").write_text(json.dumps(spec), encoding="utf-8")


class ReleaseTests(unittest.TestCase):
    def test_license_is_carried_through_full_and_runtime_installations(self):
        for include_tests in (True, False):
            with self.subTest(include_tests=include_tests), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = self.source(directory)
                notice = b"Test copyright and license notice\n"
                (source / "LICENSE").write_bytes(notice)
                archive, target = root / "package.zip", root / "installed"
                build_archive(source, archive, include_tests=include_tests)
                with zipfile.ZipFile(archive) as package:
                    self.assertEqual(package.read("LICENSE"), notice)
                record = install_archive(archive, target, root / "backups")
                self.assertEqual((target / "LICENSE").read_bytes(), notice)
                rollback(record)
                self.assertFalse((target / "LICENSE").exists())

    def source(self, directory, version="0.6.0"):
        source = Path(directory) / "source"
        source.mkdir()
        (source / "plugin.json").write_text(json.dumps({"name": "codex-pulse", "version": version}))
        (source / "overlay.py").write_text("# new implementation\n")
        (source / "new_helper.py").write_text("# new helper\n")
        (source / "server.log").write_text("local log must not ship")
        (source / "settings.json").write_text("local preferences must not ship")
        (source / "logs_2.sqlite").write_text("local records must not ship")
        (source / ".codex-pulse-local.json").write_text("personal install paths must not ship")
        write_fixture_spec(source, ["overlay.py", "new_helper.py"])
        return source

    def test_package_is_reproducible_and_contains_only_release_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(directory)
            first, second = root / "first.zip", root / "second.zip"
            build_archive(source, first)
            build_archive(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(set(verify_archive(first)["files"]), {
                "plugin.json", "overlay.py", "new_helper.py", "LICENSE", "README.md",
                "BETA_GUIDE.md", "RELEASE_NOTES.md", "distribution/windows-package.json"})

    def test_install_rollback_roundtrip_preserves_unrelated_files_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(directory)
            archive = root / "new.zip"
            build_archive(source, archive)
            target = root / "target"
            target.mkdir()
            old_manifest = b'{"name":"codex-pulse","version":"0.5.0"}'
            (target / "plugin.json").write_bytes(old_manifest)
            (target / "overlay.py").write_bytes(b"old implementation\r\n")
            (target / "my_notes.txt").write_text("keep notes")
            (target / "settings.json").write_bytes(b'{"font_size":13,"position":{"gap":24}}')
            before = {file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}
            record = install_archive(archive, target, root / "backups")
            self.assertEqual(json.loads((target / "plugin.json").read_text())["version"], "0.6.0")
            self.assertEqual((target / "settings.json").read_bytes(), before["settings.json"])
            self.assertEqual(rollback(record, dry_run=True)["files"], 8)
            rollback(record)
            self.assertEqual({file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}, before)

    def test_rollback_rejects_later_user_edits_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(directory)
            archive, target = root / "new.zip", root / "target"
            build_archive(source, archive)
            record = install_archive(archive, target, root / "backups")
            (target / "overlay.py").write_text("later user edit")
            before = {file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}
            with self.assertRaisesRegex(ValueError, "changed after upgrade"):
                rollback(record)
            self.assertEqual({file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}, before)

    def test_corrupted_package_is_rejected_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, corrupt = root / "good.zip", root / "bad.zip"
            build_archive(self.source(directory), archive)
            with zipfile.ZipFile(archive) as original, zipfile.ZipFile(corrupt, "w") as modified:
                for name in original.namelist():
                    modified.writestr(name, b"modified" if name == "overlay.py" else original.read(name))
            with self.assertRaisesRegex(ValueError, "checksum"):
                install_archive(corrupt, root / "target", root / "backups")
            self.assertFalse((root / "target").exists())

    def test_partial_write_failure_restores_originals_and_removes_only_own_new_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(directory)
            archive, target = root / "new.zip", root / "target"
            build_archive(source, archive)
            target.mkdir()
            (target / "plugin.json").write_text('{"name":"codex-pulse","version":"0.5.0"}')
            (target / "overlay.py").write_text("original")
            (target / "keep.txt").write_text("unrelated")
            before = {file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}
            real_write = Path.write_bytes
            failed = []
            # Windows TEMP may use an 8.3 alias; installation resolves its paths.
            failure_path = (target / "plugin.json").resolve()
            def write(file, data):
                if file == failure_path and not failed:
                    failed.append(True)
                    raise OSError("simulated local write failure")
                return real_write(file, data)
            with patch.object(Path, "write_bytes", new=write), self.assertRaisesRegex(OSError, "simulated"):
                install_archive(archive, target, root / "backups")
            self.assertEqual(failed, [True])
            self.assertEqual({file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}, before)

    def test_windows_aliases_and_file_directory_conflicts_are_rejected_before_install(self):
        invalid=(('overlay.py','OVERLAY.py'),('assets/icon.svg','assets/icon.svg.'),
                 ('NUL.txt',),('assets/./icon.svg',),('assets','assets/icon.svg'),
                 ('assets/x?.svg',),('assets/icon.svg ',))
        for names in invalid:
            with self.subTest(names=names),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);archive=root/'invalid.zip'
                files={'plugin.json':b'{"name":"codex-pulse","version":"0.6.0"}'}
                files.update({name:str(i).encode() for i,name in enumerate(names)})
                manifest={'name':'codex-pulse','version':'0.6.0','files':{n:digest(v) for n,v in files.items()}}
                with zipfile.ZipFile(archive,'w') as package:
                    for name,data in files.items():package.writestr(name,data)
                    package.writestr('release-manifest.json',json.dumps(manifest))
                with self.assertRaises(ValueError):
                    install_archive(archive,root/'target',root/'backups')
                self.assertFalse((root/'target').exists())
                self.assertFalse((root/'backups').exists())


if __name__ == "__main__":
    unittest.main()
