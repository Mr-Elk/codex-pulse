"""Broken release inputs must fail before publication; fixtures contain no user data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from ci.check_release import check_archive, check_installer, check_payload_links, check_public_guides, check_source
from release_policy import SPEC_PATH, clean_revision, selected_files
from release_tools import build_archive, digest, verify_archive
from test_release_tools import write_fixture_spec


class ReleaseConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pulse release checks ")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / "source"
        self.root.mkdir()
        (self.root / "plugin.json").write_text(json.dumps({"name": "codex-pulse", "version": "1.2.3-beta.4"}))
        (self.root / "overlay.py").write_text("# isolated fixture\n")
        write_fixture_spec(self.root, ["overlay.py"])

    def spec(self, change):
        path = self.root / SPEC_PATH
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))

    def commit(self):
        commands = (["init", "-q"], ["add", "."],
                    ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(self.parent / "no-hooks"),
                     "commit", "-qm", "Fixture source"])
        for args in commands:
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def source_context(self):
        guide = "https://github.com/Mr-Elk/codex-pulse/blob/v1.2.2/BETA_GUIDE.md"
        published = "https://github.com/Mr-Elk/codex-pulse/releases/tag/v1.2.2"
        for name in ("README.md", "README.en.md"):
            (self.root / name).write_text(f"[Download]({published})\n[Guide]({guide})\n")
        (self.root / "manage.py").write_text('RECOVERY_VERSION = "1.0.0"\n')
        (self.root / "distribution/install.ps1").write_text(
            "$pulsePayload = Join-Path $PSScriptRoot 'codex-pulse-1.2.3-beta.4-payload.zip'\n"
            "$pulseRecovery = Join-Path $PSScriptRoot 'recovery\\codex-pulse-1.0.0-payload.zip'\n")

    def test_new_local_code_and_platform_files_are_not_swept_into_payload(self):
        for name in ("new_entry.py", "pulse_cli.py", "settings.json", "assets/private.txt"):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("must not ship")
        files = selected_files(self.root, include_tests=False)
        self.assertFalse(set(files) & {"new_entry.py", "pulse_cli.py", "settings.json", "assets/private.txt"})
        self.assertIn("LICENSE", files)

    def test_missing_declared_asset_fails_before_creating_an_archive(self):
        self.spec(lambda spec: spec["runtime"].append("assets/missing.svg"))
        output = self.parent / "candidate.zip"
        with self.assertRaisesRegex(ValueError, "missing.*assets/missing.svg"):
            build_archive(self.root, output)
        self.assertFalse(output.exists())

    def test_static_and_literal_dynamic_dependencies_must_be_declared(self):
        (self.root / "helper.py").write_text("VALUE = 1\n")
        for code in ("import helper", "__import__('helper')"):
            (self.root / "overlay.py").write_text(code)
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, "unlisted.*helper"):
                selected_files(self.root)
        self.spec(lambda spec: spec["runtime"].append("helper.py"))
        self.assertIn("helper.py", selected_files(self.root))

    def test_stale_candidate_documents_fail_even_when_all_files_exist(self):
        for name, old in (("BETA_GUIDE.md", "版本：1.2.2。\n"), ("RELEASE_NOTES.md", "# 1.2.2\n")):
            path = self.root / name
            original = path.read_bytes()
            path.write_text(old, encoding="utf-8")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "version differs"):
                selected_files(self.root)
            path.write_bytes(original)

    def test_file_present_in_checkout_cannot_satisfy_an_unshipped_document_link(self):
        (self.root / "old-validation.md").write_text("Old evidence")
        (self.root / "README.md").write_text("[Evidence](old-validation.md)")
        with self.assertRaisesRegex(ValueError, "package link target is absent"):
            check_payload_links(selected_files(self.root))

    def test_payload_links_validate_anchors_and_ignore_code_examples(self):
        files = {"README.md": b"[Read](guide.md#missing)\n", "guide.md": b"# Available\n"}
        with self.assertRaisesRegex(ValueError, "anchor is absent"):
            check_payload_links(files)
        files["README.md"] = b"[Read](guide.md#available)\n`[example](absent)`\n"
        check_payload_links(files)

    def test_rendered_readme_uses_product_version_and_rejects_unknown_placeholders(self):
        template = self.root / "distribution/README.md.in"
        template.write_text("# Codex Pulse {{version}}\n[Guide](BETA_GUIDE.md)\n")
        def configure(spec):
            spec["runtime"].remove("README.md")
            spec["templates"]["README.md"] = "distribution/README.md.in"
        self.spec(configure)
        files = selected_files(self.root)
        self.assertTrue(files["README.md"].startswith(b"# Codex Pulse 1.2.3-beta.4\n"))
        template.write_text("{{unknown_version}}")
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            selected_files(self.root)

    def test_wrong_platform_personal_paths_and_duplicate_names_are_rejected(self):
        original = (self.root / SPEC_PATH).read_bytes()
        for name in ("pulse_cli.py", "settings.json", "../outside.py", "PLUGIN.json"):
            self.spec(lambda spec: spec["runtime"].append(name))
            with self.subTest(name=name), self.assertRaises(ValueError):
                selected_files(self.root)
            (self.root / SPEC_PATH).write_bytes(original)

    def test_empty_license_is_not_a_valid_package(self):
        (self.root / "LICENSE").write_text("")
        with self.assertRaisesRegex(ValueError, "license is empty"):
            selected_files(self.root)

    def test_installer_candidate_and_recovery_versions_are_checked_separately(self):
        self.source_context()
        check_installer(self.root, "1.2.3-beta.4")
        path = self.root / "distribution/install.ps1"
        original = path.read_text()
        for old in ("1.2.3-beta.4", "1.0.0"):
            path.write_text(original.replace(old, "0.0.1"))
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, "authoritative version"):
                check_installer(self.root, "1.2.3-beta.4")

    def test_public_guide_tracks_public_download_not_the_new_source_candidate(self):
        self.source_context()
        check_public_guides(self.root)
        path = self.root / "README.en.md"
        path.write_text(path.read_text().replace("blob/v1.2.2/", "blob/main/"))
        with self.assertRaisesRegex(ValueError, "pin its public guide"):
            check_public_guides(self.root)

    def test_existing_archive_is_never_overwritten(self):
        output = self.parent / "candidate.zip"
        output.write_bytes(b"existing candidate")
        with self.assertRaises(FileExistsError):
            build_archive(self.root, output)
        self.assertEqual(output.read_bytes(), b"existing candidate")

    def test_actual_archive_matches_clean_source_and_rejects_later_source(self):
        self.commit()
        output = self.parent / "candidate.zip"
        manifest = build_archive(self.root, output, include_tests=False)
        result = check_archive(self.root, output)
        self.assertEqual(result["version"], "1.2.3-beta.4")
        self.assertEqual(result["archive_sha256"], digest(output.read_bytes()))
        self.assertEqual(manifest["source_revision"], clean_revision(self.root))
        (self.root / "overlay.py").write_text("# changed source\n")
        with self.assertRaisesRegex(ValueError, "clean source"):
            check_archive(self.root, output)
        self.commit()
        with self.assertRaisesRegex(ValueError, "source revision"):
            check_archive(self.root, output)

    def test_rehashed_missing_extra_or_changed_files_do_not_match_source(self):
        self.commit()
        original = self.parent / "original.zip"
        build_archive(self.root, original, include_tests=False)
        with zipfile.ZipFile(original) as package:
            baseline = {name: package.read(name) for name in package.namelist()}
        for mutation in ("missing", "extra", "changed"):
            files = dict(baseline)
            if mutation == "missing":
                files.pop("LICENSE")
            elif mutation == "extra":
                files["pulse_cli.py"] = b"# unexpected platform\n"
            else:
                files["README.md"] = b"different documentation"
            manifest = json.loads(files.pop("release-manifest.json"))
            manifest["files"] = {name: digest(data) for name, data in files.items()}
            files["release-manifest.json"] = json.dumps(manifest).encode()
            output = self.parent / (mutation + ".zip")
            with zipfile.ZipFile(output, "w") as package:
                for name, data in files.items():
                    package.writestr(name, data)
            verify_archive(output)  # Self-consistent hashes alone are insufficient.
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "explicit source package plan"):
                check_archive(self.root, output)

    def test_legacy_recovery_archive_verification_remains_supported(self):
        files = {"plugin.json": b'{"name":"codex-pulse","version":"0.7.0-beta.6"}',
                 "overlay.py": b"# old recovery fixture\n"}
        manifest = {"name": "codex-pulse", "version": "0.7.0-beta.6",
                    "files": {name: digest(data) for name, data in files.items()}}
        output = self.parent / "legacy.zip"
        with zipfile.ZipFile(output, "w") as package:
            for name, data in files.items():
                package.writestr(name, data)
            package.writestr("release-manifest.json", json.dumps(manifest))
        self.assertEqual(verify_archive(output)["version"], "0.7.0-beta.6")

    def test_new_archive_cannot_claim_another_platform_or_unknown_profile(self):
        output = self.parent / "candidate.zip"
        build_archive(self.root, output, include_tests=False)
        with zipfile.ZipFile(output) as package:
            files = {name: package.read(name) for name in package.namelist()}
        original = json.loads(files["release-manifest.json"])
        for key, value in (("platform", "macos"), ("profile", "unknown"),
                           ("profile", ["runtime"]), ("source_revision", "latest")):
            manifest = dict(original)
            manifest[key] = value
            files["release-manifest.json"] = json.dumps(manifest).encode()
            changed = self.parent / (key + ".zip")
            with zipfile.ZipFile(changed, "w") as package:
                for name, data in files.items():
                    package.writestr(name, data)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "metadata"):
                verify_archive(changed)

    def test_clean_source_gate_and_command_failure_status(self):
        self.source_context()
        self.commit()
        result = check_source(self.root, require_clean=True)
        self.assertEqual(result["version"], "1.2.3-beta.4")
        (self.root / "RELEASE_NOTES.md").write_text("# 0.0.1\n")
        command = [sys.executable, "-X", "utf8", "-B", str(Path(__file__).with_name("check_release.py")),
                   "--root", str(self.root)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 1)
        self.assertIn("version differs", run.stderr)


if __name__ == "__main__":
    unittest.main()
