import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from release_tools import build_archive, digest, install_archive, rollback, verify_archive


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
        (source / "overlay.py").write_text("new implementation\n")
        (source / "new_helper.py").write_text("new helper\n")
        (source / "server.log").write_text("local log must not ship")
        (source / "settings.json").write_text("local preferences must not ship")
        (source / "logs_2.sqlite").write_text("local records must not ship")
        (source / ".codex-pulse-local.json").write_text("personal install paths must not ship")
        return source

    def test_package_is_reproducible_and_contains_only_release_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(directory)
            first, second = root / "first.zip", root / "second.zip"
            build_archive(source, first)
            build_archive(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(set(verify_archive(first)["files"]), {"plugin.json", "overlay.py", "new_helper.py"})

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
            before = {file.name: file.read_bytes() for file in target.iterdir()}
            record = install_archive(archive, target, root / "backups")
            self.assertEqual(json.loads((target / "plugin.json").read_text())["version"], "0.6.0")
            self.assertEqual((target / "settings.json").read_bytes(), before["settings.json"])
            self.assertEqual(rollback(record, dry_run=True)["files"], 3)
            rollback(record)
            self.assertEqual({file.name: file.read_bytes() for file in target.iterdir()}, before)

    def test_rollback_rejects_later_user_edits_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(directory)
            archive, target = root / "new.zip", root / "target"
            build_archive(source, archive)
            record = install_archive(archive, target, root / "backups")
            (target / "overlay.py").write_text("later user edit")
            before = {file.name: file.read_bytes() for file in target.iterdir()}
            with self.assertRaisesRegex(ValueError, "changed after upgrade"):
                rollback(record)
            self.assertEqual({file.name: file.read_bytes() for file in target.iterdir()}, before)

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
            before = {file.name: file.read_bytes() for file in target.iterdir()}
            real_write = Path.write_bytes
            failed = []
            def write(file, data):
                if file == target / "plugin.json" and not failed:
                    failed.append(True)
                    raise OSError("simulated local write failure")
                return real_write(file, data)
            with patch.object(Path, "write_bytes", new=write), self.assertRaisesRegex(OSError, "simulated"):
                install_archive(archive, target, root / "backups")
            self.assertEqual({file.name: file.read_bytes() for file in target.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
