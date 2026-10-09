$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

function Fail([string]$Message) {
  Write-Host "[STOP] $Message" -ForegroundColor Red
  exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'Git не найден в PATH.' }
if (-not (Test-Path (Join-Path $repoRoot '.git'))) { Fail "Папка не является корнем Git-репозитория: $repoRoot" }
$origin = (& git remote get-url origin 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or $origin -notmatch 'github\.com[:/]klimatst/anviklimat(?:\.git)?$') { Fail 'origin не указывает на klimatst/anviklimat. Ничего не изменено.' }
$branch = (& git branch --show-current).Trim()
if ($branch -ne 'master') { Fail "Активна ветка '$branch', а не master. Автопереключение запрещено." }
$dirty = @(& git status --porcelain)
if ($dirty.Count -gt 0) {
  Write-Host '[STOP] Есть локальные изменения. Они не будут перезаписаны.' -ForegroundColor Yellow
  & git status --short
  Write-Host 'Сначала сохраните изменения коммитом/резервной копией или разберите вручную.'
  exit 2
}
Write-Host '[1/4] Проверяю связь с GitHub…' -ForegroundColor Cyan
& git fetch --prune origin master
if ($LASTEXITCODE -ne 0) { Fail 'git fetch не выполнен. Проверьте сеть, VPN/proxy и доступ GitHub.' }
$localSha = (& git rev-parse HEAD).Trim()
$remoteSha = (& git rev-parse origin/master).Trim()
if ($localSha -eq $remoteSha) { Write-Host "[OK] Уже актуально: $($localSha.Substring(0,12))" -ForegroundColor Green; exit 0 }
& git merge-base --is-ancestor HEAD origin/master
if ($LASTEXITCODE -ne 0) { Fail 'Локальная история разошлась с origin/master. Автоматическое слияние запрещено.' }
Write-Host '[2/4] Обновляю локальный master через fast-forward…' -ForegroundColor Cyan
& git merge --ff-only origin/master
if ($LASTEXITCODE -ne 0) { Fail 'Fast-forward не прошёл. Нужна ручная проверка.' }
Write-Host '[3/4] Проверяю рабочее дерево…' -ForegroundColor Cyan
& git status --short
$newSha = (& git rev-parse HEAD).Trim()
Write-Host "[4/4] Готово. XAMPP checkout обновлён до $($newSha.Substring(0,12))." -ForegroundColor Green
Write-Host 'Локальные изменения не отправляются автоматически в GitHub: проверьте diff, затем commit и push выбранных файлов.'
