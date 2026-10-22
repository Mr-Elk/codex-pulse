param([string]$VisualStudio = '')
$ErrorActionPreference = 'Stop'
if (-not $VisualStudio) {
    $finder = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $VisualStudio = & $finder -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (-not $VisualStudio) { throw 'An existing Visual C++ x64 toolchain is required to rebuild the optional backdrop.' }
$out = Join-Path $PSScriptRoot 'assets\native'
$temp = Join-Path $PSScriptRoot 'qa\native-build'
New-Item -ItemType Directory -Force -Path $out,$temp | Out-Null
$script = @"
@call "$VisualStudio\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul
@pushd "$PSScriptRoot"
@cl /nologo /MT /O2 /std:c++20 /EHsc /DWIN32_LEAN_AND_MEAN /DNOMINMAX /LD native_backdrop.cpp /Fo"$temp\native_backdrop.obj" /link windowsapp.lib dwmapi.lib CoreMessaging.lib /OUT:"$out\pulse_backdrop_x64.dll" /IMPLIB:"$temp\pulse_backdrop.lib"
@set pulseBuildExit=%ERRORLEVEL%
@popd
@exit /b %pulseBuildExit%
"@
$batch = Join-Path $temp 'build.cmd'
[IO.File]::WriteAllText($batch, $script, [Text.Encoding]::Default)
& $env:ComSpec /d /c $batch
if ($LASTEXITCODE -ne 0) { throw "Native build failed: $LASTEXITCODE" }
