# Starts a test session in the background: tools\session.ps1 -Label x -Packs harness,campaign [-Save name] [-Timeout 1800]
param([string]$Label = 'session', [string[]]$Packs = @('harness'), [string]$Save = '', [int]$Timeout = 1800, [switch]$Plain, [switch]$High, [string]$GameArgs = '', [string[]]$UserMods = @(), [string]$UserModsFile = '')
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$log = Join-Path $repo 'build\campaign\session.log'
Remove-Item $log, "$log.err" -ErrorAction SilentlyContinue
$a = @('-3.14', "`"$repo\tools\run_game.py`"", '--label', $Label, '--timeout', $Timeout, '--packs') + $Packs
if ($UserMods.Count -gt 0) { $a += '--user-mods'; foreach ($m in $UserMods) { $a += "`"$m`"" } }
if ($UserModsFile) { $a += @('--user-mods-file', "`"$UserModsFile`"") }
if ($GameArgs) { $a += @('--args', "`"$GameArgs`"") }
if ($High) { $a += '--high-graphics' }
if ($Plain) { $a += '--plain-settings' }
if ($Save) { $a += @('--save', "`"$Save`"") }
Start-Process -FilePath py -WindowStyle Hidden -ArgumentList $a -RedirectStandardOutput $log -RedirectStandardError "$log.err"
