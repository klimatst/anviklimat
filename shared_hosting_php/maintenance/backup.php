<?php
declare(strict_types=1);

/**
 * Create a read-only SQL snapshot of the installed local PHP engine.
 * Run only from CLI: php maintenance/backup.php
 */
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
    fwrite(STDERR, "Конфигурация БД неполная; резервная копия не создана.\n");
    exit(2);
}

$backupDir = $root . '/storage/backups';
if (!is_dir($backupDir) && !mkdir($backupDir, 0750, true) && !is_dir($backupDir)) {
    fwrite(STDERR, "Не удалось создать storage/backups.\n");
    exit(3);
}
$stamp = date('Ymd-His');
$target = $backupDir . '/klimaeco-db-' . $stamp . '.sql';
$temp = $target . '.tmp';
$handle = null;

try {
    $dsn = 'mysql:host=' . $config['db_host'] . ';port=' . $config['db_port'] . ';dbname=' . $config['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $handle = fopen($temp, 'xb');
    if ($handle === false) {
        throw new RuntimeException('Не удалось создать временный файл резервной копии.');
    }

    $write = static function (string $line) use ($handle): void {
        if (fwrite($handle, $line) === false) {
            throw new RuntimeException('Ошибка записи резервной копии.');
        }
    };
    $write("-- KlimaEco database snapshot\n");
    $write("-- Created: " . date(DATE_ATOM) . "\n");
    $write("-- Database: " . preg_replace('/[^A-Za-z0-9_.-]/', '_', (string)$config['db_name']) . "\n\n");
    $write("SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\n\n");

    $tables = $pdo->query('SHOW FULL TABLES WHERE Table_type = "BASE TABLE"')->fetchAll(PDO::FETCH_NUM);
    foreach ($tables as $tableRow) {
        $table = (string)$tableRow[0];
        if (!preg_match('/^[A-Za-z0-9_$]+$/', $table)) {
            throw new RuntimeException('Имя таблицы содержит неподдерживаемые символы.');
        }
        $quotedTable = chr(96) . $table . chr(96);
        $createRow = $pdo->query('SHOW CREATE TABLE ' . $quotedTable)->fetch(PDO::FETCH_NUM);
        if (!$createRow || !isset($createRow[1])) {
            throw new RuntimeException('Не удалось получить схему таблицы ' . $table);
        }
        $write("-- Table " . $table . "\n");
        $write("DROP TABLE IF EXISTS " . $quotedTable . ";\n");
        $write((string)$createRow[1] . ";\n");

        $columnRows = $pdo->query('SHOW COLUMNS FROM ' . $quotedTable)->fetchAll();
        $columns = array_map(static fn(array $col): string => chr(96) . str_replace(chr(96), chr(96) . chr(96), (string)$col['Field']) . chr(96), $columnRows);
        if (!$columns) {
            $write("\n");
            continue;
        }
        $select = $pdo->query('SELECT * FROM ' . $quotedTable);
        $insertPrefix = 'INSERT INTO ' . $quotedTable . ' (' . implode(',', $columns) . ') VALUES ';
        while ($row = $select->fetch(PDO::FETCH_NUM)) {
            $values = [];
            foreach ($row as $value) {
                if ($value === null) {
                    $values[] = 'NULL';
                } else {
                    $quoted = $pdo->quote((string)$value);
                    if ($quoted === false) {
                        throw new RuntimeException('Не удалось экранировать значение таблицы ' . $table);
                    }
                    $values[] = $quoted;
                }
            }
            $write($insertPrefix . '(' . implode(',', $values) . ");\n");
        }
        $write("\n");
    }
    $write("SET FOREIGN_KEY_CHECKS=1;\n");
    if (!fclose($handle)) {
        $handle = null;
        throw new RuntimeException('Не удалось закрыть файл резервной копии.');
    }
    $handle = null;
    if (!rename($temp, $target)) {
        throw new RuntimeException('Не удалось завершить запись резервной копии.');
    }
    @chmod($target, 0600);
    printf("Резервная копия БД создана: %s\nРазмер: %s байт\n", $target, (string)filesize($target));
    printf("Таблиц: %d\n", count($tables));
} catch (Throwable $error) {
    if (is_resource($handle)) {
        fclose($handle);
    }
    if (is_file($temp)) {
        @unlink($temp);
    }
    fwrite(STDERR, "Резервная копия не создана: " . $error->getMessage() . "\n");
    exit(1);
}
