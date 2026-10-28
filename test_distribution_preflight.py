from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parent


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell installer preflight')
class DistributionPreflightTests(unittest.TestCase):
    def fixture(self, directory):
        stage = Path(directory) / 'release 包'
        stage.mkdir()
        (stage / 'recovery').mkdir()
        (stage / 'tools').mkdir()
        version = json.loads((SOURCE / 'plugin.json').read_text(encoding='utf-8'))['version']
        (stage / f'codex-pulse-{version}-payload.zip').write_bytes(b'preflight fixture')
        (stage / 'recovery/codex-pulse-0.7.0-beta.6-payload.zip').write_bytes(b'preflight fixture')
        script = stage / 'install.ps1'
        # Preserve the original BOM; reading UTF-8 then writing UTF-8-SIG added
        # a second BOM and made PowerShell treat param as a command.
        shutil.copyfile(SOURCE / 'distribution/install.ps1', script)
        result_file = stage / 'invoked.json'
        (stage / 'tools/manage.py').write_text(
            'from pathlib import Path\nimport json,sys\nPath(' + repr(str(result_file))
            + ').write_text(json.dumps(sys.argv[1:]))\n', encoding='utf-8')
        return stage, script, result_file

    def test_multiple_python_matches_use_the_first_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            stage, script, result_file = self.fixture(directory)
            wrapper = stage / 'run.ps1'
            wrapper.write_text(
                "function Get-Command { param($Name,$CommandType,$ErrorAction) "
                "@([pscustomobject]@{Source=" + quote(sys.executable)
                + "},[pscustomobject]@{Source='unusable-second-python.exe'}) }\n& "
                + quote(script) + " -InstallRoot " + quote(stage / 'target')
                + "\nexit $LASTEXITCODE\n", encoding='utf-8-sig')
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
                 'Bypass', '-File', str(wrapper)], capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertTrue(result_file.exists(), repr((result.stdout, result.stderr)))
            args = json.loads(result_file.read_text())
            self.assertEqual(args[0], 'install')
            self.assertIn('--recovery-archive', args)

    def test_missing_python_stops_before_existing_install_or_settings_change(self):
        with tempfile.TemporaryDirectory() as directory:
            stage, script, result_file = self.fixture(directory)
            target = Path(directory) / 'existing'
            target.mkdir()
            marker = target / 'installation.json'
            marker.write_bytes(b'keep installation')
            data = target / 'data'
            data.mkdir()
            settings = data / 'settings.json'
            settings.write_bytes(b'keep settings')
            system_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
            env = dict(os.environ)
            env['PATH'] = str(system_root / 'System32')
            shell = system_root / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            result = subprocess.run(
                [str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                 '-File', str(script), '-InstallRoot', str(target)],
                env=env, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Python', result.stderr, 'failure must reach the Python preflight')
            self.assertFalse(result_file.exists(), 'installation must not start')
            self.assertEqual(marker.read_bytes(), b'keep installation')
            self.assertEqual(settings.read_bytes(), b'keep settings')
            self.assertFalse((target / 'controller').exists())


if __name__ == '__main__':
    unittest.main()
