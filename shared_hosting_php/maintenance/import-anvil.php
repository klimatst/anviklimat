<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit("Not found\n");
}

$root = dirname(__DIR__);
$configFile = $root . '/app/config.php';
$importDirectory = $root . '/storage/imports';
if (!is_file($configFile)) {
    fwrite(STDERR, "Сначала установите сайт и создайте app/config.php.\n");
    exit(2);
}
$config = require $configFile;
if (!is_array($config) || !isset($config['db_host'], $config['db_port'], $config['db_name'], $config['db_user'], $config['db_password'])) {
    fwrite(STDERR, "Конфигурация базы данных неполная; импорт остановлен.\n");
    exit(2);
}
if (!is_dir($importDirectory) && !mkdir($importDirectory, 0750, true) && !is_dir($importDirectory)) {
    fwrite(STDERR, "Не удалось создать storage/imports.\n");
    exit(2);
}

$inputPath = $argv[1] ?? ($importDirectory . DIRECTORY_SEPARATOR . 'anvil-export.json.gz');
$realImportDirectory = realpath($importDirectory);
$realInputPath = realpath($inputPath);
if ($realImportDirectory === false || $realInputPath === false
    || !str_starts_with($realInputPath, $realImportDirectory . DIRECTORY_SEPARATOR)
    || !is_file($realInputPath)
) {
    fwrite(STDERR, "Положите переносимый файл в storage/imports/anvil-export.json.gz.\n");
    exit(2);
}

require_once $root . '/app/anvil_import.php';
try {
    $dsn = 'mysql:host=' . $config['db_host'] . ';port=' . $config['db_port'] . ';dbname=' . $config['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $result = import_anvil_export($pdo, $realInputPath);
    printf("Перенос Anvil завершён. Таблиц: %d; строк: %d.\n", $result['tables'], $result['rows']);
    printf("Контрольная сумма SHA-256: %s\n", $result['checksum']);
    echo "Исходные записи сохранены в зеркальных таблицах anvil_export_rows без потери структуры.\n";
    echo "Пароли пользователей и ключи API не импортируются.\n";
} catch (Throwable $error) {
    fwrite(STDERR, "Импорт не завершён: " . $error->getMessage() . "\n");
    exit(1);
}
