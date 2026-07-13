Set-StrictMode -Version Latest

function Test-HiveMindTcpReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$Host,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($Host, $Port)
        return $task.Wait(2000) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-HiveMindHttpReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][int[]]$AcceptedStatus
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return $AcceptedStatus -contains [int]$response.StatusCode
    } catch {
        $response = $_.Exception.Response
        return $null -ne $response -and $AcceptedStatus -contains [int]$response.StatusCode
    }
}

function Test-HiveMindFullStackReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][ValidateSet("local-min", "local-full")][string]$Profile,
        [scriptblock]$Probe,
        [ValidateRange(1, 900)][int]$TimeoutSeconds = 180
    )

    if ($Profile -eq "local-min") {
        return [pscustomobject]@{ Ready = $true; Missing = @(); Diagnostics = @() }
    }

    $required = @("docker-desktop", "milvus", "ragflow", "falkordb", "syncthing-watcher")
    $probeService = if ($null -ne $Probe) {
        $Probe
    } else {
        {
            param([string]$Name)
            switch ($Name) {
                "docker-desktop" { & docker info --format "{{.ServerVersion}}" *> $null; return $LASTEXITCODE -eq 0 }
                "milvus" { return Test-HiveMindTcpReadiness -Host "127.0.0.1" -Port 19530 }
                "ragflow" { return Test-HiveMindHttpReadiness -Url "http://127.0.0.1:9380/api/v1/system/healthz" -AcceptedStatus @(200) }
                "falkordb" { return Test-HiveMindTcpReadiness -Host "127.0.0.1" -Port 6379 }
                "syncthing-watcher" { return Test-HiveMindHttpReadiness -Url "http://127.0.0.1:8384/rest/noauth/health" -AcceptedStatus @(200, 401, 403) }
                default { return $false }
            }
        }
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $missing = @($required | Where-Object { -not (& $probeService $_) })
        if ($missing.Count -eq 0 -or $null -ne $Probe) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    return [pscustomobject]@{
        Ready = $missing.Count -eq 0
        Missing = $missing
        Diagnostics = @($missing | ForEach-Object { "required service is not ready: $_" })
    }
}

