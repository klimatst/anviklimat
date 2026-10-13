<?php
declare(strict_types=1);

require_once __DIR__ . '/engineering_schema.php';
require_once __DIR__ . '/anvil_import.php';
require_once __DIR__ . '/hisense_import.php';

function ensure_app_schema(PDO $pdo): void
{
    $statements = [
        "CREATE TABLE IF NOT EXISTS admins (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, login VARCHAR(120) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS settings (setting_key VARCHAR(120) NOT NULL PRIMARY KEY, setting_value TEXT NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS categories (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, code VARCHAR(140) NOT NULL UNIQUE, title VARCHAR(190) NOT NULL, parent_id INT UNSIGNED NULL, image_url VARCHAR(500) NOT NULL DEFAULT '', sort_order INT NOT NULL DEFAULT 100, active TINYINT(1) NOT NULL DEFAULT 1, INDEX idx_categories_parent (parent_id), CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS brands (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(190) NOT NULL UNIQUE, logo_url VARCHAR(500) NOT NULL DEFAULT '', description TEXT NOT NULL, active TINYINT(1) NOT NULL DEFAULT 1) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS products (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, model VARCHAR(190) NOT NULL, sku VARCHAR(120) NULL DEFAULT NULL, brand_id INT UNSIGNED NULL, category_id INT UNSIGNED NULL, description TEXT NOT NULL, price DECIMAL(12,2) NOT NULL DEFAULT 0, image_url VARCHAR(500) NOT NULL DEFAULT '', specifications LONGTEXT NOT NULL, is_demo TINYINT(1) NOT NULL DEFAULT 0, active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME NOT NULL, UNIQUE KEY uq_products_sku (sku), INDEX idx_products_category (category_id), INDEX idx_products_brand (brand_id), CONSTRAINT fk_products_brand FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL, CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS news (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, title VARCHAR(220) NOT NULL, slug VARCHAR(220) NOT NULL UNIQUE, excerpt TEXT NOT NULL, content LONGTEXT NOT NULL, image_url VARCHAR(500) NOT NULL DEFAULT '', published TINYINT(1) NOT NULL DEFAULT 0, created_at DATETIME NOT NULL, published_at DATETIME NULL, INDEX idx_news_public (published, published_at)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS pages (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, title VARCHAR(220) NOT NULL, slug VARCHAR(220) NOT NULL UNIQUE, content LONGTEXT NOT NULL, published TINYINT(1) NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS gallery (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, title VARCHAR(220) NOT NULL, alt_text VARCHAR(220) NOT NULL DEFAULT '', image_url VARCHAR(500) NOT NULL, location VARCHAR(190) NOT NULL DEFAULT '', sort_order INT NOT NULL DEFAULT 100, published TINYINT(1) NOT NULL DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS leads (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) NOT NULL, phone VARCHAR(80) NOT NULL, email VARCHAR(190) NOT NULL DEFAULT '', message TEXT NOT NULL, status VARCHAR(40) NOT NULL DEFAULT 'new', created_at DATETIME NOT NULL, INDEX idx_leads_status (status, created_at)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS formulas (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, code VARCHAR(140) NOT NULL UNIQUE, module VARCHAR(100) NOT NULL, title VARCHAR(220) NOT NULL, expression TEXT NOT NULL, input_schema LONGTEXT NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    ];
    foreach ($statements as $statement) $pdo->exec($statement);
    ensure_engineering_schema($pdo);
    ensure_anvil_export_schema($pdo);
}

function seed_app_data(PDO $pdo, bool $withDemo, bool $withHisense): int
{
    $dataRoot = dirname(__DIR__) . '/data/';
    $categories = json_decode((string)file_get_contents($dataRoot . 'categories.json'), true, 512, JSON_THROW_ON_ERROR);
    $insertCategory = $pdo->prepare('INSERT INTO categories (code,title,parent_id,image_url,sort_order,active) VALUES (?,?,?,?,?,1) ON DUPLICATE KEY UPDATE title=VALUES(title), parent_id=VALUES(parent_id), image_url=VALUES(image_url), sort_order=VALUES(sort_order)');
    $pending = $categories;
    $rounds = 0;
    while ($pending && $rounds++ < 100) {
        $remaining = [];
        foreach ($pending as $category) {
            $parentId = null;
            if (!empty($category['parent_code'])) {
                $findParent = $pdo->prepare('SELECT id FROM categories WHERE code=?');
                $findParent->execute([$category['parent_code']]);
                $parentId = $findParent->fetchColumn();
                if (!$parentId) { $remaining[] = $category; continue; }
            }
            $image = '';
            if (!empty($category['image_url'])) {
                $basename = basename((string)parse_url($category['image_url'], PHP_URL_PATH));
                $candidate = dirname(__DIR__) . '/assets/images/' . $basename;
                $image = is_file($candidate) ? 'assets/images/' . $basename : (preg_match('~^https://~i', $category['image_url']) ? $category['image_url'] : '');
            }
            $insertCategory->execute([(string)$category['code'], (string)$category['title'], $parentId ?: null, $image, (int)($category['sort_order'] ?? 100)]);
        }
        if (count($remaining) === count($pending)) break;
        $pending = $remaining;
    }

    $formulas = json_decode((string)file_get_contents($dataRoot . 'formulas.json'), true, 512, JSON_THROW_ON_ERROR);
    $formulaInsert = $pdo->prepare('INSERT INTO formulas (code,module,title,expression,input_schema) VALUES (?,?,?,?,?) ON DUPLICATE KEY UPDATE module=VALUES(module), title=VALUES(title), expression=VALUES(expression), input_schema=VALUES(input_schema)');
    foreach ($formulas as $formula) $formulaInsert->execute([$formula['code'], $formula['module'], $formula['title'], $formula['expression'], json_encode($formula['input_schema'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)]);

    $defaults = [
        'site_title' => 'ЭКО-КЛИМАТ',
        'site_tagline' => 'Инженерные системы, климатическая техника и профессиональный монтаж.',
        'phone' => '+7 (000) 000-00-00',
        'email' => 'info@example.ru',
        'address' => 'Ваш город · выезд по договорённости',
    ];
    $settingInsert = $pdo->prepare('INSERT INTO settings (setting_key,setting_value) VALUES (?,?) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)');
    foreach ($defaults as $key => $value) $settingInsert->execute([$key, $value]);

    $pricePagesPath = $dataRoot . 'price_pages.json';
    if (is_file($pricePagesPath)) {
        $pricePages = json_decode((string)file_get_contents($pricePagesPath), true, 512, JSON_THROW_ON_ERROR);
        $pageInsert = $pdo->prepare(
            'INSERT INTO pages (title,slug,content,published,updated_at) VALUES (?,?,?,1,NOW()) '
            . 'ON DUPLICATE KEY UPDATE title=VALUES(title), content=IF(content=\'\',VALUES(content),content)'
        );
        foreach ($pricePages as $pricePage) {
            if (!is_array($pricePage) || empty($pricePage['slug']) || empty($pricePage['title']) || empty($pricePage['content'])) {
                continue;
            }
            $pageInsert->execute([
                (string)$pricePage['title'],
                (string)$pricePage['slug'],
                (string)$pricePage['content'],
            ]);
        }
    }

    $hisenseCount = $withHisense ? import_hisense_catalog($pdo, $dataRoot . 'hisense_catalog.json') : 0;
    if (!$withDemo) return $hisenseCount;
    $demo = json_decode((string)file_get_contents($dataRoot . 'demo_catalog.json'), true, 512, JSON_THROW_ON_ERROR);
    $brandInsert = $pdo->prepare("INSERT INTO brands (name,description,active) VALUES (?,'',1) ON DUPLICATE KEY UPDATE name=VALUES(name)");
    foreach ($demo['brands'] as $brand) $brandInsert->execute([$brand]);
    $productInsert = $pdo->prepare('INSERT INTO products (model,sku,brand_id,category_id,description,price,image_url,specifications,is_demo,active,created_at) VALUES (?,?,?,?,?,?,?,?,1,1,NOW()) ON DUPLICATE KEY UPDATE model=VALUES(model), brand_id=VALUES(brand_id), category_id=VALUES(category_id), description=VALUES(description), price=VALUES(price), image_url=VALUES(image_url), specifications=VALUES(specifications), is_demo=1, active=1');
    $brandQuery = $pdo->prepare('SELECT id FROM brands WHERE name=?');
    $categoryQuery = $pdo->prepare('SELECT id FROM categories WHERE code=?');
    foreach ($demo['products'] as $product) {
        $brandQuery->execute([$product['brand']]); $brandId = $brandQuery->fetchColumn();
        $categoryQuery->execute([$product['subcategory_code']]); $categoryId = $categoryQuery->fetchColumn();
        if (!$categoryId) { $categoryQuery->execute([$product['category_code']]); $categoryId = $categoryQuery->fetchColumn(); }
        $imageName = basename((string)parse_url((string)$product['image'], PHP_URL_PATH));
        $image = is_file(dirname(__DIR__) . '/assets/images/' . $imageName) ? 'assets/images/' . $imageName : 'assets/images/conditioners.jpg';
        $productInsert->execute([$product['model'], $product['sku'], $brandId ?: null, $categoryId ?: null, $product['description'], $product['sale_price'], $image, json_encode($product['specifications'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)]);
    }
    return $hisenseCount;
}

