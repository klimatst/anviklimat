$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $RepoRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python не найден. Установите Python 3.11+ и включите Add Python to PATH."
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
  Write-Warning "Java не найдена в PATH. Установите Amazon Corretto 8+ и перезапустите PowerShell."
  throw "Для Anvil App Server требуется Java."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install anvil-app-server -r requirements.txt

New-Item -ItemType Directory -Force -Path ".anvil-data" | Out-Null
Write-Host "Starting KlimaEco at http://localhost:3030"
Write-Host "Persistent app data: $RepoRoot\.anvil-data"
& (Join-Path $RepoRoot ".venv\Scripts\anvil-app-server.exe") --app $RepoRoot --data-dir (Join-Path $RepoRoot ".anvil-data")
