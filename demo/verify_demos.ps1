param(
    [int]$WaitSeconds = 12
)

$ErrorActionPreference = "Stop"

$cases = @(
    @{ Name = "deploy_mode1"; Pattern = "odom_speed_limit" },
    @{ Name = "deploy_mode2"; Pattern = "odom_speed_limit" },
    @{ Name = "nav2_compatible_local"; Pattern = "nav2_cmd_vel_speed_limit" },
    @{ Name = "deploy_mode3"; Pattern = "odom_speed_limit" },
    @{ Name = "deploy_mode4_hybrid"; Pattern = "odom_speed_limit" },
    @{ Name = "multi_robot_orchestrated"; Pattern = "robot1_speed" },
    @{ Name = "multi_robot_global"; Pattern = "fleet_minimum_distance" },
    @{ Name = "choreographed_verdicts"; Pattern = "simultaneous_local_violations" },
    @{ Name = "offline_replay"; Pattern = "odom_speed_limit" }
)

$failed = @()
foreach ($case in $cases) {
    $compose = Join-Path $PSScriptRoot "$($case.Name)\docker-compose.yml"
    Write-Host "=== $($case.Name) ==="
    try {
        docker compose -f $compose up --build -d | Out-Host
        Start-Sleep -Seconds $WaitSeconds
        $logs = docker compose -f $compose logs --no-color
        $logs | Out-Host
        $logText = $logs -join [Environment]::NewLine
        if ($logText -notmatch $case.Pattern) {
            $failed += $case.Name
            Write-Host "FAIL: missing $($case.Pattern)" -ForegroundColor Red
        } elseif ($logText -notmatch '"result": false' -or $logText -notmatch '"result": true') {
            $failed += $case.Name
            Write-Host "FAIL: missing violation/recovery cycle" -ForegroundColor Red
        } else {
            Write-Host "PASS: found $($case.Pattern) violation/recovery cycle" -ForegroundColor Green
        }
    } finally {
        docker compose -f $compose down | Out-Host
    }
}

if ($failed.Count -gt 0) {
    throw "Demo verification failed: $($failed -join ', ')"
}
Write-Host "All demo verifications passed." -ForegroundColor Green
