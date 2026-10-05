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
    ?>
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= e($title) ?> · <?= e($brand) ?></title>
  <meta name="description" content="<?= e(setting('site_tagline', 'Инженерные климатические системы, оборудование и монтаж')) ?>">
  <link rel="stylesheet" href="<?= e(site_path('assets/style.css')) ?>">
</head>
<body>
<header class="site-header">
  <div class="topline wrap"><a class="brand" href="<?= e(site_path()) ?>"><span class="brand-mark">ЭК</span><span><?= e($brand) ?><small>КЛИМАТИЧЕСКИЕ СИСТЕМЫ</small></span></a>
    <div class="top-contact"><span><?= e(setting('phone', '+7 (000) 000-00-00')) ?></span><a class="button button-small" href="<?= e(site_path('index.php?page=contact')) ?>">Оставить заявку</a></div>
  </div>
  <nav class="main-nav"><div class="wrap nav-inner">
    <?php foreach ([['Главная','home',''],['Каталог','catalog','index.php?page=catalog'],['Новости','news','index.php?page=news'],['Галерея','gallery','index.php?page=gallery'],['Расчёты','calculator','index.php?page=calculator'],['Контакты','contact','index.php?page=contact']] as [$label,$key,$href]): ?>
      <a class="nav-link <?= $active === $key ? 'active' : '' ?>" href="<?= e(site_path($href)) ?>"><?= e($label) ?></a>
    <?php endforeach; ?>
    <a class="nav-admin" href="<?= e(site_path('admin/')) ?>">Вход</a>
  </div></nav>
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
