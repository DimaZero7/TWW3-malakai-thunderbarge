# Starts one battle in the background and returns: tools\battle.ps1 -Label b3
# Output: build\v1\last_run.log (the game is closed by tools\run_battle.py whatever happens).
param([string]$Label = 'run', [int]$Timeout = 720, [switch]$Low)
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$log = Join-Path $repo 'build\v1\last_run.log'
Remove-Item $log, "$log.err" -ErrorAction SilentlyContinue
$a = @('-3.14', "`"$repo\tools\run_battle.py`"", '--label', $Label, '--timeout', $Timeout)
if ($Low) { $a += '--low' }
Start-Process -FilePath py -WindowStyle Hidden -ArgumentList $a -RedirectStandardOutput $log -RedirectStandardError "$log.err"
