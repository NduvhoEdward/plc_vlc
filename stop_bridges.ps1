$bridgeRoot = $PSScriptRoot
$bridgePidPath = Join-Path $bridgeRoot '.service-pids.json'
if (-not (Test-Path -LiteralPath $bridgePidPath)) { Write-Output 'No saved background services.'; exit }
$bridgeIds = Get-Content -LiteralPath $bridgePidPath | ConvertFrom-Json
foreach ($bridgeRole in @('sender','receiver')) {
    $bridgeProcessId = [int]$bridgeIds.$bridgeRole
    $bridgeProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$bridgeProcessId"
    if ($bridgeProcess -and $bridgeProcess.CommandLine.Contains((Join-Path $bridgeRoot 'run_demo.py')) -and $bridgeProcess.CommandLine.Contains($bridgeRole)) {
        Stop-Process -Id $bridgeProcessId
        Write-Output "$bridgeRole stopped. An interrupted transfer must drain and reconcile before reuse."
    }
}
