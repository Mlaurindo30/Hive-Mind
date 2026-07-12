[CmdletBinding()]
param(
    [string]$Url = "http://127.0.0.1:37700/api/health"
)

$ErrorActionPreference = "Stop"
try {
    $health = Invoke-RestMethod -Uri $Url -TimeoutSec 5
    if ($health.initialized -eq $true) {
        Write-Host "claude-mem worker healthy"
        exit 0
    }
    Write-Warning "claude-mem worker responded but is not initialized"
    exit 1
} catch {
    Write-Warning "claude-mem worker health check failed: $($_.Exception.Message)"
    exit 1
}
