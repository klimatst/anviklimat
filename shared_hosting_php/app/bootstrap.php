<?php
declare(strict_types=1);

$configFile = __DIR__ . '/config.php';
if (!is_file($configFile)) {
    header('Location: ../install/');
    exit;
}
$config = require $configFile;
require_once __DIR__ . '/functions.php';
require_once __DIR__ . '/engineering_os.php';

header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: strict-origin-when-cross-origin');
header('X-Frame-Options: SAMEORIGIN');

$isSecure = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off');
if (session_status() !== PHP_SESSION_ACTIVE) {
    session_set_cookie_params([
        'httponly' => true,
        'secure' => $isSecure,
        'samesite' => 'Lax',
        'path' => '/',
    ]);
    session_start();
}

function db(): PDO
{
    static $pdo = null;
    global $config;
    if ($pdo instanceof PDO) {
        return $pdo;
    }
    $dsn = 'mysql:host=' . $config['db_host'] . ';port=' . $config['db_port'] . ';dbname=' . $config['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    return $pdo;
}

/**
 * Install built-in, source-derived price pages into existing local databases
 * without overwriting content already edited by the site administrator.
 */
function ensure_builtin_price_pages(): void
{
    static $checked = false;
    if ($checked) {
        return;
    }
    $checked = true;
    $path = dirname(__DIR__) . '/data/price_pages.json';
    if (!is_file($path)) {
        return;
    }
    try {
        $pages = json_decode((string)file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
        if (!is_array($pages)) {
            return;
        }
        $known = db()->query('SELECT slug FROM pages')->fetchAll(PDO::FETCH_COLUMN);
        $known = array_fill_keys(array_map('strval', $known), true);
        $insert = db()->prepare('INSERT INTO pages (title,slug,content,published,updated_at) VALUES (?,?,?,1,NOW())');
        foreach ($pages as $page) {
            if (!is_array($page) || empty($page['slug']) || empty($page['title']) || empty($page['content'])) {
                continue;
            }
            $slug = (string)$page['slug'];
            if (isset($known[$slug])) {
                continue;
            }
            $insert->execute([(string)$page['title'], $slug, (string)$page['content']]);
            $known[$slug] = true;
        }
    } catch (Throwable $exception) {
        // Do not take down an existing site if its DB account is read-only.
        error_log('KlimaEco built-in page seed skipped: ' . $exception->getMessage());
    }
}

ensure_builtin_price_pages();
