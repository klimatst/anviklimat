param(
    [string]$Php = "C:\xampp\php\php.exe"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$failures = [System.Collections.Generic.List[string]]::new()
if (-not (Test-Path -LiteralPath $Php)) {
    Write-Error "PHP не найден: $Php. Укажите путь параметром -Php."
    exit 2
}
$phpFiles = Get-ChildItem -LiteralPath $root -Recurse -File -Filter *.php |
    Where-Object { $_.FullName -notmatch '[\\/]storage[\\/]uploads[\\/]' }
foreach ($file in $phpFiles) {
    $output = & $Php -l $file.FullName 2>&1
    if ($LASTEXITCODE -ne 0) {
        $failures.Add("$($file.FullName): $($output -join ' ')")
        Write-Host "[FAIL] $($file.FullName)" -ForegroundColor Red
        Write-Host ($output -join [Environment]::NewLine)
    } else {
        Write-Host "[OK]   $($file.FullName)" -ForegroundColor Green
    }
}
foreach ($json in @("data\categories.json", "data\demo_catalog.json", "data\formulas.json")) {
    $path = Join-Path $root $json
    if (-not (Test-Path -LiteralPath $path)) {
        $failures.Add("Не найден обязательный JSON: $json")
        continue
    }
    try {
        Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
        Write-Host "[OK]   JSON $json" -ForegroundColor Green
    } catch {
        $failures.Add(("Некорректный JSON {0}: {1}" -f $json, $_.Exception.Message))
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $root "app\config.php"))) {
    Write-Host "[INFO] app\config.php ещё нет — запустите install\ в браузере для первичной установки." -ForegroundColor Yellow
}
if ($failures.Count) {
    Write-Host ([Environment]::NewLine + "Проверка не пройдена: $($failures.Count) ошибка(и).") -ForegroundColor Red
    $failures | ForEach-Object { Write-Host " - $_" }
    exit 1
}
Write-Host ([Environment]::NewLine + "Проверка завершена: PHP-синтаксис и исходные JSON-файлы корректны.") -ForegroundColor Green
