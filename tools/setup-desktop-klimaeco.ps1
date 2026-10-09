$ErrorActionPreference = 'Stop'
$repoUrl = 'https://github.com/klimatst/anviklimat.git'
$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) { throw 'Не удалось определить папку рабочего стола Windows.' }
$target = Join-Path $desktop 'KlimaEco'
if (Test-Path $target) {
  if (-not (Test-Path (Join-Path $target '.git'))) { throw "Папка существует, но это не Git-репозиторий: $target. Ничего не перезаписано." }
  Push-Location $target
  try {
    $origin = (& git remote get-url origin).Trim()
    if ($origin -notmatch 'github\.com[:/]klimatst/anviklimat(?:\.git)?$') { throw "В папке другой origin: $origin. Ничего не перезаписано." }
    $dirty = @(& git status --porcelain)
    if ($dirty.Count -gt 0) { throw "Есть незакоммиченные изменения в $target. Сначала сохраните их." }
    & git fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось связаться с GitHub. Проверьте сеть и Git Credential Manager.' }
    & git ls-remote --exit-code --heads origin desktop-sync *> $null
    if ($LASTEXITCODE -eq 0) {
      & git switch desktop-sync
      if ($LASTEXITCODE -ne 0) { throw 'Не удалось переключиться на desktop-sync.' }
      & git pull --no-rebase origin desktop-sync
      if ($LASTEXITCODE -ne 0) { throw 'Обновление desktop-sync остановлено; проверьте конфликты.' }
    } else {
      & git switch -c desktop-sync origin/master
      if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать ветку desktop-sync от origin/master.' }
      & git push -u origin desktop-sync
      if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать desktop-sync на GitHub. Проверьте авторизацию.' }
    }
  } finally { Pop-Location }
} else {
  & git clone --origin origin $repoUrl $target
  if ($LASTEXITCODE -ne 0) { throw 'Клонирование не удалось. Проверьте GitHub, VPN/proxy и доступ Git.' }
  Push-Location $target
  try {
    & git switch -c desktop-sync origin/master
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать ветку desktop-sync.' }
    & git push -u origin desktop-sync
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось опубликовать desktop-sync. Настройте Git Credential Manager и повторите запуск.' }
  } finally { Pop-Location }
}
Write-Host ''
Write-Host "Готово: $target" -ForegroundColor Green
Write-Host 'Локальные изменения будут фиксироваться и отправляться в GitHub в ветку desktop-sync.'
Write-Host 'Изменения НЕ отправляются автоматически прямо в master.'
Start-Process explorer.exe $target
Start-Process powershell.exe -ArgumentList @('-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $target 'tools\desktop-sync-watch.ps1'))

# Open both local site modes after clone/setup. PHP/XAMPP engine uses 4173; lightweight preview uses 4174.
$phpLauncher = Join-Path $target 'shared_hosting_php\START-LOCAL.cmd'
$previewLauncher = Join-Path $target 'local-site\START-LOCAL.cmd'
if (Test-Path $phpLauncher) { Start-Process -FilePath $phpLauncher -WorkingDirectory (Split-Path $phpLauncher) }
if (Test-Path $previewLauncher) { Start-Process -FilePath $previewLauncher -WorkingDirectory (Split-Path $previewLauncher) }
