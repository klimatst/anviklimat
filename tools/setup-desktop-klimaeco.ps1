$ErrorActionPreference = 'Stop'
$repoUrl = 'https://github.com/klimatst/anviklimat.git'
$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) { throw 'Could not determine the Windows Desktop folder.' }
$target = Join-Path $desktop 'KlimaEco'
if (Test-Path $target) {
  if (-not (Test-Path (Join-Path $target '.git'))) { throw "Target folder exists but is not a Git repository: $target. Nothing was overwritten." }
  Push-Location $target
  try {
    $origin = (& git remote get-url origin).Trim()
    if ($origin -notmatch 'github\.com[:/]klimatst/anviklimat(?:\.git)?$') { throw "Unexpected origin in target folder: $origin. Nothing was overwritten." }
    $dirty = @(& git status --porcelain)
    if ($dirty.Count -gt 0) { throw "Uncommitted changes exist in $target. Save them before setup." }
    & git fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'Could not connect to GitHub. Check network and Git Credential Manager.' }
    & git ls-remote --exit-code --heads origin desktop-sync *> $null
    if ($LASTEXITCODE -eq 0) {
      & git switch desktop-sync
      if ($LASTEXITCODE -ne 0) { throw 'Could not switch to desktop-sync.' }
      & git pull --no-rebase origin desktop-sync
      if ($LASTEXITCODE -ne 0) { throw 'Updating desktop-sync stopped. Check for merge conflicts.' }
    } else {
      & git switch -c desktop-sync origin/master
      if ($LASTEXITCODE -ne 0) { throw 'Could not create desktop-sync from origin/master.' }
      & git push -u origin desktop-sync
      if ($LASTEXITCODE -ne 0) { throw 'Could not create desktop-sync on GitHub. Check authentication.' }
    }
  } finally { Pop-Location }
} else {
  & git clone --origin origin $repoUrl $target
  if ($LASTEXITCODE -ne 0) { throw 'Clone failed. Check GitHub connectivity, VPN/proxy, and Git access.' }
  Push-Location $target
  try {
    & git switch -c desktop-sync origin/master
    if ($LASTEXITCODE -ne 0) { throw 'Could not create desktop-sync branch.' }
    & git push -u origin desktop-sync
    if ($LASTEXITCODE -ne 0) { throw 'Could not publish desktop-sync. Configure Git Credential Manager and retry.' }
  } finally { Pop-Location }
}
Write-Host ''
Write-Host "Ready: $target" -ForegroundColor Green
Write-Host 'Local changes will be committed and pushed to the GitHub branch desktop-sync.'
Write-Host 'Changes are NOT pushed directly to master automatically.'
Start-Process explorer.exe $target
Start-Process powershell.exe -ArgumentList @('-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $target 'tools\desktop-sync-watch.ps1'))

# Open both local site modes after clone/setup. PHP/XAMPP engine uses 4173; lightweight preview uses 4174.
$phpLauncher = Join-Path $target 'shared_hosting_php\START-LOCAL.cmd'
$previewLauncher = Join-Path $target 'local-site\START-LOCAL.cmd'
if (Test-Path $phpLauncher) { Start-Process -FilePath $phpLauncher -WorkingDirectory (Split-Path $phpLauncher) }
if (Test-Path $previewLauncher) { Start-Process -FilePath $previewLauncher -WorkingDirectory (Split-Path $previewLauncher) }
