param([string]$Receipt, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
if (-not $Receipt) {
    $pulseLocalReceipt = Join-Path $PSScriptRoot 'latest.json'
    $pulseLocalPointer = Join-Path $PSScriptRoot '.codex-pulse-local.json'
    if (Test-Path -LiteralPath $pulseLocalReceipt) { $Receipt = $pulseLocalReceipt }
    elseif (Test-Path -LiteralPath $pulseLocalPointer) {
        $Receipt = (Get-Content -Raw -LiteralPath $pulseLocalPointer -Encoding UTF8 | ConvertFrom-Json).receipt_file
    } else { $Receipt = Join-Path $env:LOCALAPPDATA 'CodexPulse\releases\latest.json' }
}
if (-not (Test-Path -LiteralPath $Receipt)) { throw '尚无本机升级回退记录。' }
$pulseReceipt = Get-Content -Raw -LiteralPath $Receipt -Encoding UTF8 | ConvertFrom-Json
$pulseController = Split-Path -Parent $Receipt
$pulseTool = Join-Path $pulseController 'release_tools.py'
if (-not (Test-Path -LiteralPath $pulseReceipt.codex_cli)) {
    $pulseReceipt.codex_cli = (Get-Command codex -ErrorAction Stop).Source
}
$pulseVerify = @('-X','utf8','-B',$pulseTool,'rollback',$pulseReceipt.rollback_record,'--dry-run')
& $pulseReceipt.python_path @pulseVerify
if ($LASTEXITCODE -ne 0) { throw '回退检查失败，已保留当前文件。' }
if ($DryRun) { exit 0 }

# Only close our verified helper window. No forced process termination.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PulseCloseWindow {
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hwnd,uint message,IntPtr w,IntPtr l);
}
'@
if (Test-Path -LiteralPath $pulseReceipt.status_file) {
    $pulseStatus = Get-Content -Raw -LiteralPath $pulseReceipt.status_file -Encoding UTF8 | ConvertFrom-Json
    $pulseProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$pulseStatus.pid)
    if ($pulseProcess -and $pulseProcess.CommandLine -like '*codex-pulse*overlay.py*' -and [PulseCloseWindow]::IsWindow([IntPtr]$pulseStatus.overlay_hwnd)) {
        [uint32]$pulseOwnerPid = 0
        [void][PulseCloseWindow]::GetWindowThreadProcessId([IntPtr]$pulseStatus.overlay_hwnd, [ref]$pulseOwnerPid)
        if ($pulseOwnerPid -ne [uint32]$pulseStatus.pid) { throw '统计条窗口身份已变化，停止回退。' }
        $pulseWait = Get-Process -Id $pulseStatus.pid
        [void][PulseCloseWindow]::PostMessage([IntPtr]$pulseStatus.overlay_hwnd, 0x10, [IntPtr]::Zero, [IntPtr]::Zero)
        if (-not $pulseWait.WaitForExit(5000)) { throw '统计条尚未关闭，停止回退。' }
    }
}
& $pulseReceipt.python_path -X utf8 -B $pulseTool rollback $pulseReceipt.rollback_record
if ($LASTEXITCODE -ne 0) { throw '文件回退失败，备份仍已保留。' }
& $pulseReceipt.codex_cli plugin add $pulseReceipt.plugin_selector --json
if ($LASTEXITCODE -ne 0) { throw '源码已回退，插件重新登记失败；请保留回退记录。' }
$pulseListing = & $pulseReceipt.codex_cli plugin list --marketplace $pulseReceipt.marketplace --json | ConvertFrom-Json
$pulsePlugin = @($pulseListing.installed | Where-Object pluginId -eq $pulseReceipt.plugin_selector)
if ($pulsePlugin.Count -ne 1) { throw '无法唯一核对回退后的插件。' }
$pulsePlugin = $pulsePlugin[0]
foreach ($value in @($pulsePlugin.name, $pulsePlugin.marketplaceName, $pulsePlugin.version)) {
    if ($value -notmatch '^[A-Za-z0-9_.-]+$') { throw '插件登记路径无效。' }
}
$pulseCache = Join-Path $pulseReceipt.codex_home ('plugins\cache\' + $pulsePlugin.marketplaceName + '\' + $pulsePlugin.name + '\' + $pulsePlugin.version)
$pulseManifest = Get-Content -Raw -LiteralPath (Join-Path $pulseCache 'plugin.json') -Encoding UTF8 | ConvertFrom-Json
if ($pulseManifest.version -ne $pulseReceipt.previous_version) { throw '回退版本不符，停止自动启动。' }
Start-Process -WindowStyle Hidden -FilePath $pulseReceipt.pythonw_path -ArgumentList @('-B',('"' + (Join-Path $pulseCache 'overlay.py') + '"'),'--status-file',('"' + $pulseReceipt.status_file + '"'),'--settings-file',('"' + $pulseReceipt.settings_file + '"'))
Write-Output ('已回退到 ' + $pulseManifest.version + '，保留当前字号和位置设置。')
