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
        throw "anvil.yaml was not found. Run this updater from the klimatst/anviklimat clone folder."
    }
    $origin = ((Invoke-Git @('remote','get-url','origin')) -join '').Trim()
    if ($origin -notmatch 'github\.com[:/]klimatst/anviklimat(?:\.git)?$') {
        throw 'origin does not point to klimatst/anviklimat. Update cancelled.'
    }

    $branch = ((Invoke-Git @('branch','--show-current')) -join '').Trim()
    if ($branch -notin @('master','desktop-sync')) {
        throw "Current branch '$branch' is not supported. Only master and desktop-sync are allowed."
    }

    $dirty = @(Invoke-Git @('status','--porcelain'))
    if ($dirty.Count -gt 0) {
        Write-Host '[STOP] Uncommitted local changes were found. They have been preserved; automatic update cancelled.' -ForegroundColor Yellow
        Write-Host 'Changed files:'
        $dirty | ForEach-Object { Write-Host "  $_" }
        throw 'Save or review local changes first. No files were deleted.'
    }

    Write-Host '[1/4] Fetching GitHub branch information...' -ForegroundColor Cyan
    Invoke-Git @('fetch','--prune','origin') | Out-Null
    $remoteRef = "origin/$branch"
    & git.exe -C $repoRoot show-ref --verify --quiet "refs/remotes/$remoteRef"
    if ($LASTEXITCODE -ne 0) { throw "Remote branch $remoteRef was not found." }

    $counts = (((Invoke-Git @('rev-list','--left-right','--count',"HEAD...$remoteRef")) -join '').Trim() -split '\s+')
    if ($counts.Count -lt 2) { throw 'Could not determine the synchronization state.' }
    $ahead = [int]$counts[0]
    $behind = [int]$counts[1]
    if ($ahead -gt 0 -and $behind -gt 0) {
        throw "Local branch and $remoteRef have diverged. Update cancelled to avoid conflicts."
    }
    if ($behind -gt 0) {
        Write-Host "[2/4] Fast-forwarding $branch ($behind new commit(s))..." -ForegroundColor Cyan
        Invoke-Git @('merge','--ff-only',$remoteRef) | Out-Null
    } elseif ($ahead -gt 0) {
        Write-Host "[INFO] Local branch has $ahead commit(s) not on GitHub. They will not be pushed automatically." -ForegroundColor Yellow
    } else {
        Write-Host '[2/4] Local branch already matches GitHub.' -ForegroundColor Green
    }

    $sha = ((Invoke-Git @('rev-parse','--short','HEAD')) -join '').Trim()
    Write-Host '[3/4] Checking working tree...' -ForegroundColor Cyan
    Invoke-Git @('status','--short')
    Write-Host "[4/4] Done. Branch: $branch; commit: $sha" -ForegroundColor Green
    Write-Host 'Open http://127.0.0.1:4173/ and press Ctrl+F5.'
    Write-Host 'If the page still looks old, the PHP server may be running from a different folder.'
    exit 0
} catch {
    Write-Host ("[ERROR] " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
