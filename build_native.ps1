param([string]$VisualStudio = '', [string]$BuildDirectory = '')
$ErrorActionPreference = 'Stop'
if (-not $VisualStudio) {
    $finder = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (!(Test-Path -LiteralPath $finder)) { throw 'Visual Studio Build Tools locator is unavailable; provide -VisualStudio.' }
    $VisualStudio = & $finder -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (-not $VisualStudio) { throw 'An existing Visual C++ x64 toolchain is required to rebuild the optional backdrop.' }
$out = Join-Path $PSScriptRoot 'assets\native'
$dll = Join-Path $out 'pulse_backdrop_x64.dll'
if (Test-Path -LiteralPath $dll) { throw 'An existing native DLL was preserved. Rebuild from a fresh checkout.' }
$temp = if ($BuildDirectory) { [IO.Path]::GetFullPath($BuildDirectory) } else {
    Join-Path $PSScriptRoot ('qa\native-build-' + [guid]::NewGuid().ToString('N'))
}
if (Test-Path -LiteralPath $temp) { throw 'Use a new native build directory.' }
New-Item -ItemType Directory -Force -Path $out | Out-Null
New-Item -ItemType Directory -Path $temp | Out-Null
$sourceHashes = @{}
foreach ($name in @('native_backdrop.cpp','build_native.ps1')) {
    $sourceHashes[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $name)).Hash.ToLowerInvariant()
}
$script = @"
@chcp 65001 >nul
@call "$VisualStudio\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul
@if errorlevel 1 exit /b %ERRORLEVEL%
@echo %VCToolsVersion%>"$temp\compiler-version.txt"
@echo %WindowsSDKVersion%>"$temp\sdk-version.txt"
@pushd "$PSScriptRoot"
@cl /nologo /Bv /MT /O2 /std:c++20 /utf-8 /EHsc /DWIN32_LEAN_AND_MEAN /DNOMINMAX /LD native_backdrop.cpp /Fo"$temp\native_backdrop.obj" /link windowsapp.lib dwmapi.lib CoreMessaging.lib /OUT:"$dll" /IMPLIB:"$temp\pulse_backdrop.lib" >"$temp\compiler.log" 2>&1
@set pulseBuildExit=%ERRORLEVEL%
@popd
@exit /b %pulseBuildExit%
"@
$batch = Join-Path $temp 'build.cmd'
[IO.File]::WriteAllText($batch, $script, (New-Object Text.UTF8Encoding($false)))
& $env:ComSpec /d /c $batch
if ($LASTEXITCODE -ne 0) { throw "Native build failed: $LASTEXITCODE" }
foreach ($name in $sourceHashes.Keys) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $name)).Hash.ToLowerInvariant() -ne $sourceHashes[$name]) {
        throw 'Native source changed during compilation; no build receipt was issued.'
    }
}
$revision = $null
if (Get-Command git.exe -ErrorAction SilentlyContinue) {
    $status = @(& git.exe -C $PSScriptRoot status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -eq 0 -and $status.Count -eq 0) {
        $revision = (& git.exe -C $PSScriptRoot rev-parse HEAD).Trim()
    }
}
$receipt = @{
    schema = 1; platform = 'windows-x64'; source_revision = $revision
    source_hashes = $sourceHashes
    dll_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $dll).Hash.ToLowerInvariant()
    compiler_version = (Get-Content -Raw -LiteralPath (Join-Path $temp 'compiler-version.txt')).Trim()
    sdk_version = (Get-Content -Raw -LiteralPath (Join-Path $temp 'sdk-version.txt')).Trim().TrimEnd('\')
    signature_status = (Get-AuthenticodeSignature -LiteralPath $dll).Status.ToString()
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $temp 'native-build.json')
Write-Output ('Native build receipt: ' + (Join-Path $temp 'native-build.json'))
