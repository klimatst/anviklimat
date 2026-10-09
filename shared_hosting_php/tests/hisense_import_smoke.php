<?php
declare(strict_types=1);

$root = dirname(__DIR__);
require_once $root . '/app/hisense_import.php';

$host = getenv('MYSQL_HOST') ?: '127.0.0.1';
$name = getenv('MYSQL_DATABASE') ?: 'klimaeco_test';
$user = getenv('MYSQL_USER') ?: 'root';
$password = getenv('MYSQL_PASSWORD') ?: 'testroot';
$dsn = 'mysql:host=' . $host . ';port=3306;dbname=' . $name . ';charset=utf8mb4';
$pdo = new PDO($dsn, $user, $password, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);

$pdo->exec('CREATE TABLE brands (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(190) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci');
$pdo->exec('CREATE TABLE categories (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(140) NOT NULL UNIQUE,
    title VARCHAR(190) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci');
$pdo->exec('CREATE TABLE products (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    model VARCHAR(190) NOT NULL,
    sku VARCHAR(120) NULL DEFAULT NULL UNIQUE,
    brand_id INT UNSIGNED NULL,
    category_id INT UNSIGNED NULL,
    description TEXT NOT NULL,
    price DECIMAL(12,2) NOT NULL DEFAULT 0,
    image_url VARCHAR(500) NOT NULL DEFAULT '',
    specifications LONGTEXT NOT NULL,
    is_demo TINYINT(1) NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci');

$catalogPath = $root . '/data/hisense_catalog.json';
$catalog = json_decode((string)file_get_contents($catalogPath), true, 512, JSON_THROW_ON_ERROR);
$categories = json_decode((string)file_get_contents($root . '/data/categories.json'), true, 512, JSON_THROW_ON_ERROR);
$categoryInsert = $pdo->prepare('INSERT INTO categories (code,title) VALUES (?,?)');
foreach ($categories as $category) {
    $categoryInsert->execute([(string)$category['code'], (string)$category['title']]);
}

$first = $catalog['products'][0];
$legacy = $pdo->prepare(
    "INSERT INTO products (model,sku,brand_id,category_id,description,price,image_url,specifications,is_demo,active,created_at) "
    . "VALUES (?, 'legacy-sku-test', NULL, NULL, '', 0, 'assets/images/conditioners.jpg', '[]', 1, 1, NOW())"
);
$legacy->execute([(string)$first['model']]);

$processed = import_hisense_catalog($pdo, $catalogPath);
$total = (int)$pdo->query('SELECT COUNT(*) FROM products')->fetchColumn();
if ($processed !== 241 || $total !== 241) {
    throw new RuntimeException("Expected 241 processed rows and 241 products; got {$processed} / {$total}");
}
$legacyCheck = $pdo->prepare('SELECT brand_id,category_id,description,price,image_url,specifications,is_demo FROM products WHERE model=?');
$legacyCheck->execute([(string)$first['model']]);
$legacyRow = $legacyCheck->fetch();
if (!$legacyRow || !$legacyRow['brand_id'] || !$legacyRow['category_id'] || (int)$legacyRow['is_demo'] !== 0 || $legacyRow['price'] <= 0) {
    throw new RuntimeException('Existing row was not safely enriched by model match.');
}

$manual = $catalog['products'][1];
$manualUpdate = $pdo->prepare('UPDATE products SET description=?,price=?,image_url=?,specifications=? WHERE sku=?');
$manualUpdate->execute([
    'Manual admin edit',
    12345,
    'storage/uploads/custom.png',
    json_encode([['Manual', 'yes', '']], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
    (string)$manual['sku'],
]);
$oldImage = $catalog['products'][2];
$oldImageUpdate = $pdo->prepare('UPDATE products SET image_url=? WHERE sku=?');
$oldImageUpdate->execute(['https://images.breez.ru/catalog/hisense/old-image.png', (string)$oldImage['sku']]);

$processedAgain = import_hisense_catalog($pdo, $catalogPath);
$totalAgain = (int)$pdo->query('SELECT COUNT(*) FROM products')->fetchColumn();
if ($processedAgain !== 241 || $totalAgain !== 241) {
    throw new RuntimeException("Second import created duplicate rows: {$processedAgain} / {$totalAgain}");
}
$manualCheck = $pdo->prepare('SELECT description,price,image_url,specifications FROM products WHERE sku=?');
$manualCheck->execute([(string)$manual['sku']]);
$manualRow = $manualCheck->fetch();
if (!$manualRow || $manualRow['description'] !== 'Manual admin edit' || (float)$manualRow['price'] !== 12345.0 || $manualRow['image_url'] !== 'storage/uploads/custom.png') {
    throw new RuntimeException('Second import overwrote non-empty administrator fields.');
}
$imageCheck = $pdo->prepare('SELECT image_url FROM products WHERE sku=?');
$imageCheck->execute([(string)$oldImage['sku']]);
$imageRow = $imageCheck->fetch();
if (!$imageRow || $imageRow['image_url'] !== (string)$oldImage['image_url']) {
    throw new RuntimeException('Legacy Hisense CDN image was not migrated to the local repository path.');
}
echo "PASS: 241 products imported, legacy model matched without duplicates, manual edits preserved, legacy image URLs migrated.\n";
