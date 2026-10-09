$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot
$branch = 'desktop-sync'
$intervalSeconds = 5
$stablePollsRequired = 3
$lastStatus = ''
$stablePolls = 0
$lastCommitAttempt = [DateTime]::MinValue
function Invoke-RepoGit([string[]]$GitArgs) {
  # Use the executable explicitly; PowerShell command names are case-insensitive.
  $gitExe = (Get-Command git.exe -ErrorAction Stop).Source
  $output = & $gitExe @GitArgs 2>&1
  if ($LASTEXITCODE -ne 0) { throw ('git ' + ($GitArgs -join ' ') + ' failed: ' + ($output -join [Environment]::NewLine)) }
  return ($output -join [Environment]::NewLine)
}
function Say([string]$Message, [string]$Color = 'Gray') { Write-Host ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $Message) -ForegroundColor $Color }
if (-not (Test-Path (Join-Path $repoRoot '.git'))) { throw "Not a Git repository: $repoRoot" }
$origin = Invoke-RepoGit @('remote','get-url','origin')
if ($origin -notmatch 'github\.com[:/]klimatst/anviklimat(?:\.git)?$') { throw "Unexpected origin: $origin" }
$currentBranch = (Invoke-RepoGit @('branch','--show-current')).Trim()
if ($currentBranch -ne $branch) { throw "Expected branch $branch but found $currentBranch. Refusing to sync." }
Say "Live sync started in $repoRoot" 'Green'
Say 'Local edits are committed and pushed to GitHub branch desktop-sync. Master is merged only when there are no conflicts.' 'Cyan'
Say 'Press Ctrl+C to stop.' 'DarkGray'
while ($true) {
  try {
    Invoke-RepoGit @('fetch','origin')
    $status = (Invoke-RepoGit @('status','--porcelain')).Trim()
    if ($status -ne $lastStatus) { $lastStatus = $status; $stablePolls = 0 } else { $stablePolls++ }
    if ($status -ne '' -and $stablePolls -ge $stablePollsRequired -and ((Get-Date) - $lastCommitAttempt).TotalSeconds -ge 10) {
      Invoke-RepoGit @('add','-A')
      $staged = (Invoke-RepoGit @('diff','--cached','--name-only')).Trim()
      if ($staged -ne '') {
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Invoke-RepoGit @('commit','-m',"Auto-sync desktop changes $stamp")
        Say 'Local changes committed.' 'Green'
      }
      $lastCommitAttempt = Get-Date; $lastStatus = ''; $stablePolls = 0
    }
    Invoke-RepoGit @('merge','--no-edit','origin/master')
    Invoke-RepoGit @('merge','--no-edit','origin/desktop-sync')
    Invoke-RepoGit @('push','origin','HEAD:desktop-sync')
    Start-Sleep -Seconds $intervalSeconds
  } catch {
    Say $_.Exception.Message 'Red'
    Say 'Sync paused for this cycle. No reset/clean/force-push is used. Resolve conflicts or network/auth issues, then restart this script.' 'Yellow'
    Start-Sleep -Seconds 15
  }
}
