[CmdletBinding()]
param(
    [ValidateSet("Status", "Pull", "Push", "Watch")]
    [string]$Mode = "Status",
    [int]$IntervalSeconds = 10
)
$ErrorActionPreference = "Stop"
$ExpectedOrigin = "github.com[:/]klimatst/anviklimat(?:\.git)?$"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Git {
    param([string[]]$GitArgs, [switch]$AllowFailure)
    $output = & git -C $RepoRoot @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
        throw "git $($GitArgs -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return ,$output
}
function Get-Branch { return ((Invoke-Git @("branch", "--show-current")) -join "").Trim() }
function Assert-Repository {
    if (-not (Test-Path (Join-Path $RepoRoot "anvil.yaml"))) {
        throw "Не найден anvil.yaml в $RepoRoot. Скрипт должен лежать в tools внутри клона репозитория."
    }
    $origin = ((Invoke-Git @("config", "--get", "remote.origin.url")) -join "").Trim()
    if ($origin -notmatch $ExpectedOrigin) {
        throw "origin не соответствует klimatst/anviklimat. Синхронизация остановлена; URL скрыт из соображений безопасности."
    }
}
function Test-CleanTree { return (@(Invoke-Git @("status", "--porcelain")).Count -eq 0) }

function Sync-OneCycle {
    Assert-Repository
    $branch = Get-Branch
    if ([string]::IsNullOrWhiteSpace($branch)) { throw "HEAD detached: переключитесь на локальную ветку." }
    if (-not (Test-CleanTree)) {
        Write-Host "[PAUSE] Есть незакоммиченные изменения. Ничего не перезаписываю." -ForegroundColor Yellow
        return
    }
    Invoke-Git @("fetch", "--prune", "origin") | Out-Null
    $remoteRef = "origin/$branch"
    & git -C $RepoRoot show-ref --verify --quiet "refs/remotes/origin/$branch"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[INFO] Ветка $remoteRef отсутствует на GitHub; первая публикация только вручную через Mode Push." -ForegroundColor Yellow
        return
    }
    $counts = ((Invoke-Git @("rev-list", "--left-right", "--count", "HEAD...$remoteRef")) -join "").Trim().Split()
    if ($counts.Count -lt 2) { throw "Не удалось определить расхождение HEAD и $remoteRef." }
    $ahead = [int]$counts[0]; $behind = [int]$counts[1]
    if ($ahead -gt 0 -and $behind -gt 0) {
        Write-Host "[CONFLICT] Ветки разошлись. Нужен ручной разбор; автоматическое слияние запрещено." -ForegroundColor Red
        return
    }
    if ($behind -gt 0) {
        Invoke-Git @("merge", "--ff-only", $remoteRef) | Out-Null
        Write-Host "[PULL] $branch обновлена fast-forward из GitHub." -ForegroundColor Green
        $ahead = 0
    }
    if ($ahead -gt 0) {
        if ($branch -in @("master", "main")) {
            Write-Host "[SAFE] Автопубликация коммитов из $branch запрещена. Перенесите работу в отдельную ветку." -ForegroundColor Yellow
            return
        }
        Invoke-Git @("push", "origin", "HEAD:$branch") | Out-Null
        Write-Host "[PUSH] Отправлены коммиты в origin/$branch." -ForegroundColor Green
    }
    if ($ahead -eq 0 -and $behind -eq 0) { Write-Host "[OK] $branch синхронизирована с GitHub." -ForegroundColor Green }
}

try {
    Assert-Repository
    switch ($Mode) {
        "Status" {
            $branch = Get-Branch
            $changes = @(Invoke-Git @("status", "--porcelain"))
            Write-Host "KlimaEco Git sync"
            Write-Host "Repository: $RepoRoot"
            Write-Host "Branch: $branch"
            Write-Host "Origin: verified as klimatst/anviklimat (URL hidden)"
            Write-Host "Working tree: $(if ($changes.Count -eq 0) { 'clean' } else { "$($changes.Count) changed path(s); sync paused until saved" })"
            Write-Host "Policy: fast-forward pull only; push from non-main/master branches; never force-push."
        }
        "Pull" {
            $branch = Get-Branch
            if (-not (Test-CleanTree)) { throw "Есть незакоммиченные изменения. Pull отменён." }
            Invoke-Git @("fetch", "origin") | Out-Null
            Invoke-Git @("merge", "--ff-only", "origin/$branch")
        }
        "Push" {
            $branch = Get-Branch
            if ($branch -in @("master", "main")) { throw "Прямая отправка в $branch запрещена. Используйте рабочую ветку и PR." }
            if (-not (Test-CleanTree)) { throw "Есть незакоммиченные изменения. Сначала выполните git add и git commit." }
            Invoke-Git @("fetch", "origin") | Out-Null
            Invoke-Git @("push", "-u", "origin", "HEAD:$branch")
        }
        "Watch" {
            if ($IntervalSeconds -lt 5) { throw "IntervalSeconds должен быть не меньше 5 секунд." }
            Write-Host "Автосинхронизация запущена; Ctrl+C для остановки. Незакоммиченные изменения не трогаются."
            while ($true) {
                try { Sync-OneCycle } catch { Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red }
                Start-Sleep -Seconds $IntervalSeconds
            }
        }
    }
} catch {
    Write-Error $_
    exit 1
}
