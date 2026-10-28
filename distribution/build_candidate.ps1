param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][string]$BaselineInstaller,
    [string]$Python = 'python.exe',
    [string]$VisualStudio = ''
)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath($OutputDirectory)
$baseline = (Resolve-Path -LiteralPath $BaselineInstaller).Path
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory; existing candidates are preserved.' }
if ($output.StartsWith($source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $output -eq $source) {
    throw 'Put the candidate output outside the source checkout.'
}
if (Test-Path -LiteralPath (Join-Path $source 'assets\native\pulse_backdrop_x64.dll')) {
    throw 'Use a fresh clean checkout without a previous native DLL.'
}
$Python = (Get-Command $Python -CommandType Application | Select-Object -First 1).Source
function Invoke-PulsePython([string[]]$Arguments) {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Candidate preparation stopped; Python exit code: $LASTEXITCODE" }
}
Invoke-PulsePython -Arguments @('-X','utf8','-B','-c',"import sys; assert sys.platform == 'win32' and sys.maxsize > 2**32 and sys.version_info >= (3,10)")
Invoke-PulsePython -Arguments @('-X','utf8','-B',(Join-Path $source 'ci\check_release.py'),'--require-clean')
Invoke-PulsePython -Arguments @('-X','utf8','-B',(Join-Path $PSScriptRoot 'windows_candidate.py'),'inputs','--baseline',$baseline)
New-Item -ItemType Directory -Path $output | Out-Null
$build = Join-Path $output 'native-build'
& (Join-Path $source 'build_native.ps1') -VisualStudio $VisualStudio -BuildDirectory $build
$checks = Join-Path $output 'checks'
Invoke-PulsePython -Arguments @('-X','utf8','-B',(Join-Path $source 'ci\run_windows_tests.py'),'--log-dir',$checks,'--candidate-receipt')
$smoke = Join-Path $output 'native-smoke.json'
Invoke-PulsePython -Arguments @('-X','utf8','-B',(Join-Path $source 'ci\check_native.py'),'--output',$smoke)
$version = (Get-Content -Raw -Encoding UTF8 (Join-Path $source 'plugin.json') | ConvertFrom-Json).version
$archive = Join-Path $output ("codex-pulse-$version-windows.zip")
Invoke-PulsePython -Arguments @('-X','utf8','-B',(Join-Path $PSScriptRoot 'windows_candidate.py'),'build','--archive',$archive,
    '--baseline',$baseline,'--native-receipt',(Join-Path $build 'native-build.json'),'--smoke-receipt',$smoke,
    '--test-log',(Join-Path $checks 'unittest.log'))
Get-FileHash -Algorithm SHA256 -LiteralPath $archive | Format-List
Write-Output 'Local candidate built and verified. Installation/manual acceptance remains pending. Nothing was published.'
