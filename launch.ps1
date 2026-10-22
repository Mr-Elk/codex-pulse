param([switch]$Edit)
$ErrorActionPreference = 'Stop'
$pulsePython = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pulsePython) { $pulsePython = (Get-Command python.exe -ErrorAction Stop).Source }
$pulseArguments = @('-B', ('"' + (Join-Path $PSScriptRoot 'launch.py') + '"'))
if ($Edit) { $pulseArguments += '--edit' }
Start-Process -WindowStyle Hidden -FilePath $pulsePython -ArgumentList $pulseArguments
