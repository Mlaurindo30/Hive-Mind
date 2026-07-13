[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$Check = $false
$List  = $false

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking

$python = Get-HiveMindPython -Root $Root
$server = Join-Path $Root "scripts\services\sinapse-mcp.py"
$ServerName = "sinapse-memory"
$PromptSrc = Join-Path $Root "config\sinapse-agent-prompt.md"

$VALID_AGENTS = @("claude","codex","gemini","qwen","kimi","kiro","kilo","roo","vscode","cursor","opencode","openclaw","swarmclaw")

# --- argument parsing (subset of register-mcp.sh) ---------------------------------
$CodexOnly = $false
$ClaudeOnly = $false
$Only = ""
$InjectPrompt = $true
# -Only, -CodexOnly, -ClaudeOnly, -Check, -List, -NoInstructions e agentes
# posicionais. Mesma semantica do register-mcp.sh.
$Only        = ''
$CodexOnly   = $false
$ClaudeOnly  = $false
$List        = $false
$InjectPrompt = $true
$positional  = @()
foreach ($arg in $Rest) {
    if ($arg -eq '-Only' -or $arg -eq '--only' -or $arg -eq '-Self' -or $arg -eq '--self' -or $arg -eq '-Agent' -or $arg -eq '--agent') { continue }
    if ($arg -like '-Only=*' -or $arg -like '--only=*') { $Only = $arg.Split('=',2)[1]; continue }
    switch -Regex ($arg) {
        '^(?:-{1,2})check$'              { $Check = $true }
        '^(?:-{1,2})list$'               { $List  = $true }
        '^(?:-{1,2})no-instructions$'    { $InjectPrompt = $false }
        '^(?:-{1,2})codex-only$'         { $CodexOnly = $true }
        '^(?:-{1,2})claude-only$'        { $ClaudeOnly = $true }
        '^(?:-{1,2})codexonly$'          { $CodexOnly = $true }
        '^(?:-{1,2})claudeonly$'         { $ClaudeOnly = $true }
        default { $positional += $arg }
    }
}
if (-not $Only -and $positional.Count -gt 0) { $Only = $positional[0] }
if ($List) { Write-Host ($VALID_AGENTS -join ' '); exit 0 }
if ($Only) {
    if ($VALID_AGENTS -notcontains $Only) {
        Write-Error "agente invalido: '$Only'. Validos: $($VALID_AGENTS -join ' ')"
        exit 2
    }
}

# --- shared helpers ---------------------------------------------------------------

function ConvertTo-PlainHashtable {
    param([Parameter(Mandatory = $true)]$Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary]) {
        $r = @{}; foreach ($k in $Value.Keys) { $r[$k] = ConvertTo-PlainHashtable $Value[$k] }; return $r
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $items = @(); foreach ($i in $Value) { $items += ConvertTo-PlainHashtable $i }; return $items
    }
    if ($Value.PSObject.Properties.Count -gt 0 -and $Value -isnot [string]) {
        $r = @{}; foreach ($p in $Value.PSObject.Properties) { $r[$p.Name] = ConvertTo-PlainHashtable $p.Value }; return $r
    }
    return $Value
}

function Test-McpJsonRegistered {
    param([string]$Path, [string]$ServerName, [string]$RootKey = "mcpServers")
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try { $cfg = ConvertTo-PlainHashtable (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json) }
    catch { return $false }
    if ($null -eq $cfg) { return $false }
    $servers = $cfg[$RootKey]
    if ($null -eq $servers) { return $false }
    return $servers.ContainsKey($ServerName)
}

function Test-McpConfigTomlRegistered {
    param([string]$Path, [string]$ServerName)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $content = Get-Content -Raw -LiteralPath $Path
    $pattern = '^\s*\[\s*mcp_servers\.' + [regex]::Escape($ServerName) + '\s*\]\s*$'
    return [regex]::IsMatch($content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
}

function Write-Status {
    param([string]$Path, [bool]$Ok, [string]$Hint = "")
    $label = if ($Ok) { "configured" } else { "missing" }
    Write-Host "$Path : $label$Hint"
}

function Merge-McpConfig {
    param(
        [string]$Path,
        [string]$ServerName,
        [hashtable]$Entry,
        [string]$RootKey = "mcpServers"
    )
    $dir = Split-Path -Parent $Path
    Ensure-HiveMindDirectory -Path $dir
    $cfg = @{}
    if (Test-Path -LiteralPath $Path) {
        try { $cfg = ConvertTo-PlainHashtable (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json) }
        catch { Write-Warning "Invalid JSON in $Path; skipping"; return }
    }
    if (-not $cfg.ContainsKey($RootKey)) { $cfg[$RootKey] = @{} }
    if ($Check) {
        $ok = $cfg[$RootKey].ContainsKey($ServerName)
        Write-Status $Path $ok
        return
    }
    $cfg[$RootKey][$ServerName] = $Entry
    $cfg | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path -Encoding UTF8
    Write-Host "registered $ServerName in $Path"
}

function Merge-McpConfigToml {
    param([string]$Path, [string]$ServerName, [string]$Command, [string[]]$Args, [hashtable]$Env)
    $dir = Split-Path -Parent $Path
    Ensure-HiveMindDirectory -Path $dir
    $content = if (Test-Path -LiteralPath $Path) { Get-Content -Raw -LiteralPath $Path } else { "" }

    $argStr = ($Args | ForEach-Object { '"' + ($_ -replace '\\','\\') + '"' }) -join ", "
    $envLines = ($Env.GetEnumerator() | ForEach-Object { "$($_.Key) = `"$($_.Value -replace '\\','\\')`"" }) -join "`n"
    $block = "`n[mcp_servers.${ServerName}]`ncommand = `"$($Command -replace '\\','\\')`"`nargs = [$argStr]`nstartup_timeout_sec = 30`n`n[mcp_servers.${ServerName}.env]`n$envLines`n"

    $pattern = '^\s*\[\s*mcp_servers\.' + [regex]::Escape($ServerName) + '(\.[^\]]+)?\s*\][^\r\n]*\r?\n(?:[^\[\r\n]*\r?\n)*'

    if ($Check) {
        $ok = Test-McpConfigTomlRegistered -Path $Path -ServerName $ServerName
        Write-Status $Path $ok
        return
    }
    if ([regex]::IsMatch($content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)) {
        $content = [regex]::Replace($content, $pattern, $block.TrimStart("`r`n"), [System.Text.RegularExpressions.RegexOptions]::Multiline)
    } else {
        $trimmed = $content.TrimEnd("`r","`n")
        $content = $trimmed + "`r`n" + $block
    }
    Set-Content -LiteralPath $Path -Value $content -Encoding UTF8
    Write-Host "registered $ServerName in $Path"
}

function Remove-HiveMindLegacy {
    param([hashtable]$LegacyEntries, [string]$RootKey = "mcpServers")
    foreach ($legacy in @("claude-mem-local", "neural-memory-local")) {
        if ($LegacyEntries.ContainsKey($legacy)) { $LegacyEntries.Remove($legacy) }
    }
}

# --- per-agent entry builders -----------------------------------------------------

function Get-StdioEntry {
    @{
        command = $python
        args = @($server)
        cwd = $Root
        env = @{ PYTHONPATH = $Root; SINAPSE_HOME = $Root }
    }
}

function Get-StdioEntryNoCwd {
    @{
        command = $python
        args = @($server)
        env = @{ PYTHONPATH = $Root; SINAPSE_HOME = $Root }
    }
}

# --- per-agent registrars ---------------------------------------------------------

function Register-Claude {
    $entry = Get-StdioEntry
    $claudeJson = Join-Path $env:USERPROFILE ".claude.json"
    $projMcp = Join-Path $Root ".mcp.json"
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue

    if ($Check) {
        if ($claudeCmd) {
            & $claudeCmd.Source mcp get sinapse-memory *> $null
            if ($LASTEXITCODE -eq 0) { Write-Host "$claudeJson : configured (via 'claude mcp get')" }
            else { Write-Host "$claudeJson : missing (no 'claude mcp get' hit)" }
        } else {
            Write-Status $claudeJson (Test-McpJsonRegistered -Path $claudeJson -ServerName $ServerName)
        }
        Write-Status $projMcp (Test-McpJsonRegistered -Path $projMcp -ServerName $ServerName)
        return
    }

    if ($claudeCmd) {
        & $claudeCmd.Source mcp remove sinapse-memory -s user *> $null
        & $claudeCmd.Source mcp add sinapse-memory -s user -e PYTHONPATH="$Root" -- $python $server
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "claude mcp add failed; falling back to JSON edit"
            Merge-McpConfig -Path $claudeJson -ServerName $ServerName -Entry $entry
        } else { Write-Host "registered sinapse-memory via 'claude mcp add' -> $claudeJson" }
    } else {
        Merge-McpConfig -Path $claudeJson -ServerName $ServerName -Entry $entry
    }
    Merge-McpConfig -Path $projMcp -ServerName $ServerName -Entry $entry
}

function Register-Codex {
    $configPath = Join-Path $env:USERPROFILE ".codex\config.toml"
    $jsonPath   = Join-Path $env:USERPROFILE ".codex\mcp.json"
    $codexCmd = Get-Command codex -ErrorAction SilentlyContinue

    if ($Check) {
        Write-Status $configPath (Test-McpConfigTomlRegistered -Path $configPath -ServerName $ServerName)
        Write-Status $jsonPath (Test-McpJsonRegistered -Path $jsonPath -ServerName $ServerName) "(optional mirror)"
        if (-not $codexCmd) { Write-Host "  (note) 'codex' CLI not on PATH" }
        return
    }

    if ($codexCmd) {
        foreach ($s in @("claude-mem-local","neural-memory-local","sinapse-memory")) {
            & $codexCmd.Source mcp remove $s *> $null
        }
        & $codexCmd.Source mcp add sinapse-memory --env PYTHONPATH="$Root" -- $python $server
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "codex mcp add failed; falling back to config.toml edit"
            Merge-McpConfigToml -Path $configPath -ServerName $ServerName -Command $python -Args @($server) -Env @{ SINAPSE_HOME = $Root }
        } else { Write-Host "registered sinapse-memory via 'codex mcp add' -> $configPath" }
    } else {
        Merge-McpConfigToml -Path $configPath -ServerName $ServerName -Command $python -Args @($server) -Env @{ SINAPSE_HOME = $Root }
    }
    Merge-McpConfig -Path $jsonPath -ServerName $ServerName -Entry (Get-StdioEntry)
}

function Register-GenericJson {
    param(
        [string]$Name,
        [string]$Path,
        [string]$RootKey = "mcpServers",
        [string]$CliName = "",
        [string[]]$CliAddArgs = @()
    )
    $entry = Get-StdioEntry
    $cli = if ($CliName) { Get-Command $CliName -ErrorAction SilentlyContinue } else { $null }

    if ($Check) {
        if ($cli) {
            $ok = (& $cli.Source mcp get sinapse-memory *> $null); $LASTEXITCODE -eq 0
            Write-Status $Path $ok "(via '$CliName mcp get')"
        } else {
            Write-Status $Path (Test-McpJsonRegistered -Path $Path -ServerName $ServerName -RootKey $RootKey)
        }
        return
    }

    if ($cli) {
        & $cli.Source mcp remove sinapse-memory *> $null
        $addArgs = @("mcp", "add", "sinapse-memory") + $CliAddArgs + @("--", $python, $server)
        & $cli.Source @addArgs
    } else {
        Merge-McpConfig -Path $Path -ServerName $ServerName -Entry $entry -RootKey $RootKey
    }
}

function Register-Gemini   { Register-GenericJson -Name "Gemini CLI"  -Path (Join-Path $env:USERPROFILE ".gemini\settings.json") -CliName "gemini"  -CliAddArgs @("-e","PYTHONPATH=$Root") }
function Register-Qwen     { Register-GenericJson -Name "Qwen Code"   -Path (Join-Path $env:USERPROFILE ".qwen\settings.json")   -CliName "qwen"    -CliAddArgs @("-e","PYTHONPATH=$Root") }
function Register-Kimi     { Register-GenericJson -Name "Kimi Code"   -Path (Join-Path $env:USERPROFILE ".kimi\mcp.json")        -CliName "kimi"    -CliAddArgs @("-e","PYTHONPATH=$Root") }
function Register-Kiro     { Register-GenericJson -Name "Kiro"        -Path (Join-Path $env:USERPROFILE ".kiro\settings\mcp.json") -CliName "kiro"   -CliAddArgs @("-e","PYTHONPATH=$Root") }
function Register-Opencode { Register-GenericJson -Name "OpenCode"    -Path (Join-Path $env:USERPROFILE ".opencode\mcp.json")    -CliName "opencode" -CliAddArgs @("-e","PYTHONPATH=$Root") }
function Register-Openclaw { Register-GenericJson -Name "OpenClaw"    -Path (Join-Path $env:USERPROFILE ".openclaw\openclaw.json") -CliName "openclaw" -CliAddArgs @("-e","PYTHONPATH=$Root") }

function Register-Kilo {
    $path = Join-Path $env:APPDATA "Code\User\globalStorage\kilocode.kilo-code\settings\mcp_settings.json"
    Register-GenericJson -Name "Kilo Code" -Path $path
}
function Register-Roo {
    $path = Join-Path $env:APPDATA "Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json"
    Register-GenericJson -Name "Roo Code" -Path $path
}
function Register-VSCode {
    $path = Join-Path $Root ".vscode\mcp.json"
    $entry = Get-StdioEntry
    $entry["type"] = "stdio"
    if ($Check) {
        Write-Status $path (Test-McpJsonRegistered -Path $path -ServerName $ServerName -RootKey "servers")
        return
    }
    Merge-McpConfig -Path $path -ServerName $ServerName -Entry $entry -RootKey "servers"
}
function Register-Cursor {
    $path = Join-Path $env:USERPROFILE ".cursor\mcp.json"
    Register-GenericJson -Name "Cursor" -Path $path
}

function Register-Swarmclaw {
    $db = Join-Path $env:USERPROFILE ".swarmclaw\data\swarmclaw.db"
    if ($Check) {
        if (Test-Path -LiteralPath $db) { Write-Status $db $true }
        else { Write-Status $db $false "(db not found)" }
        return
    }
    Ensure-HiveMindDirectory -Path (Split-Path -Parent $db)
    $entries = @(@{
        name = "sinapse-memory"
        transport = "stdio"
        command = $python
        args = @($server)
        cwd = $Root
        env = @{ PYTHONPATH = $Root; SINAPSE_HOME = $Root }
    })
    $entriesJson = $entries | ConvertTo-Json -Depth 10 -Compress
    $dbPath = $db
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $py = @"
import json, sqlite3, time, uuid, os
db = r'$dbPath'
entries = json.loads('''$entriesJson''')
conn = sqlite3.connect(db)
rows = conn.execute('SELECT id, data FROM mcp_servers').fetchall()
existing = {}
for row_id, row_data in rows:
    try: existing[json.loads(row_data).get('name')] = row_id
    except: pass
now = int(time.time() * 1000)
for e in entries:
    name = e['name']
    sid = existing.get(name, uuid.uuid4().hex[:16])
    data = dict(e, id=sid, createdAt=now, updatedAt=now)
    conn.execute('INSERT OR REPLACE INTO mcp_servers (id, data) VALUES (?, ?)', (sid, json.dumps(data)))
for legacy in ('claude-mem-local', 'neural-memory-local'):
    lid = existing.get(legacy)
    if lid: conn.execute('DELETE FROM mcp_servers WHERE id = ?', (lid,))
conn.commit()
conn.close()
"@
    & $python -c $py
    Write-Host "registered sinapse-memory in $db"
}

# --- prompt injection (matches the .sh contract) ----------------------------------

function Get-PromptTarget {
    param([string]$Key)
    switch ($Key) {
        "claude"   { Join-Path $Root "CLAUDE.md" }
        "gemini"   { Join-Path $Root "GEMINI.md" }
        "vscode"   { Join-Path $Root ".github\copilot-instructions.md" }
        "cursor"   { Join-Path $Root ".cursor\rules\hive-mind.md" }
        { $_ -in @("codex","qwen","kimi","kiro","kilo","roo","opencode","openclaw") } { Join-Path $Root "AGENTS.md" }
        default { "" }
    }
}

function Inject-Instructions {
    param([string]$Target)
    if (-not (Test-Path -LiteralPath $PromptSrc)) {
        Write-Host '    prompt fonte ausente: ' $PromptSrc
        return
    }
    Ensure-HiveMindDirectory -Path (Split-Path -Parent $Target)
    $src = (Get-Content -Raw -LiteralPath $PromptSrc).TrimEnd("`r","`n")
    $begin = '<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->'
    $end   = '<!-- END HIVE-MIND SINAPSE -->'
    $block = $begin + "`n" + $src + "`n" + $end + "`n"
    $existing = if (Test-Path -LiteralPath $Target) { Get-Content -Raw -LiteralPath $Target } else { '' }
    $pattern = [regex]::Escape($begin) + '.*?' + [regex]::Escape($end) + '`r?`n?'
    if ([regex]::IsMatch($existing, $pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)) {
        $new = [regex]::Replace($existing, $pattern, $block, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    } else {
        $prefix = $existing.TrimEnd("`r","`n")
        if ($prefix) { $new = $prefix + "`n`n" + $block } else { $new = $block }
    }
    Set-Content -LiteralPath $Target -Value $new -Encoding UTF8
    Write-Host ('    prompt injetado em ' + $Target.Substring($Root.Length + 1))
}


# --- capture hooks (unchanged behavior) -------------------------------------------

$installCaptureHooks = {
    $installer = Join-Path $Root "scripts\setup\install-capture-hooks.py"
    if ((Test-Path -LiteralPath $installer) -and (Test-Path -LiteralPath $python)) {
        $mode = if ($Check) { "--check" } else { "--install" }
        try {
            & $python $installer $mode
            if ($LASTEXITCODE -ne 0) { Write-Warning "install-capture-hooks.py $mode exited with $LASTEXITCODE" }
        } catch { Write-Warning "capture hook installation failed: $_" }
    }
}

# --- main dispatch ----------------------------------------------------------------

$AGENTS_FOUND = 0
$RunAgent = {
    param([string]$Key)
    $fn = "Register-$($Key.Substring(0,1).ToUpper() + $Key.Substring(1))"
    if (Get-Command $fn -ErrorAction SilentlyContinue) { & $fn } else { Write-Warning "no registrar for $Key" }
    $script:AGENTS_FOUND++
    if (-not $Check -and $InjectPrompt) {
        $tgt = Get-PromptTarget $Key
        if ($tgt) { Inject-Instructions $tgt }
    }
}

Write-Host "Hive-Mind - registro MCP (PROJECT_ROOT: $Root)"
Write-Host ""

if ($Only) {
    Write-Host "Modo single-agent: $Only"
    & $RunAgent $Only
    & $installCaptureHooks
    Write-Host ""
    if ($Check) { Write-Host "Verification completed for: $Only" }
    else {
        Write-Host "Registered: $Only. Restart that agent to load the MCPs."
        Write-Host "Test: ask it `"use the sinapse_health tool`"."
    }
    exit 0
}

if (-not $ClaudeOnly) {
    if (Get-Command claude -ErrorAction SilentlyContinue) { & $RunAgent "claude" }
    if (Get-Command codex  -ErrorAction SilentlyContinue) { & $RunAgent "codex"  }
    if (Get-Command gemini -ErrorAction SilentlyContinue) { & $RunAgent "gemini" }
    if ((Get-Command qwen   -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:USERPROFILE ".qwen")))   { & $RunAgent "qwen"   }
    if ((Get-Command kimi   -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:USERPROFILE ".kimi")))   { & $RunAgent "kimi"   }
    if ((Get-Command kiro   -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:USERPROFILE ".kiro")))   { & $RunAgent "kiro"   }
    $kiloPath = Join-Path $env:APPDATA "Code\User\globalStorage\kilocode.kilo-code"
    if ((Test-Path $kiloPath) -or (Test-Path (Join-Path $env:USERPROFILE ".kilocode"))) { & $RunAgent "kilo" }
    $rooPath = Join-Path $env:APPDATA "Code\User\globalStorage\rooveterinaryinc.roo-cline"
    if (Test-Path $rooPath) { & $RunAgent "roo" }
    if ((Get-Command code -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:APPDATA "Code\User\globalStorage\github.copilot-chat"))) { & $RunAgent "vscode" }
    if (Test-Path (Join-Path $env:USERPROFILE ".cursor")) { & $RunAgent "cursor" }
    if (Get-Command opencode -ErrorAction SilentlyContinue) { & $RunAgent "opencode" }
    if (Get-Command openclaw -ErrorAction SilentlyContinue) { & $RunAgent "openclaw" }
    if ((Get-Command swarmclaw -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:USERPROFILE ".swarmclaw"))) { & $RunAgent "swarmclaw" }
}
if (-not $CodexOnly) {
    if (Get-Command claude -ErrorAction SilentlyContinue) { & $RunAgent "claude" }
}

& $installCaptureHooks
Write-Host ""
if ($AGENTS_FOUND -eq 0) {
    Write-Host "0 agent(s) detected."
    if ($Check) { exit 0 } else { exit 1 }
}
if ($Check) { Write-Host "$AGENTS_FOUND agent(s) detected." }
else {
    Write-Host "$AGENTS_FOUND agent(s) registered."
    Write-Host "Test: ask it `"use the sinapse_health tool`"."
}
