from pathlib import Path
import subprocess,unittest,json

class ComposerWrapperTests(unittest.TestCase):
    def test_actual_powershell_predicate_prefers_visible_shell_over_scrolled_text_extent(self):
        script=r'''
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors)
$fn=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-PulseComposerWrapper'},$true)
if ($errors.Count -or $null -eq $fn) { throw 'Missing or invalid predicate' }
. ([scriptblock]::Create($fn.Extent.Text))
$window=[pscustomobject]@{Top=0;Height=1032;Bottom=1032}
$edit=[pscustomobject]@{Width=461;Height=320;Top=652;Bottom=972}
$shell=[pscustomobject]@{Width=527;Height=328;Top=700;Bottom=1028}
$results=@((Test-PulseComposerWrapper $shell $edit $window 520))
$edit.Height=800;$edit.Top=172
$results+=Test-PulseComposerWrapper $shell $edit $window 520
$shell.Bottom=972
$results+=Test-PulseComposerWrapper $shell $edit $window 520
$shell.Bottom=1028;$shell.Height=933;$shell.Top=95
$results+=Test-PulseComposerWrapper $shell $edit $window 520
$shell.Height=328;$shell.Top=700;$shell.Width=1600
$results+=Test-PulseComposerWrapper $shell $edit $window 520
$results|ConvertTo-Json -Compress
'''
        # Extract only the pure predicate AST. No UIA assembly, window lookup,
        # content read, screenshot or input is executed by this test.
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command','& { '+script+' }',str(Path(__file__).with_name('composer_anchor.ps1'))],capture_output=True,text=True,encoding='utf-8',timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),[True,True,False,False,False])

if __name__=='__main__':unittest.main()
