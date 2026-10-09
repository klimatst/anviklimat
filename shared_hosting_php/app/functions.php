<?php
declare(strict_types=1);

class UserInputException extends RuntimeException {}

function e(mixed $value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function setting(string $key, string $default = ''): string
{
    static $settings = null;
    if ($settings === null) {
        $settings = [];
        foreach (db()->query('SELECT setting_key, setting_value FROM settings') as $row) {
            $settings[$row['setting_key']] = $row['setting_value'];
        }
    }
    return (string)($settings[$key] ?? $default);
}

function site_path(string $path = ''): string
{
    $base = rtrim((string)($GLOBALS['config']['base_url'] ?? ''), '/');
    return $base . '/' . ltrim($path, '/');
}

function media_url(string $path, string $fallback = ''): string
{
    $path = trim($path);
    if ($path === '') return $fallback === '' ? '' : media_url($fallback);
    if (preg_match('~^https?://~i', $path)) return $path;
    return site_path(ltrim($path, '/'));
}

function redirect_to(string $url): never
{
    header('Location: ' . $url, true, 303);
    exit;
}

function csrf_token(): string
{
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function verify_csrf(): void
{
    $submitted = (string)($_POST['_csrf'] ?? '');
    if ($submitted === '' || !hash_equals(csrf_token(), $submitted)) {
        http_response_code(400);
        exit('Сеанс формы истёк. Обновите страницу и повторите действие.');
    }
}

function flash(string $message, string $kind = 'success'): void
{
    $_SESSION['flash'] = ['message' => $message, 'kind' => $kind];
}

function take_flash(): ?array
{
    $value = $_SESSION['flash'] ?? null;
    unset($_SESSION['flash']);
    return is_array($value) ? $value : null;
}

function admin_user(): ?array
{
    if (empty($_SESSION['admin_id'])) {
        return null;
    }
    $query = db()->prepare('SELECT id, login FROM admins WHERE id = ? LIMIT 1');
    $query->execute([(int)$_SESSION['admin_id']]);
    return $query->fetch() ?: null;
}

function require_admin(): array
{
    $user = admin_user();
    if (!$user) {
        redirect_to(site_path('admin/'));
    }
    return $user;
}

function safe_html(string $html): string
{
    $allowedTags = '<p><h2><h3><h4><ul><ol><li><strong><b><em><i><blockquote><br><hr><a><table><thead><tbody><tr><th><td>';
    $html = strip_tags($html, $allowedTags);
    $html = preg_replace_callback('/<\/?([a-z0-9]+)(?:\s+[^>]*)?>/i', static function (array $match): string {
        $tagText = $match[0];
        $closing = str_starts_with($tagText, '</');
        $tag = strtolower($match[1]);
        $void = in_array($tag, ['br', 'hr'], true);
        if ($closing) {
            return $void ? '' : '</' . $tag . '>';
        }
        if ($tag === 'a' && preg_match('/\bhref\s*=\s*(["\'])(.*?)\1/i', $tagText, $hrefMatch)) {
            $href = trim(html_entity_decode($hrefMatch[2], ENT_QUOTES | ENT_HTML5, 'UTF-8'));
            if (preg_match('~^(https?://|mailto:|/|#)~i', $href)) {
                return '<a href="' . e($href) . '" rel="nofollow noopener">';
            }
        }
        return '<' . $tag . ($void ? '>' : '>');
    }, $html) ?? '';
    return $html;
}

function image_upload(string $field = 'image'): ?string
{
    if (empty($_FILES[$field]) || ($_FILES[$field]['error'] ?? UPLOAD_ERR_NO_FILE) === UPLOAD_ERR_NO_FILE) {
        return null;
    }
    $file = $_FILES[$field];
    if ($file['error'] !== UPLOAD_ERR_OK || $file['size'] > 5 * 1024 * 1024 || !is_uploaded_file($file['tmp_name'])) {
        throw new UserInputException('Фото не загружено: допустимый размер — до 5 МБ.');
    }
    $info = @getimagesize($file['tmp_name']);
    $types = [IMAGETYPE_JPEG => 'jpg', IMAGETYPE_PNG => 'png', IMAGETYPE_WEBP => 'webp'];
    if (!$info || !isset($types[$info[2]])) {
        throw new UserInputException('Загрузите изображение JPG, PNG или WebP.');
    }
    $name = bin2hex(random_bytes(16)) . '.' . $types[$info[2]];
    $target = dirname(__DIR__) . '/storage/uploads/' . $name;
    if (!move_uploaded_file($file['tmp_name'], $target)) {
        throw new UserInputException('Не удалось сохранить фотографию. Проверьте права на storage/uploads.');
    }
    return site_path('storage/uploads/' . $name);
}

function public_header(string $title, string $active = ''): void
{
    $flash = take_flash();
    $brand = setting('site_title', 'ЭКО-КЛИМАТ');
    $phone = setting('phone', '+7 (925) 787-38-48');
    $search = trim((string)($_GET['q'] ?? ''));
    $categories = [];
    try {
        $categories = db()->query('SELECT code, title FROM categories WHERE active=1 AND (parent_id IS NULL OR parent_id=0) ORDER BY sort_order, title LIMIT 18')->fetchAll();
    } catch (Throwable $exception) {
        $categories = [];
    }
    ?>
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#111719">
  <title><?= e($title) ?> · <?= e($brand) ?></title>
  <meta name="description" content="<?= e(setting('site_tagline', 'Инженерные климатические системы, оборудование и монтаж')) ?>">
  <link rel="stylesheet" href="<?= e(site_path('assets/style.css')) ?>">
</head>
<body>
<header class="site-header eco-header">
  <div class="eco-header__system wrap">
    <svg class="eco-header__route-map" viewBox="0 0 1000 112" preserveAspectRatio="none" aria-hidden="true">
      <path d="M130 54 C168 54 165 14 205 14 H865 C900 14 914 54 950 54" class="eco-header__pipe-glow"></path>
      <path d="M130 54 C168 54 165 14 205 14 H865 C900 14 914 54 950 54" class="eco-header__pipe"></path>
      <path d="M130 54 C168 54 165 14 205 14 H865 C900 14 914 54 950 54" class="eco-header__flow"></path>
    </svg>
    <a class="eco-header__unit eco-header__unit--indoor" href="<?= e(site_path()) ?>" aria-label="ЭКО-КЛИМАТ — главная">
      <svg viewBox="0 0 230 78" aria-hidden="true">
        <defs><linearGradient id="eco-unit" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#61727b"/><stop offset=".3" stop-color="#34434c"/><stop offset="1" stop-color="#10171c"/></linearGradient></defs>
        <path d="M12 16Q12 7 24 7H205Q218 7 218 18V49Q218 58 207 61H23Q12 58 12 48Z" fill="url(#eco-unit)" stroke="#7e949c" stroke-width="1.5"/>
        <path d="M20 18Q20 12 28 12H202Q210 12 210 20V40Q115 46 20 40Z" fill="#27353d" stroke="#536a74"/>
        <path d="M24 18Q115 13 205 18" fill="none" stroke="#e0eef0" stroke-opacity=".28"/>
        <path d="M27 49H202" stroke="#0c1216" stroke-width="3"/><circle cx="202" cy="21" r="2.7" fill="#53b797"/>
      </svg>
      <span class="eco-header__brand"><strong><?= e($brand) ?></strong><small>ИНЖЕНЕРНЫЙ КЛИМАТ</small></span>
    </a>
    <div class="eco-header__tools">
      <form class="eco-search" action="<?= e(site_path('index.php')) ?>" method="get" role="search">
        <input type="hidden" name="page" value="catalog">
        <input type="search" name="q" value="<?= e($search) ?>" placeholder="Поиск оборудования и услуг" aria-label="Поиск оборудования и услуг">
        <button type="submit" class="button button-small">Найти</button>
      </form>
      <div class="eco-header__utility">
        <a class="eco-header__phone" href="tel:<?= e(preg_replace('/[^0-9+]/', '', $phone)) ?>"><?= e($phone) ?></a>
        <a class="eco-header__action" href="<?= e(site_path('admin/')) ?>">Войти</a>
        <a class="button button-small" href="<?= e(site_path('index.php?page=contact')) ?>">Оставить заявку</a>
      </div>
    </div>
    <div class="eco-header__unit eco-header__unit--outdoor" aria-label="Наружный климатический блок">
      <svg viewBox="0 0 104 78" aria-hidden="true">
        <defs><linearGradient id="eco-outdoor" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#394750"/><stop offset="1" stop-color="#11191e"/></linearGradient></defs>
        <rect x="8" y="5" width="88" height="68" rx="8" fill="url(#eco-outdoor)" stroke="#58717b" stroke-width="1.5"/>
        <rect x="15" y="11" width="74" height="56" rx="6" fill="#202a31" stroke="#40545d"/>
        <circle cx="52" cy="39" r="22" fill="#26343c" stroke="#77939d" stroke-width="1.4"/>
        <circle cx="52" cy="39" r="3" fill="#53b797"/>
        <path d="M52 36c-5-11-2-15 2-15 5 0 6 7 2 15m-1 6c11-5 15-2 15 2 0 5-7 6-15 2m-6-1c5 11 2 15-2 15-5 0-6-7-2-15m1-6c-11 5-15 2-15-2 0-5 7-6 15-2" fill="#7b9ba6" class="eco-header__fan"/>
      </svg>
      <span>VRV / VRF</span>
    </div>
  </div>
  <nav class="main-nav eco-navigation" aria-label="Основная навигация">
    <div class="wrap nav-inner">
      <a class="nav-link <?= $active === 'home' ? 'active' : '' ?>" href="<?= e(site_path()) ?>">Главная</a>
      <div class="eco-menu-group">
        <a class="nav-link <?= $active === 'catalog' ? 'active' : '' ?>" href="<?= e(site_path('index.php?page=catalog')) ?>">Каталог <span aria-hidden="true">▾</span></a>
        <div class="eco-dropdown"><strong>ОБОРУДОВАНИЕ ПО НАПРАВЛЕНИЯМ</strong>
          <?php foreach ($categories as $category): ?><a href="<?= e(site_path('index.php?page=catalog&category=' . rawurlencode((string)$category['code']))) ?>"><?= e($category['title']) ?></a><?php endforeach; ?>
          <a class="eco-dropdown__all" href="<?= e(site_path('index.php?page=catalog')) ?>">Весь каталог ↗</a>
        </div>
      </div>
      <div class="eco-menu-group">
        <a class="nav-link" href="<?= e(site_path('index.php?page=calculator')) ?>">Цены и расчёты <span aria-hidden="true">▾</span></a>
        <div class="eco-dropdown"><strong>ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ</strong>
          <a href="<?= e(site_path('index.php?page=calculator')) ?>">Предварительный расчёт кондиционирования</a>
          <a href="<?= e(site_path('index.php?page=contact')) ?>">Запросить смету на монтаж</a>
          <a href="<?= e(site_path('index.php?page=contact')) ?>">Запросить расчёт вентиляции</a>
        </div>
      </div>
      <a class="nav-link <?= in_array($active, ['news','article'], true) ? 'active' : '' ?>" href="<?= e(site_path('index.php?page=news')) ?>">Новости</a>
      <a class="nav-link <?= $active === 'gallery' ? 'active' : '' ?>" href="<?= e(site_path('index.php?page=gallery')) ?>">Наши работы</a>
      <a class="nav-link <?= $active === 'contact' ? 'active' : '' ?>" href="<?= e(site_path('index.php?page=contact')) ?>">Сервис и контакты</a>
      <a class="nav-admin" href="<?= e(site_path('admin/')) ?>">Админ-панель ↗</a>
    </div>
  </nav>
</header>
<main>
<?php if ($flash): ?><div class="wrap"><div class="notice <?= e($flash['kind']) ?>"><?= e($flash['message']) ?></div></div><?php endif; ?>
<?php
}

function public_footer(): void
{
    ?>
</main>
<footer class="site-footer"><div class="wrap footer-grid"><div><a class="brand" href="<?= e(site_path()) ?>"><span class="brand-mark">ЭК</span><span><?= e(setting('site_title', 'ЭКО-КЛИМАТ')) ?><small>ИНЖЕНЕРНЫЙ КЛИМАТ</small></span></a><p class="muted"><?= e(setting('site_tagline', 'Оборудование, расчёты и профессиональный монтаж')) ?></p></div>
  <div><strong>Связаться</strong><p><?= e(setting('phone', '+7 (000) 000-00-00')) ?><br><?= e(setting('email', 'info@example.ru')) ?></p></div>
  <div><strong>Разделы</strong><p><a href="<?= e(site_path('index.php?page=catalog')) ?>">Каталог</a><br><a href="<?= e(site_path('index.php?page=gallery')) ?>">Наши работы</a><br><a href="<?= e(site_path('index.php?page=contact')) ?>">Заявка на сервис</a></p></div>
</div><div class="wrap footer-bottom">© <?= date('Y') ?> <?= e(setting('site_title', 'ЭКО-КЛИМАТ')) ?> <a href="<?= e(site_path('admin/')) ?>">Управление сайтом</a></div></footer>
<script src="<?= e(site_path('assets/app.js')) ?>" defer></script>
</body></html>
<?php
}
