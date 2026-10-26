from pathlib import Path
import os,subprocess,tempfile,unittest


@unittest.skipUnless(os.name=='nt','Windows PowerShell installer preflight')
class DistributionPreflightTests(unittest.TestCase):
    def test_multiple_python_matches_use_the_first_executable(self):
        import json,sys
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d)/'release 包';stage.mkdir();(stage/'recovery').mkdir();(stage/'tools').mkdir()
            (stage/'codex-pulse-0.7.0-beta.10-payload.zip').write_bytes(b'preflight fixture')
            (stage/'recovery/codex-pulse-0.7.0-beta.6-payload.zip').write_bytes(b'preflight fixture')
            script=stage/'install.ps1';script.write_text(Path(__file__).with_name('distribution').joinpath('install.ps1').read_text(encoding='utf-8'),encoding='utf-8-sig')
            result_file=stage/'invoked.json'
            (stage/'tools/manage.py').write_text('from pathlib import Path\nimport json,sys\nPath('+repr(str(result_file))+').write_text(json.dumps(sys.argv[1:]))\n',encoding='utf-8')
            wrapper=stage/'run.ps1'
            quote=lambda p:"'"+str(p).replace("'","''")+"'"
            wrapper.write_text("function Get-Command { param($Name,$CommandType,$ErrorAction) @([pscustomobject]@{Source="+quote(sys.executable)+"},[pscustomobject]@{Source='unusable-second-python.exe'}) }\n& "+quote(script)+" -InstallRoot "+quote(stage/'target')+"\nexit $LASTEXITCODE\n",encoding='utf-8-sig')
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper)],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            self.assertTrue(result_file.exists(),repr((result.stdout,result.stderr)))
            args=json.loads(result_file.read_text());self.assertEqual(args[0],'install');self.assertIn('--recovery-archive',args)

    def test_missing_python_stops_before_existing_install_or_settings_change(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage=root/'release 包';stage.mkdir();(stage/'recovery').mkdir()
            (stage/'codex-pulse-0.7.0-beta.10-payload.zip').write_bytes(b'not used before preflight')
            (stage/'recovery/codex-pulse-0.7.0-beta.6-payload.zip').write_bytes(b'not used before preflight')
            script=stage/'install.ps1';script.write_text(Path(__file__).with_name('distribution').joinpath('install.ps1').read_text(encoding='utf-8'),encoding='utf-8-sig')
            target=root/'existing';target.mkdir();marker=target/'installation.json';marker.write_bytes(b'keep installation')
            data=target/'data';data.mkdir();settings=data/'settings.json';settings.write_bytes(b'keep settings')
            system_root=Path(os.environ.get('SystemRoot',r'C:\Windows'))
            env=dict(os.environ);env['PATH']=str(system_root/'System32')
            shell=system_root/'System32/WindowsPowerShell/v1.0/powershell.exe'
            result=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-InstallRoot',str(target)],env=env,capture_output=True,timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(marker.read_bytes(),b'keep installation');self.assertEqual(settings.read_bytes(),b'keep settings')
            self.assertFalse((target/'controller').exists())


if __name__=='__main__':unittest.main()
