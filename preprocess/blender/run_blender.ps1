# Run a Blender script against the atlas with the project's safety rules (CONVENTIONS section 11):
#   * refuses to start when less than -MinFreeGB of physical memory is available (11.9 GB machine; the low-memory reaper killed an export once)
#   * --disable-autoexec (the atlas's embedded z-anatomy.py never runs) and --python-exit-code 1 (any script error fails the run)
#   * samples Blender's peak working set once a second and prints it, so the next run can be sized
# Usage: powershell -File preprocess\blender\run_blender.ps1 -Script preprocess\blender\export_anatomy.py -Log out.txt -MinFreeGB 3 -ScriptArgs "a|b|c"
param(
  [Parameter(Mandatory = $true)][string]$Script,
  [Parameter(Mandatory = $true)][string]$Log,
  [double]$MinFreeGB = 3.0,
  [string]$ScriptArgs = "",  # script arguments separated by "|"
  [switch]$Empty              # v1.1: an empty factory scene instead of the atlas (texture bakes: no 307 MB file in memory)
)
$ErrorActionPreference = "Stop"
$blender = "D:\tools\blender-4.2.16-windows-x64\blender.exe"
$blend = "D:\coronary-projection-trainer\assets\anatomy\source\Z-Anatomy\Startup.blend"
$freeGB = [math]::Round((Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue / 1024, 2)
Write-Output "available memory: $freeGB GB (minimum $MinFreeGB GB)"
if ($freeGB -lt $MinFreeGB) { Write-Output "REFUSED: not enough free memory; close applications and retry"; exit 2 }
$rest = @($ScriptArgs.Split("|") | Where-Object { $_ -ne "" })
$scene = if ($Empty) { @("--factory-startup") } else { @("`"$blend`"") }
$argList = @("-b", "--disable-autoexec", "--python-exit-code", "1") + $scene + @("--python", "`"$Script`"", "--") + ($rest | ForEach-Object { "`"$_`"" })
$p = Start-Process -FilePath $blender -ArgumentList $argList -PassThru -NoNewWindow -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
$null = $p.Handle   # cache the handle, otherwise ExitCode is empty after exit (Start-Process quirk)
$peak = 0
while (-not $p.HasExited) {
  try { $p.Refresh(); if ($p.WorkingSet64 -gt $peak) { $peak = $p.WorkingSet64 } } catch {}
  Start-Sleep -Milliseconds 1000
}
$p.WaitForExit()
Write-Output ("blender exit code {0}; peak working set {1:N2} GB" -f $p.ExitCode, ($peak / 1GB))
exit $p.ExitCode
