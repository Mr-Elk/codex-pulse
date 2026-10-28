import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import manage
from release_tools import build_archive,install_archive
from runtime_state import read_json
from test_release_tools import write_fixture_spec


class BetaInstallTests(unittest.TestCase):
    def package(self, root, version):
        source=root/("source-"+version);source.mkdir()
        (source/"plugin.json").write_text(json.dumps({"name":"codex-pulse","version":version}))
        (source/"overlay.py").write_text("version="+repr(version))
        (source/"test_example.py").write_text("# test fixture")
        (source/"rollback.ps1").write_text("legacy plugin rollback must not enter portable beta")
        (source/"回退上一版本.cmd").write_text("legacy entry")
        write_fixture_spec(source, ["overlay.py"], ["test_example.py", "rollback.ps1", "回退上一版本.cmd"])
        archive=root/(version+".zip")
        build_archive(source,archive,include_tests=False)
        return archive

    def test_fresh_install_upgrade_actual_rollback_preserve_preferences(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/"beta with spaces"
            v1=self.package(root,"0.6.17");v2=self.package(root,"0.6.18-beta.1")
            manage.install(v1,target)
            settings=target/"data"/"settings.json";settings.parent.mkdir()
            original=b'{"theme_color":"#166daa","font_size":17,"unknown":{"preserve":true}}'
            settings.write_bytes(original)
            manage.install(v2,target)
            self.assertEqual(read_json(target/"installation.json")["current"],"0.6.18-beta.1")
            manage.rollback(target,dry_run=True)
            manage.rollback(target)
            self.assertEqual(read_json(target/"installation.json")["current"],"0.6.17")
            self.assertEqual(settings.read_bytes(),original)
            self.assertFalse((target/"versions"/"0.6.18-beta.1"/"test_example.py").exists())
            self.assertFalse((target/"versions"/"0.6.18-beta.1"/"rollback.ps1").exists())
            self.assertFalse((target/"versions"/"0.6.18-beta.1"/"回退上一版本.cmd").exists())
            self.assertTrue((target/"controller"/"manage.py").exists())

    def test_rollback_preserves_later_user_edits_and_active_version(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/"beta"
            manage.install(self.package(root,"0.6.17"),target)
            manage.install(self.package(root,"0.6.18-beta.1"),target)
            edited=target/"versions"/"0.6.17"/"overlay.py";edited.write_text("user edit")
            before=(target/"installation.json").read_bytes()
            with self.assertRaisesRegex(ValueError,"changed"):
                manage.rollback(target)
            self.assertEqual((target/"installation.json").read_bytes(),before)
            self.assertEqual(edited.read_text(),"user edit")

    def test_copied_controller_runs_without_the_developer_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'standalone'
            manage.install(self.package(root, '0.6.17'), target)
            result = subprocess.run(
                [sys.executable, '-X', 'utf8', '-B', str(target / 'controller/manage.py'),
                 'status', '--target', str(target)], cwd=target,
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('running', json.loads(result.stdout))

    def test_unrelated_target_and_archive_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/"notes";target.mkdir();(target/"note.txt").write_text("keep")
            with self.assertRaisesRegex(ValueError,"empty folder"):
                manage.install(self.package(root,"0.6.17"),target)
            with self.assertRaisesRegex(ValueError,"Invalid package version"):
                manage.version_dir(root,"../outside")
            self.assertEqual(list(target.iterdir()),[target/"note.txt"])

    @unittest.skipUnless(sys.platform=='win32','Legacy rollback entry requires Windows PowerShell')
    def test_plugin_rollback_uses_supervisor_when_present_and_keeps_old_version_fallback(self):
        for supervised in (True,False):
            with self.subTest(supervised=supervised),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);controller=root/'controller';controller.mkdir()
                for name in ('release_tools.py', 'release_policy.py', 'product_version.py'):
                    shutil.copy2(Path(__file__).with_name(name), controller/name)
                target=root/'source';target.mkdir()
                old=b'{"name":"codex-pulse","version":"0.6.17"}'
                (target/'plugin.json').write_bytes(old)
                archive=self.package(root,'0.6.18-beta.5')
                record=install_archive(archive,target,root/'backups')
                codex=root/'codex-home';cache=codex/'plugins'/'cache'/'qa'/'codex-pulse'/'0.6.17';cache.mkdir(parents=True)
                (cache/'plugin.json').write_bytes(old)
                marker=root/'started.json'
                writer="import json,sys\nfrom pathlib import Path\nPath("+repr(str(marker))+").write_text(json.dumps({'entry':Path(__file__).name,'args':sys.argv[1:]}),encoding='utf-8')\n"
                (cache/'overlay.py').write_text(writer,encoding='utf-8')
                if supervised:(cache/'launch.py').write_text(writer,encoding='utf-8')
                cli=root/'fake_cli.py'
                listing={'installed':[{'pluginId':'codex-pulse@qa','name':'codex-pulse','marketplaceName':'qa','version':'0.6.17'}]}
                cli.write_text('import json\nprint(json.dumps('+repr(listing)+'))\n',encoding='utf-8')
                cli_entry=root/'fake_codex.cmd'
                cli_entry.write_text('@echo off\r\n"'+sys.executable+'" -X utf8 -B "'+str(cli)+'" %*\r\n',encoding='utf-8')
                receipt={'python_path':sys.executable,'pythonw_path':sys.executable,'codex_cli':str(cli_entry),
                         'rollback_record':str(record),'plugin_selector':'codex-pulse@qa','marketplace':'qa',
                         'codex_home':str(codex),'previous_version':'0.6.17',
                         'status_file':str(root/'runtime.json'),'settings_file':str(root/'settings.json')}
                path=controller/'latest.json';path.write_text(json.dumps(receipt),encoding='utf-8')
                completed=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                                          str(Path(__file__).with_name('rollback.ps1')),'-Receipt',str(path)],
                                         capture_output=True,timeout=20)
                self.assertEqual(completed.returncode,0,completed.stderr.decode(errors='replace'))
                deadline=time.monotonic()+4
                while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
                started=read_json(marker)
                self.assertEqual(started['entry'],'launch.py' if supervised else 'overlay.py')
                self.assertIn(str(root/'settings.json'),started['args'])
                self.assertIn(str(root/'runtime.json'),started['args'])
                self.assertEqual((target/'plugin.json').read_bytes(),old)
