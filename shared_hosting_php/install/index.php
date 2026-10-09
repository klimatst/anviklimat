<?php
declare(strict_types=1);
$installSecure = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off');
session_set_cookie_params(['httponly'=>true, 'secure'=>$installSecure, 'samesite'=>'Lax', 'path'=>'/']);
session_start();
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: strict-origin-when-cross-origin');
header('X-Frame-Options: SAMEORIGIN');
$root = dirname(__DIR__);
$configPath = $root . '/app/config.php';
if (is_file($configPath)) {
    http_response_code(403);
    exit('<!doctype html><meta charset="utf-8"><h1>Установка уже завершена</h1><p>Удалите папку install с сервера и откройте <a href="../admin/">панель управления</a>.</p>');
}
require_once $root . '/app/functions.php';
require_once $root . '/app/hisense_import.php';
if (empty($_SESSION['install_csrf'])) $_SESSION['install_csrf'] = bin2hex(random_bytes(32));
$error = '';
$done = false;
$hisenseCount = 0;
$scriptName = str_replace('\\', '/', (string)($_SERVER['SCRIPT_NAME'] ?? '/install/index.php'));
$realScript = realpath($scriptName);
if (str_starts_with($scriptName, $root . '/') || ($realScript && str_starts_with(str_replace('\\', '/', $realScript), $root . '/'))) $scriptName = '/install/index.php';
$requirements = [
    'PHP 8.1 или новее' => PHP_VERSION_ID >= 80100,
    'Расширение PDO' => extension_loaded('pdo'),
    'Драйвер MySQL для PDO' => extension_loaded('pdo_mysql'),
    'Папка app доступна для создания config.php' => is_writable($root . '/app'),
    'Папка storage/uploads доступна для записи' => is_writable($root . '/storage/uploads'),
];

function installer_connect_database(string $host, int $port, string $dbName, string $dbUser, string $dbPassword): PDO
{
    $options = [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ];
    $databaseDsn = 'mysql:host=' . $host . ';port=' . $port . ';dbname=' . $dbName . ';charset=utf8mb4';
    try {
        return new PDO($databaseDsn, $dbUser, $dbPassword, $options);
    } catch (PDOException $initialError) {
        // Local XAMPP installations often use root and can create the database
        // automatically. Shared hosting can still use a pre-created database.
        try {
            $serverDsn = 'mysql:host=' . $host . ';port=' . $port . ';charset=utf8mb4';
            $server = new PDO($serverDsn, $dbUser, $dbPassword, $options);
            $server->exec('CREATE DATABASE IF NOT EXISTS `' . $dbName . '` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
            return new PDO($databaseDsn, $dbUser, $dbPassword, $options);
        } catch (Throwable $creationError) {
            throw new RuntimeException(
                'Не удалось подключиться к базе данных. Проверьте имя базы, пользователя и пароль. '
                . 'Если база ещё не создана, создайте её в phpMyAdmin либо используйте учётную запись с правом CREATE DATABASE. '
                . 'Подробности: ' . $creationError->getMessage(),
                0,
                $initialError
            );
        }
    }
}

function installer_schema(PDO $pdo): void
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
}

function installer_seed(PDO $pdo, bool $withDemo, bool $withHisense): int
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

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    if (!hash_equals((string)$_SESSION['install_csrf'], (string)($_POST['_csrf'] ?? ''))) {
        $error = 'Сеанс формы истёк. Обновите страницу и повторите установку.';
    } elseif (in_array(false, $requirements, true)) {
        $error = 'Сначала выполните требования, отмеченные красным.';
    } else {
        $host = trim((string)($_POST['db_host'] ?? 'localhost'));
        $port = max(1, min(65535, (int)($_POST['db_port'] ?? 3306)));
        $dbName = trim((string)($_POST['db_name'] ?? ''));
        $dbUser = trim((string)($_POST['db_user'] ?? ''));
        $dbPassword = (string)($_POST['db_password'] ?? '');
        $adminLogin = trim((string)($_POST['admin_login'] ?? 'admin'));
        $adminPassword = (string)($_POST['admin_password'] ?? '');
        $siteTitle = trim((string)($_POST['site_title'] ?? 'ЭКО-КЛИМАТ'));
        $baseUrl = trim((string)($_POST['base_url'] ?? ''));
        if ($baseUrl === '') {
            $isHttps = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off');
            $basePath = rtrim(dirname(dirname($scriptName)), '/');
            if ($basePath === '/' || $basePath === '.') $basePath = '';
            $baseUrl = ($isHttps ? 'https://' : 'http://') . ($_SERVER['HTTP_HOST'] ?? 'localhost') . $basePath;
        }
        if ($host === '' || !preg_match('/^[A-Za-z0-9._:\[\]-]+$/D', $host) || !preg_match('/^[A-Za-z0-9_$-]+$/D', $dbName) || !preg_match('/^[A-Za-z0-9_$-]+$/D', $dbUser) || $adminLogin === '' || strlen($adminLogin) > 120 || strlen($adminPassword) < 10 || strlen($siteTitle) > 190 || !filter_var($baseUrl, FILTER_VALIDATE_URL) || !preg_match('~^https?://~i', $baseUrl)) {
            $error = 'Проверьте хостинг-реквизиты, адрес сайта и задайте пароль администратора не короче 10 символов.';
        } else {
            try {
                $pdo = installer_connect_database($host, $port, $dbName, $dbUser, $dbPassword);
                installer_schema($pdo);
                $hisenseCount = installer_seed($pdo, !empty($_POST['demo_catalog']), !empty($_POST['hisense_catalog']));
                $admin = $pdo->prepare('INSERT INTO admins (login,password_hash,created_at) VALUES (?,?,NOW()) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)');
                $admin->execute([$adminLogin, password_hash($adminPassword, PASSWORD_DEFAULT)]);
                $updateTitle = $pdo->prepare("INSERT INTO settings (setting_key,setting_value) VALUES ('site_title',?) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)");
                $updateTitle->execute([$siteTitle]);
                $configuration = [
                    'db_host' => $host, 'db_port' => $port, 'db_name' => $dbName, 'db_user' => $dbUser,
                    'db_password' => $dbPassword, 'base_url' => rtrim($baseUrl, '/'),
                ];
                $phpConfig = "<?php\ndeclare(strict_types=1);\nreturn " . var_export($configuration, true) . ";\n";
                if (file_put_contents($configPath, $phpConfig, LOCK_EX) === false) throw new RuntimeException('Не удалось записать app/config.php. Проверьте права на папку app.');
                @chmod($configPath, 0640);
                $done = true;
            } catch (Throwable $exception) {
                $error = 'Установка не завершена: ' . $exception->getMessage();
            }
        }
    }
}
$protocol = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https://' : 'http://';
$guessedBase = $protocol . ($_SERVER['HTTP_HOST'] ?? 'localhost') . rtrim(dirname(dirname($scriptName)), '/');
if (str_ends_with($guessedBase, '://')) $guessedBase .= 'localhost';
?>
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Установка ЭКО-КЛИМАТ</title><link rel="stylesheet" href="../assets/style.css"></head><body class="installer-body"><main class="installer wrap">
<div class="installer-brand"><span class="brand-mark">ЭК</span><div><p class="eyebrow">ЭКО-КЛИМАТ / УСТАНОВЩИК</p><h1>Настройка сайта</h1></div></div>
<?php if ($done): ?><section class="installer-card"><div class="install-success">✓</div><p class="eyebrow">ГОТОВО</p><h2>Сайт установлен</h2><p>База данных настроена, категории и формулы загружены. <?php if ($hisenseCount > 0): ?>Каталог Hisense: обработано <?= (int)$hisenseCount ?> моделей.<?php else: ?>Импорт каталога Hisense пропущен.<?php endif; ?> Панель администратора готова к работе.</p><div class="install-actions"><a class="button" href="../admin/">Открыть панель управления <span>↗</span></a><a class="button button-ghost" href="../">Открыть сайт</a></div><div class="notice warning">Удалите папку install с хостинга после входа. Сохраните логин и пароль администратора.</div></section>
<?php else: ?>
<div class="installer-columns"><section class="installer-card"><p class="eyebrow">ШАГ 1 / ПРОВЕРКА</p><h2>Требования хостинга</h2><ul class="requirements"><?php foreach ($requirements as $label => $ok): ?><li class="<?= $ok ? 'req-ok' : 'req-bad' ?>"><span><?= $ok ? '✓' : '!' ?></span><?= e($label) ?></li><?php endforeach; ?></ul><p class="muted small">Для обычного shared-хостинга нужны PHP 8.1+, PDO MySQL и база MySQL/MariaDB.</p></section>
<section class="installer-card install-form-card"><p class="eyebrow">ШАГ 2 / ПОДКЛЮЧЕНИЕ</p><h2>Параметры сайта</h2><?php if ($error): ?><div class="notice error"><?= e($error) ?></div><?php endif; ?><form method="post"><input type="hidden" name="_csrf" value="<?= e($_SESSION['install_csrf']) ?>"><div class="form-grid"><label>Хост базы данных<input name="db_host" required value="<?= e($_POST['db_host'] ?? 'localhost') ?>" placeholder="localhost"></label><label>Порт<input name="db_port" type="number" required value="<?= e($_POST['db_port'] ?? '3306') ?>"></label><label>Имя базы данных<input name="db_name" required value="<?= e($_POST['db_name'] ?? '') ?>" placeholder="account_climate"></label><label>Пользователь базы<input name="db_user" required value="<?= e($_POST['db_user'] ?? '') ?>" placeholder="account_climate"></label><label class="span-2">Пароль базы данных<input name="db_password" type="password" autocomplete="new-password"></label><label class="span-2">Адрес сайта<input name="base_url" value="<?= e($_POST['base_url'] ?? $guessedBase) ?>" placeholder="https://example.ru"><small>Можно оставить автоматически определённый адрес.</small></label><label class="span-2">Название сайта<input name="site_title" required maxlength="190" value="<?= e($_POST['site_title'] ?? 'ЭКО-КЛИМАТ') ?>"></label></div><hr><p class="eyebrow">ШАГ 3 / АДМИНИСТРАТОР</p><div class="form-grid"><label>Логин администратора<input name="admin_login" required maxlength="120" value="<?= e($_POST['admin_login'] ?? 'admin') ?>"></label><label>Пароль администратора<input name="admin_password" type="password" required minlength="10" autocomplete="new-password"><small>Не менее 10 символов.</small></label></div><label class="check-label demo-choice"><input type="checkbox" name="demo_catalog" value="1" <?= !isset($_POST['db_name']) || !empty($_POST['demo_catalog']) ? 'checked' : '' ?>> Загрузить демонстрационные бренды и 30 тестовых товаров</label><p class="muted small">Демо-записи явно отмечены на сайте и предназначены для проверки. Снимите галочку, если хотите начать с пустого каталога.</p><label class="check-label demo-choice"><input type="checkbox" name="hisense_catalog" value="1" <?= !isset($_POST['db_name']) || !empty($_POST['hisense_catalog']) ? 'checked' : '' ?>> Импортировать 241 реальную модель Hisense из исходного каталога</label><p class="muted small">Включённый импорт использует исходные артикулы, цены, категории, характеристики и доступные фотографии. Уже заполненные вручную поля существующих товаров сохраняются.</p><button class="button install-submit" <?= in_array(false, $requirements, true) ? 'disabled' : '' ?>>Проверить базу и установить сайт <span>↗</span></button></form></section></div>
<?php endif; ?><p class="installer-foot">Отдельный установочный пакет для PHP-хостинга · данные исходного Anvil-проекта не изменяются.</p></main></body></html>
