<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/app/database_setup.php';
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
require_once $root . '/app/engineering_schema.php';
require_once $root . '/app/anvil_import.php';
$storageReady = true;
foreach (['uploads', 'backups', 'imports'] as $storageDirectory) {
    $path = $root . '/storage/' . $storageDirectory;
    if (!is_dir($path) && !mkdir($path, 0750, true) && !is_dir($path)) {
        $storageReady = false;
    }
}
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
    'Расширение zlib для импорта данных Anvil' => extension_loaded('zlib'),
    'Папка app доступна для создания config.php' => is_writable($root . '/app'),
    'Папка storage/uploads доступна для записи' => $storageReady && is_writable($root . '/storage/uploads'),
    'Папка storage/imports доступна для записи' => $storageReady && is_writable($root . '/storage/imports'),
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
                ensure_app_schema($pdo);
                $hisenseCount = seed_app_data($pdo, !empty($_POST['demo_catalog']), !empty($_POST['hisense_catalog']));
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
<section class="installer-card install-form-card"><p class="eyebrow">ШАГ 2 / ПОДКЛЮЧЕНИЕ</p><h2>Параметры сайта</h2><?php if ($error): ?><div class="notice error"><?= e($error) ?></div><?php endif; ?><form method="post"><input type="hidden" name="_csrf" value="<?= e($_SESSION['install_csrf']) ?>"><div class="form-grid"><label>Хост базы данных<input name="db_host" required value="<?= e($_POST['db_host'] ?? 'localhost') ?>" placeholder="localhost"></label><label>Порт<input name="db_port" type="number" required value="<?= e($_POST['db_port'] ?? '3306') ?>"></label><label>Имя базы данных<input name="db_name" required value="<?= e($_POST['db_name'] ?? '') ?>" placeholder="account_climate"></label><label>Пользователь базы<input name="db_user" required value="<?= e($_POST['db_user'] ?? '') ?>" placeholder="account_climate"></label><label class="span-2">Пароль базы данных<input name="db_password" type="password" autocomplete="new-password"></label><label class="span-2">Адрес сайта<input name="base_url" value="<?= e($_POST['base_url'] ?? $guessedBase) ?>" placeholder="https://example.ru"><small>Можно оставить автоматически определённый адрес.</small></label><label class="span-2">Название сайта<input name="site_title" required maxlength="190" value="<?= e($_POST['site_title'] ?? 'ЭКО-КЛИМАТ') ?>"></label></div><hr><p class="eyebrow">ШАГ 3 / АДМИНИСТРАТОР</p><div class="form-grid"><label>Логин администратора<input name="admin_login" required maxlength="120" value="<?= e($_POST['admin_login'] ?? 'admin') ?>"></label><label>Пароль администратора<input name="admin_password" type="password" required minlength="10" autocomplete="new-password"><small>Не менее 10 символов.</small></label></div><label class="check-label demo-choice"><input type="checkbox" name="demo_catalog" value="1" <?= !empty($_POST['demo_catalog']) ? 'checked' : '' ?>> Загрузить демонстрационные бренды и 30 тестовых товаров</label><p class="muted small">Демо-записи явно отмечены на сайте и предназначены для проверки. Демонстрационные данные выключены по умолчанию.</p><label class="check-label demo-choice"><input type="checkbox" name="hisense_catalog" value="1" <?= !isset($_POST['db_name']) || !empty($_POST['hisense_catalog']) ? 'checked' : '' ?>> Импортировать 241 реальную модель Hisense из исходного каталога</label><p class="muted small">Включённый импорт использует исходные артикулы, цены, категории, характеристики и доступные фотографии. Уже заполненные вручную поля существующих товаров сохраняются.</p><button class="button install-submit" <?= in_array(false, $requirements, true) ? 'disabled' : '' ?>>Проверить базу и установить сайт <span>↗</span></button></form></section></div>
<?php endif; ?><p class="installer-foot">Отдельный установочный пакет для PHP-хостинга · данные исходного Anvil-проекта не изменяются.</p></main></body></html>
