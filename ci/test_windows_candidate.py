"""Candidate gates use tiny archives and synthetic PE bytes, never real product builds."""
import io
from contextlib import redirect_stderr
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.run_windows_tests import run_ci, save_receipt
from ci.check_native import main as native_main
from distribution.windows_candidate import (DLL, NATIVE_SOURCES, SMOKE_CHECKS, TOOLS,
    baseline_files, build_candidate, check_amd64_dll, encoded, verify_candidate)
from product_version import windows_version
from release_policy import clean_revision
from release_tools import digest
from test_release_tools import write_fixture_spec

SOURCE = Path(__file__).resolve().parents[1]


def old_payload(version):
    files = {"plugin.json": encoded({"name": "codex-pulse", "version": version}),
             "overlay.py": b"# legacy test fixture, no UI\n"}
    files["release-manifest.json"] = encoded({"name": "codex-pulse", "version": version,
                                             "files": {name: digest(data) for name, data in files.items()}})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


class WindowsCandidateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pulse candidate checks ")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / "source"
        self.root.mkdir()
        (self.root / "plugin.json").write_bytes(encoded({"name": "codex-pulse", "version": "1.2.3"}))
        (self.root / "overlay.py").write_text("# fixture only\n")
        write_fixture_spec(self.root, ["overlay.py"])
        for name in ("README.md", "README.en.md"):
            (self.root / name).write_text(
                "[Download](https://github.com/Mr-Elk/codex-pulse/releases/tag/v1.2.2)\n"
                "[Guide](https://github.com/Mr-Elk/codex-pulse/blob/v1.2.2/BETA_GUIDE.md)\n")
        for name in TOOLS:
            shutil.copyfile(SOURCE / name, self.root / name)
        for name in NATIVE_SOURCES:
            (self.root / name).write_text("// fixture source\n")
        for name in ("ACCEPTANCE.md", "INSTALLER_README.md.in", "install-candidate.cmd.in", "collect-acceptance.cmd.in"):
            shutil.copyfile(SOURCE / "distribution" / name, self.root / "distribution" / name)
        script = (SOURCE / "distribution/install.ps1").read_text(encoding="utf-8-sig")
        (self.root / "distribution/install.ps1").write_text(script.replace(windows_version(SOURCE), "1.2.3"), encoding="utf-8-sig")
        self.recovery = old_payload("0.7.0-beta.6")
        self.upgrade = old_payload("0.7.0-beta.10")
        self.baseline = self.parent / "old.zip"
        with zipfile.ZipFile(self.baseline, "w") as archive:
            archive.writestr("old/codex-pulse-0.7.0-beta.10-payload.zip", self.upgrade)
            archive.writestr("old/recovery/codex-pulse-0.7.0-beta.6-payload.zip", self.recovery)
        path = self.root / "manage.py"
        from manage import RECOVERY_SHA256
        path.write_text(path.read_text().replace(RECOVERY_SHA256, digest(self.recovery)))
        lock = {"schema": 1, "prefix": "old/", "installer_sha256": digest(self.baseline.read_bytes()),
                "upgrade_version": "0.7.0-beta.10", "upgrade_payload_sha256": digest(self.upgrade),
                "recovery_version": "0.7.0-beta.6", "recovery_payload_sha256": digest(self.recovery)}
        (self.root / "distribution/windows-baselines.json").write_bytes(encoded(lock))
        (self.root / ".gitignore").write_text("*.dll\n")
        pe = bytearray(128)
        pe[:2] = b"MZ"
        struct.pack_into("<I", pe, 60, 64)
        pe[64:68] = b"PE\0\0"
        struct.pack_into("<H", pe, 68, 0x8664)
        struct.pack_into("<H", pe, 86, 0x2000)
        struct.pack_into("<H", pe, 88, 0x20B)
        path = self.root / DLL
        path.parent.mkdir(parents=True)
        path.write_bytes(pe)
        spec_path = self.root / "distribution/windows-package.json"
        spec = json.loads(spec_path.read_text())
        spec["optional_runtime"] = [DLL]
        spec_path.write_bytes(encoded(spec))
        self.commit()
        revision = clean_revision(self.root)
        self.native = self.parent / "native.json"
        self.native.write_bytes(encoded({"schema": 1, "source_revision": revision, "platform": "windows-x64",
            "dll_sha256": digest(pe), "source_hashes": {name: digest((self.root / name).read_bytes()) for name in NATIVE_SOURCES},
            "compiler_version": "14.44.35207", "sdk_version": "10.0.26100.0", "signature_status": "NotSigned",
            "private_path": "must not be exported"}))
        self.smoke = self.parent / "smoke.json"
        self.smoke.write_bytes(encoded({"schema": 1, "source_revision": revision, "platform": "windows-x64",
                                       "dll_sha256": digest(pe), "windows_build": 22631,
                                       "checks": dict.fromkeys(SMOKE_CHECKS, True)}))
        self.log = self.parent / "unittest.log"
        self.log.write_bytes(b"Ran 7 tests in 0.123s\n\nOK\n")
        save_receipt(self.parent / "regression.json", self.log, {"source_revision": revision, "dll_sha256": digest(pe)})
        self.output = self.parent / "new.zip"

    def commit(self):
        for args in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(self.parent / "no-hooks"),
                      "commit", "-qm", "Fixture source")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def build(self):
        return build_candidate(self.root, self.output, self.baseline, self.native, self.smoke, self.log)

    def verify(self, path):
        return verify_candidate(self.root, path, self.baseline, self.native, self.smoke, self.log)

    def test_complete_wrapper_is_verifiable_and_manual_results_start_unrun(self):
        result = self.build()
        self.assertEqual(result["version"], "1.2.3")
        self.assertFalse(result["published"])
        self.assertEqual(result["sha256"], digest(self.output.read_bytes()))
        with zipfile.ZipFile(self.output) as archive:
            for name in TOOLS:
                self.assertIn("tools/" + name, archive.namelist())
            self.assertEqual(archive.read("recovery/codex-pulse-0.7.0-beta.6-payload.zip"), self.recovery)
            results = json.loads(archive.read("acceptance/RESULTS.json"))
            self.assertEqual(set(results["results"].values()), {"not_run"})
            self.assertNotIn(b"private_path", archive.read("build-evidence.json"))
            self.assertIn(b"CodexPulseCandidates\\1.2.3", archive.read("安装内测版.cmd"))

    def test_bundled_tools_run_install_and_rollback_without_a_checkout(self):
        self.build()
        bundle = self.parent / "standalone"
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(bundle)  # Our exact, already-verified fixture wrapper.
        controller = bundle / "tools/manage.py"
        target = self.parent / "test install"
        command = [sys.executable, "-X", "utf8", "-B", str(controller)]
        result = subprocess.run([*command, "install", str(bundle / "codex-pulse-1.2.3-payload.zip"),
                                 "--target", str(target), "--recovery-archive",
                                 str(bundle / "recovery/codex-pulse-0.7.0-beta.6-payload.zip")],
                                cwd=bundle, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = target / "data/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_bytes(b'{"unknown":{"keep":true},"font_size":17}')
        before = settings.read_bytes()
        result = subprocess.run([*command, "rollback", "--target", str(target)],
                                cwd=bundle, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((target / "installation.json").read_bytes())["current"], "0.7.0-beta.6")
        self.assertEqual(settings.read_bytes(), before)

    def test_existing_output_and_dirty_source_are_preserved(self):
        self.output.write_bytes(b"keep candidate")
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"keep candidate")
        self.output = self.parent / "other.zip"
        (self.root / "overlay.py").write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "clean Git"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_missing_native_component_cannot_be_hidden_by_optional_payload_rule(self):
        (self.root / DLL).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_wrong_architecture_is_rejected_before_output(self):
        path = self.root / DLL
        data = bytearray(path.read_bytes())
        struct.pack_into("<H", data, 68, 0x14C)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "AMD64"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_stale_native_and_failed_smoke_receipts_cannot_be_reused(self):
        for path, key, value in ((self.native, "source_revision", "0" * 40),
                                 (self.native, "dll_sha256", "0" * 64),
                                 (self.smoke, "checks", dict.fromkeys(SMOKE_CHECKS, False))):
            original = path.read_bytes()
            receipt = json.loads(original)
            receipt[key] = value
            path.write_bytes(encoded(receipt))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build()
            self.assertFalse(self.output.exists())
            path.write_bytes(original)

    def test_skipped_tests_or_old_regression_receipt_block_the_candidate(self):
        original = self.log.read_bytes()
        self.log.write_bytes(b"Ran 7 tests in 0.12s\n\nOK (skipped=1)\n")
        with self.assertRaisesRegex(ValueError, "without skips"):
            self.build()
        self.log.write_bytes(original)
        path = self.parent / "regression.json"
        value = json.loads(path.read_bytes())
        value["source_revision"] = "0" * 40
        path.write_bytes(encoded(value))
        with self.assertRaisesRegex(ValueError, "regression receipt"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_baseline_corruption_is_rejected_without_rewriting_it(self):
        changed = b"invalid old archive"
        self.baseline.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "locked input"):
            self.build()
        self.assertEqual(self.baseline.read_bytes(), changed)
        self.assertFalse(self.output.exists())

    def test_self_consistent_wrapper_tampering_is_rejected_against_source(self):
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            baseline = {name: archive.read(name) for name in archive.namelist()}
        for mutation in ("missing", "extra", "changed"):
            files = dict(baseline)
            manifest = json.loads(files.pop("candidate-manifest.json"))
            if mutation == "missing":
                files.pop("tools/product_version.py")
            elif mutation == "extra":
                files["pulse_cli.py"] = b"must not ship"
            else:
                files["tools/manage.py"] += b"\n# altered tool\n"
            manifest["files"] = {name: digest(data) for name, data in files.items()}
            files["candidate-manifest.json"] = encoded(manifest)
            changed = self.parent / (mutation + ".zip")
            with zipfile.ZipFile(changed, "w") as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "wrapper"):
                self.verify(changed)

    def test_failed_or_changed_source_run_never_issues_a_success_receipt(self):
        for codes, identities in (([0, 9], [{"source_revision": "a"}]),
                                  ([0, 0], [{"source_revision": "a"}, {"source_revision": "b"}])):
            directory = self.parent / ("logs-" + str(codes[-1]))
            with patch("ci.run_windows_tests.run_logged", side_effect=codes), \
                    patch("ci.run_windows_tests.candidate_identity", side_effect=identities):
                if codes[-1]:
                    self.assertEqual(run_ci(directory, candidate_receipt=True), 9)
                else:
                    with self.assertRaisesRegex(ValueError, "changed during"):
                        run_ci(directory, candidate_receipt=True)
            self.assertFalse((directory / "regression.json").exists())

    def test_stalled_native_worker_fails_without_issuing_evidence(self):
        output = self.parent / "stalled-native.json"
        with patch("ci.check_native.subprocess.run", side_effect=subprocess.TimeoutExpired("native", 45)), \
                redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(native_main(["--output", str(output)]), 124)
        self.assertIn("timed out", errors.getvalue())
        self.assertFalse(output.exists())


@unittest.skipUnless(sys.platform == "win32", "Candidate PowerShell entry requires Windows")
class CandidatePowerShellTests(unittest.TestCase):
    """Run the real wrapper with isolated boundary stubs, never a compiler or product."""

    def setUp(self):
        # pwsh -> Python -> powershell.exe otherwise inherits PowerShell 7 modules.
        # Let Windows PowerShell construct its own search path, without changing
        # the parent environment or the user's persistent configuration.
        self.powershell_env = {key: value for key, value in os.environ.items()
                               if key.upper() != "PSMODULEPATH"}

    @staticmethod
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    def fixture(self, directory, failure=""):
        parent = Path(directory)
        source = parent / "source 中文 with spaces"
        (source / "distribution").mkdir(parents=True)
        (source / "ci").mkdir()
        script = source / "distribution/build_candidate.ps1"
        shutil.copyfile(SOURCE / "distribution/build_candidate.ps1", script)
        (source / "plugin.json").write_text('{"version":"1.2.3"}', encoding="utf-8")
        baseline = parent / "old input.zip"
        baseline.write_bytes(b"boundary fixture only")
        events = parent / "steps.txt"

        def boundary(name, step, tail=""):
            code = ("from pathlib import Path\nimport sys\n"
                    f"step = {step}\n"
                    f"with Path({str(events)!r}).open('a', encoding='utf-8') as log: log.write(step + '\\n')\n"
                    f"if step == {failure!r}: sys.exit(23)\n" + tail)
            (source / name).write_text(code, encoding="utf-8")

        boundary("ci/check_release.py", "'source'", "assert sys.argv[1:] == ['--require-clean']\n")
        boundary("ci/run_windows_tests.py", "'tests'", "assert '--candidate-receipt' in sys.argv\n")
        boundary("ci/check_native.py", "'smoke'", "assert '--output' in sys.argv\n")
        boundary("distribution/windows_candidate.py", "sys.argv[1]",
                 f"assert Path(sys.argv[sys.argv.index('--baseline') + 1]) == Path({str(baseline)!r})\n"
                 "if step == 'build':\n"
                 "    assert '--native-receipt' in sys.argv and '--smoke-receipt' in sys.argv and '--test-log' in sys.argv\n"
                 "    Path(sys.argv[sys.argv.index('--archive') + 1]).write_bytes(b'wrapper boundary fixture')\n")
        native = ("param([string]$VisualStudio = '', [string]$BuildDirectory)\n"
                  f"Add-Content -LiteralPath {self.quote(events)} -Encoding UTF8 -Value 'native'\n"
                  f"if ({self.quote(failure)} -eq 'native') {{ throw 'Controlled native build failure' }}\n"
                  "New-Item -ItemType Directory -Path $BuildDirectory | Out-Null\n")
        (source / "build_native.ps1").write_text(native, encoding="utf-8-sig")
        output = parent / "candidate output 中文"
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-File", str(script), "-OutputDirectory", str(output),
                   "-BaselineInstaller", str(baseline), "-Python", sys.executable]
        return command, output, events

    def test_real_wrapper_passes_spaced_paths_and_boundaries_in_order(self):
        with tempfile.TemporaryDirectory(prefix="pulse script checks ") as directory:
            command, output, events = self.fixture(directory)
            result = subprocess.run(command, cwd=directory, env=self.powershell_env, capture_output=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(events.read_text(encoding="utf-8-sig").splitlines(),
                             ["source", "inputs", "native", "tests", "smoke", "build"])
            self.assertEqual((output / "codex-pulse-1.2.3-windows.zip").read_bytes(), b"wrapper boundary fixture")

    def test_failed_boundary_stops_before_packaging(self):
        for failure, last in (("source", "source"), ("native", "native"), ("tests", "tests"), ("smoke", "smoke")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="pulse script failure ") as directory:
                command, output, events = self.fixture(directory, failure)
                result = subprocess.run(command, cwd=directory, env=self.powershell_env, capture_output=True, timeout=45)
                self.assertNotEqual(result.returncode, 0)
                steps = events.read_text(encoding="utf-8-sig").splitlines()
                self.assertEqual(steps[-1], last)
                self.assertNotIn("build", steps)
                self.assertFalse((output / "codex-pulse-1.2.3-windows.zip").exists())

    def test_builtin_hash_and_signature_checks_load_in_system_powershell(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "unsigned.ps1"
            sample.write_bytes(b"# isolated unsigned fixture, never executed\n")
            command = ("$ErrorActionPreference = 'Stop'; @{ hash = "
                       "(Get-FileHash -Algorithm SHA256 -LiteralPath " + self.quote(sample) +
                       ").Hash.ToLowerInvariant(); signature = "
                       "(Get-AuthenticodeSignature -LiteralPath " + self.quote(sample) +
                       ").Status.ToString() } | ConvertTo-Json -Compress")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                    env=self.powershell_env, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(json.loads(result.stdout),
                             {"hash": digest(sample.read_bytes()), "signature": "NotSigned"})

    def test_native_and_candidate_scripts_parse_in_windows_powershell(self):
        paths = [SOURCE / name for name in ("build_native.ps1", "distribution/build_candidate.ps1", "distribution/install.ps1")]
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "parse.ps1"
            script.write_text("$ErrorActionPreference = 'Stop'\nforeach ($path in @(" +
                              ",".join(self.quote(path) for path in paths) + ")) {\n"
                              "  $tokens = $null; $errors = $null\n"
                              "  [System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors) | Out-Null\n"
                              "  if ($errors.Count) { throw ($errors | Out-String) }\n}\n", encoding="utf-8-sig")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script)],
                                    env=self.powershell_env, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
