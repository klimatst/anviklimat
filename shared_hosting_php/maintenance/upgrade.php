<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit("Not found\n");
}
$root = dirname(__DIR__);
$configFile = $root . '/app/config.php';
if (!is_file($configFile)) {
    fwrite(STDERR, "Не найдена app/config.php. Сначала установите сайт.\n");
    exit(2);
}
$config = require $configFile;
if (!is_array($config) || !isset($config['db_host'], $config['db_port'], $config['db_name'], $config['db_user'], $config['db_password'])) {
    fwrite(STDERR, "Конфигурация БД неполная; обновление не выполнено.\n");
    exit(2);
}
require_once $root . '/app/engineering_schema.php';
try {
    $dsn = 'mysql:host=' . $config['db_host'] . ';port=' . $config['db_port'] . ';dbname=' . $config['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    ensure_engineering_schema($pdo);
    echo "Engineering OS schema is ready. Existing data was not deleted or modified.\n";
} catch (Throwable $error) {
    fwrite(STDERR, "Обновление схемы не выполнено: " . $error->getMessage() . "\n");
    exit(1);
}
