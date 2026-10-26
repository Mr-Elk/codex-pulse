param([string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'CodexPulseBeta'))
$ErrorActionPreference = 'Stop'
$pulsePayload = Join-Path $PSScriptRoot 'codex-pulse-0.7.0-beta.10-payload.zip'
$pulseRecovery = Join-Path $PSScriptRoot 'recovery\codex-pulse-0.7.0-beta.6-payload.zip'
if (!(Test-Path -LiteralPath $pulsePayload) -or !(Test-Path -LiteralPath $pulseRecovery)) {
    Write-Error '安装包不完整：请先解压整个文件夹，保留 recovery 和 tools。现有安装未改变。'
    exit 1
}
$pulseCommand = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$pulseCommand) {
    Write-Error '未找到 Python 3.10 或更高版本（需包含 Tkinter）。请准备运行环境后重试；现有版本未停止，设置未改变。'
    exit 1
}
$pulsePython = $pulseCommand.Source
try {
    & $pulsePython -X utf8 -c "import sys,tkinter; assert sys.version_info >= (3,10)"
    if ($LASTEXITCODE -ne 0) { throw 'Python or Tkinter unavailable' }
} catch {
    Write-Error 'Python 环境不可用：需要 Python 3.10 或更高版本及 Tkinter。现有版本未停止，设置未改变。'
    exit 1
}
& $pulsePython -X utf8 -B (Join-Path $PSScriptRoot 'tools\manage.py') install $pulsePayload --target $InstallRoot --recovery-archive $pulseRecovery
if ($LASTEXITCODE -ne 0) { throw '安装未完成；原设置和备份保留。请查看上面的原因。' }
Write-Output ('安装完成。启动入口位于：' + $InstallRoot)
Write-Output '已准备 beta.6 回退基线；回退后保留当前设置。'
