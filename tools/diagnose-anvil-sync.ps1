$ErrorActionPreference = "Continue"

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail) {
    $status = if ($Ok) { "PASS" } else { "CHECK" }
    $color = if ($Ok) { "Green" } else { "Yellow" }
    Write-Host ("[{0}] {1}: {2}" -f $status, $Name, $Detail) -ForegroundColor $color
}

Write-Host "\`nKlimaEco / Anvil sync diagnostics" -ForegroundColor Cyan
Write-Host "This script only reads local settings and tests network endpoints. It does not change files or print credentials.\`n"

$root = $null
try { $root = (& git rev-parse --show-toplevel 2>$null | Select-Object -First 1).Trim() } catch {}
$gitOk = -not [string]::IsNullOrWhiteSpace($root) -and (Test-Path (Join-Path $root "anvil.yaml"))
Write-Check "Anvil project folder" $gitOk $(if ($gitOk) { $root } else { "Run this from the KlimaEco repository folder (the folder containing anvil.yaml)." })

if ($gitOk) {
    $branch = (& git -C $root branch --show-current 2>$null | Select-Object -First 1)
    $head = (& git -C $root rev-parse HEAD 2>$null | Select-Object -First 1)
    $origin = (& git -C $root config --get remote.origin.url 2>$null | Select-Object -First 1)
    $originOk = $origin -match 'github\.com[:/]klimatst/anviklimat(?:\.git)?$'
    Write-Check "Git origin" $originOk $(if ($originOk) { "points to klimatst/anviklimat" } else { "origin does not match the expected repository (URL hidden for safety)" })
    Write-Host ("[INFO] Local branch: {0}; HEAD: {1}" -f $branch, $head)

    $dirty = @(& git -C $root status --porcelain 2>$null)
    Write-Check "Working tree" ($dirty.Count -eq 0) $(if ($dirty.Count -eq 0) { "clean" } else { "$($dirty.Count) changed/untracked path(s); review before switching branches" })

    $remoteLine = & git -C $root ls-remote origin refs/heads/master 2>$null
    if ($LASTEXITCODE -eq 0 -and $remoteLine) {
        $remoteSha = (($remoteLine -split '\s+')[0]).Trim()
        $localMaster = (& git -C $root rev-parse refs/remotes/origin/master 2>$null | Select-Object -First 1)
        Write-Check "GitHub reachability" $true ("origin/master currently at " + $remoteSha.Substring(0, [Math]::Min(12, $remoteSha.Length)))
        if ($localMaster) {
            Write-Check "Local remote-tracking ref" ($localMaster -eq $remoteSha) ("origin/master " + $(if ($localMaster -eq $remoteSha) { "matches GitHub" } else { "is stale; run git fetch origin" }))
        } else {
            Write-Check "Local remote-tracking ref" $false "origin/master is not present locally; run git fetch origin"
        }
    } else {
        Write-Check "GitHub reachability via Git" $false "git ls-remote failed; check proxy/VPN, DNS, TLS, and Git credentials"
    }
} else {
    Write-Host "[INFO] Git checks skipped because the current folder is not a recognizable Anvil Git checkout."
}

$anvil = Get-Command anvil -ErrorAction SilentlyContinue
Write-Check "Anvil CLI installed" ($null -ne $anvil) $(if ($anvil) { "command found" } else { "anvil command not found in PATH" })
if ($anvil) {
    $version = (& anvil --version 2>&1 | Select-Object -First 1)
    Write-Host ("[INFO] Anvil CLI version: {0}" -f $version)
}

$watch = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^(anvil|node)(\.exe)?$' -and $_.CommandLine -match 'anvil(\.cmd)?\s+watch|anvil-cli.*watch'
})
Write-Check "Anvil watch process" ($watch.Count -gt 0) $(if ($watch.Count -gt 0) { "watch-like process detected" } else { "no anvil watch process detected; local edits will not live-sync unless another sync path is active" })

foreach ($uri in @("https://anvil.works", "https://api.github.com")) {
    try {
        $response = Invoke-WebRequest -Uri $uri -Method Head -TimeoutSec 12 -UseBasicParsing
        Write-Check ("HTTPS " + $uri) ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) ("HTTP " + $response.StatusCode)
    } catch {
        Write-Check ("HTTPS " + $uri) $false $_.Exception.Message
    }
}

$httpProxy = -not [string]::IsNullOrWhiteSpace($env:HTTP_PROXY)
$httpsProxy = -not [string]::IsNullOrWhiteSpace($env:HTTPS_PROXY)
Write-Check "Proxy environment" ($httpProxy -or $httpsProxy) $(if ($httpProxy -or $httpsProxy) { "HTTP_PROXY/HTTPS_PROXY configured (values intentionally hidden)" } else { "no HTTP(S)_PROXY environment variable; this is fine if direct access works" })

Write-Host "\`nInterpretation:" -ForegroundColor Cyan
Write-Host "- For instant local-to-Anvil sync, run 'anvil watch' in this exact app folder and keep it running."
Write-Host "- This diagnostic does not print proxy URLs, Git credentials, Anvil tokens, or secret values."
Write-Host "- If GitHub master is newer than the local checkout, fetch/pull the intended branch before starting watch."
