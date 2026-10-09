[CmdletBinding()]
param([string]$RepoRoot)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $RepoRoot = Join-Path ([Environment]::GetFolderPath('Desktop')) 'KlimaEco' }
$repoRoot = (Resolve-Path $RepoRoot).Path
Set-Location $repoRoot

function Invoke-Git([string[]]$GitArgs) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & git.exe -C $repoRoot @GitArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw ("git " + ($GitArgs -join ' ') + " failed (exit $exitCode): " + ($output -join [Environment]::NewLine))
    }
    return ,$output
}

try {
    if (-not (Test-Path (Join-Path $repoRoot 'anvil.yaml'))) {
        throw "Не найден anvil.yaml. Запустите файл из папки клона klimatst/anviklimat."
    }
    $origin = ((Invoke-Git @('remote','get-url','origin')) -join '').Trim()
    if ($origin -notmatch 'github\.com[:/]klimatst/anviklimat(?:\.git)?$') {
        throw 'origin не указывает на klimatst/anviklimat. Обновление остановлено.'
    }

    $branch = ((Invoke-Git @('branch','--show-current')) -join '').Trim()
    if ($branch -notin @('master','desktop-sync')) {
        throw "Текущая ветка '$branch'. Скрипт безопасно обновляет только master или desktop-sync."
    }

    $dirty = @(Invoke-Git @('status','--porcelain'))
    if ($dirty.Count -gt 0) {
        Write-Host '[СТОП] В папке есть незакоммиченные изменения. Они сохранены; автоматическое обновление отменено.' -ForegroundColor Yellow
        Write-Host 'Изменённые файлы:'
        $dirty | ForEach-Object { Write-Host "  $_" }
        throw 'Сначала сохраните или отдельно разберите локальные изменения. Ничего не удалено.'
    }

    Write-Host '[1/4] Проверяю GitHub и загружаю сведения о ветках...' -ForegroundColor Cyan
    Invoke-Git @('fetch','--prune','origin') | Out-Null
    $remoteRef = "origin/$branch"
    $hasRemote = & git.exe -C $repoRoot show-ref --verify --quiet "refs/remotes/$remoteRef"
    if ($LASTEXITCODE -ne 0) { throw "На GitHub не найдена ветка $remoteRef." }

    $counts = (((Invoke-Git @('rev-list','--left-right','--count',"HEAD...$remoteRef")) -join '').Trim() -split '\s+')
    if ($counts.Count -lt 2) { throw 'Не удалось определить состояние синхронизации.' }
    $ahead = [int]$counts[0]
    $behind = [int]$counts[1]
    if ($ahead -gt 0 -and $behind -gt 0) {
        throw "Локальная ветка и $remoteRef разошлись. Автоматическое слияние остановлено, чтобы не создавать конфликт."
    }
    if ($behind -gt 0) {
        Write-Host "[2/4] Безопасно обновляю $branch ($behind новых коммитов)..." -ForegroundColor Cyan
        Invoke-Git @('merge','--ff-only',$remoteRef) | Out-Null
    } elseif ($ahead -gt 0) {
        Write-Host "[ИНФО] Локальная ветка содержит $ahead коммит(ов), которых нет на GitHub. Локальные коммиты не отправляю автоматически." -ForegroundColor Yellow
    } else {
        Write-Host '[2/4] Локальная ветка уже совпадает с GitHub.' -ForegroundColor Green
    }

    $sha = ((Invoke-Git @('rev-parse','--short','HEAD')) -join '').Trim()
    Write-Host '[3/4] Проверяю состояние файлов...' -ForegroundColor Cyan
    Invoke-Git @('status','--short')
    Write-Host "[4/4] Готово. Ветка: $branch; коммит: $sha" -ForegroundColor Green
    Write-Host 'Теперь откройте http://127.0.0.1:4173/ и нажмите Ctrl+F5.'
    Write-Host 'Если страница всё ещё старая, PHP-сервер, вероятно, запущен из другой папки.'
    exit 0
} catch {
    Write-Host ("[ОШИБКА] " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
