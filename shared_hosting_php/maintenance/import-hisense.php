<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit("Not found\n");
}

$root = dirname(__DIR__);
$configFile = $root . '/app/config.php';
if (!is_file($configFile)) {
    fwrite(STDERR, "Не найдена app/config.php. Сначала завершите установку сайта.\n");
    exit(2);
}
$config = require $configFile;
if (!is_array($config) || !isset($config['db_host'], $config['db_port'], $config['db_name'], $config['db_user'], $config['db_password'])) {
    fwrite(STDERR, "Конфигурация БД неполная; импорт не выполнен.\n");
    exit(2);
}

require_once $root . '/app/hisense_import.php';
try {
    $dsn = 'mysql:host=' . $config['db_host'] . ';port=' . $config['db_port'] . ';dbname=' . $config['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $count = import_hisense_catalog($pdo, $root . '/data/hisense_catalog.json');
    printf("Каталог Hisense обработан: %d моделей.\n", $count);
    echo "Существующие непустые поля администратора сохранены; отсутствующие поля и изображения-заглушки заполнены.\n";
} catch (Throwable $error) {
    fwrite(STDERR, "Импорт не завершён: " . $error->getMessage() . "\n");
    exit(1);
}
