<?php
declare(strict_types=1);
require __DIR__ . '/app/bootstrap.php';

$page = (string)($_GET['page'] ?? 'home');
$allowed = ['home', 'catalog', 'product', 'news', 'article', 'gallery', 'calculator', 'ventilation-calculator', 'refrigerant-ruler', 'contact', 'content'];
if (!in_array($page, $allowed, true)) {
    http_response_code(404);
    $page = 'home';
}

if ($page === 'contact' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    verify_csrf();
    $name = trim((string)($_POST['name'] ?? ''));
    $phone = trim((string)($_POST['phone'] ?? ''));
    $email = trim((string)($_POST['email'] ?? ''));
    $message = trim((string)($_POST['message'] ?? ''));
    if ($name === '' || $phone === '' || strlen($name) > 480 || strlen($phone) > 320 || strlen($message) > 16000 || ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL))) {
        flash('Проверьте имя, телефон и электронную почту.', 'error');
        redirect_to(site_path('index.php?page=contact'));
    }
    $insert = db()->prepare('INSERT INTO leads (name, phone, email, message, created_at) VALUES (?, ?, ?, ?, NOW())');
    $insert->execute([$name, $phone, $email, $message]);
    flash('Заявка отправлена. Мы свяжемся с вами.');
    redirect_to(site_path('index.php?page=contact'));
}

$categories = db()->query('SELECT id, code, title, parent_id, image_url FROM categories WHERE active = 1 ORDER BY sort_order, title')->fetchAll();
$categoryByCode = [];
foreach ($categories as $category) {
    $categoryByCode[$category['code']] = $category;
}
$title = ['home' => 'Инженерный климат', 'catalog' => 'Каталог оборудования', 'product' => 'Карточка товара', 'news' => 'Новости', 'article' => 'Новости', 'gallery' => 'Наши работы', 'calculator' => 'Инженерные расчёты', 'ventilation-calculator' => 'Расчёт вентиляции', 'refrigerant-ruler' => 'Линейка холодильщика', 'contact' => 'Контакты', 'content' => 'Информация'][$page];
$activeNav = in_array($page, ['catalog', 'product'], true) ? 'catalog' : (in_array($page, ['news', 'article'], true) ? 'news' : (in_array($page, ['calculator', 'ventilation-calculator', 'refrigerant-ruler'], true) ? 'calculator' : $page));
if ($page === 'home') $activeNav = 'home';
public_header($title, $activeNav);
?>
<?php if ($page === 'home'): ?>
<section class="hero"><div class="hero-photo" style="background-image:url('<?= e(site_path('assets/images/vrv-vrf.jpg')) ?>')"></div><div class="wrap hero-content"><p class="eyebrow">ПРОЕКТИРОВАНИЕ · ПОСТАВКА · МОНТАЖ</p><h1>Климатические системы<br><span>для вашего пространства</span></h1><p><?= e(setting('site_tagline', 'Подбор оборудования и инженерные решения для дома и бизнеса.')) ?></p><div class="hero-actions"><a class="button" href="<?= e(site_path('index.php?page=catalog')) ?>">Открыть каталог <span>↗</span></a><a class="button button-ghost" href="<?= e(site_path('index.php?page=contact')) ?>">Заказать консультацию</a></div></div><div class="hero-stats wrap"><div><b>01</b><span>Подбор<br>оборудования</span></div><div><b>02</b><span>Инженерный<br>расчёт</span></div><div><b>03</b><span>Монтаж<br>под ключ</span></div></div></section>
<section class="section wrap"><div class="section-heading"><div><p class="eyebrow">ОБОРУДОВАНИЕ</p><h2>Системы для климата</h2></div><a class="text-link" href="<?= e(site_path('index.php?page=catalog')) ?>">Весь каталог <span>↗</span></a></div><div class="category-grid">
<?php $featuredCodes = ['air-conditioning', 'vrf-vrv', 'ventilation', 'materials']; foreach ($featuredCodes as $code): if (empty($categoryByCode[$code])) continue; $c = $categoryByCode[$code]; ?>
<a class="category-card" href="<?= e(site_path('index.php?page=catalog&category=' . rawurlencode($code))) ?>"><img src="<?= e(media_url((string)$c['image_url'], 'assets/images/vrv-vrf.jpg')) ?>" alt=""><span class="category-shade"></span><span class="category-info"><small>КАТАЛОГ / 0<?= count($categories) ?></small><strong><?= e($c['title']) ?></strong><i>Открыть раздел ↗</i></span></a>
<?php endforeach; ?>
</div></section>
<section class="section section-dark"><div class="wrap"><div class="section-heading"><div><p class="eyebrow">ВЫБОР РЕДАКТОРА</p><h2>Популярное оборудование</h2></div><a class="text-link" href="<?= e(site_path('index.php?page=catalog')) ?>">Перейти в каталог ↗</a></div><div class="product-grid">
<?php $items = db()->query('SELECT p.*, b.name brand_name FROM products p LEFT JOIN brands b ON b.id=p.brand_id WHERE p.active=1 ORDER BY p.id DESC LIMIT 4')->fetchAll(); foreach ($items as $item): ?>
<a class="product-card" href="<?= e(site_path('index.php?page=product&id=' . (int)$item['id'])) ?>"><div class="product-image"><img src="<?= e(media_url((string)$item['image_url'], 'assets/images/conditioners.jpg')) ?>" alt=""><span class="badge">КАТАЛОГ</span></div><div class="product-meta"><?= e($item['brand_name'] ?: 'Оборудование') ?></div><h3><?= e($item['model']) ?></h3><div class="product-bottom"><strong><?= $item['is_demo'] ? 'ДЕМО · ' : '' ?><?= number_format((float)$item['price'], 0, ',', ' ') ?> ₽</strong><span>↗</span></div></a>
<?php endforeach; ?>
<?php if (!$items): ?><div class="empty-state">Каталог скоро пополнится. <a href="<?= e(site_path('index.php?page=contact')) ?>">Запросите подбор оборудования.</a></div><?php endif; ?>
</div></div></section>
<section class="feature-band"><div class="wrap feature-band-inner"><div><p class="eyebrow">ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ</p><h2>От расчёта<br>к правильному решению</h2><p>Предварительные расчёты помогут оценить задачу до выезда специалиста.</p></div><a class="button" href="<?= e(site_path('index.php?page=calculator')) ?>">Открыть расчёты <span>↗</span></a></div></section>
<section class="section wrap"><div class="section-heading"><div><p class="eyebrow">ПРОЕКТЫ</p><h2>Выполненные работы</h2></div><a class="text-link" href="<?= e(site_path('index.php?page=gallery')) ?>">Вся галерея ↗</a></div><div class="gallery-grid">
<?php $photos = db()->query('SELECT * FROM gallery WHERE published=1 ORDER BY sort_order, id DESC LIMIT 3')->fetchAll(); foreach ($photos as $photo): ?><a class="gallery-card" href="<?= e(site_path('index.php?page=gallery')) ?>"><img src="<?= e(media_url((string)$photo['image_url'])) ?>" alt="<?= e($photo['alt_text'] ?: $photo['title']) ?>"><span><?= e($photo['title']) ?></span></a><?php endforeach; ?>
<?php if (!$photos): ?><a class="gallery-card" href="<?= e(site_path('index.php?page=gallery')) ?>"><img src="<?= e(site_path('assets/images/ventilation.jpg')) ?>" alt="Вентиляционное оборудование"><span>Инженерные системы и монтаж</span></a><a class="gallery-card" href="<?= e(site_path('index.php?page=gallery')) ?>"><img src="<?= e(site_path('assets/images/conditioners.jpg')) ?>" alt="Климатическое оборудование"><span>Климатические решения</span></a><a class="gallery-card" href="<?= e(site_path('index.php?page=gallery')) ?>"><img src="<?= e(site_path('assets/images/materials.jpg')) ?>" alt="Монтаж инженерных систем"><span>Работы на объекте</span></a><?php endif; ?>
</div></section>
<?php elseif ($page === 'catalog'): ?>
<?php
$search = trim((string)($_GET['q'] ?? ''));
$selectedCode = (string)($_GET['category'] ?? '');
$selected = $categoryByCode[$selectedCode] ?? null;
$sql = 'SELECT p.*, b.name brand_name, c.title category_title FROM products p LEFT JOIN brands b ON b.id=p.brand_id LEFT JOIN categories c ON c.id=p.category_id WHERE p.active=1';
$params = [];
if ($search !== '') { $sql .= ' AND (p.model LIKE ? OR p.description LIKE ? OR b.name LIKE ?)'; $like = '%' . $search . '%'; array_push($params, $like, $like, $like); }
if ($selected) {
    $ids = [(int)$selected['id']]; $changed = true;
    while ($changed) { $changed = false; foreach ($categories as $c) { if (in_array((int)$c['parent_id'], $ids, true) && !in_array((int)$c['id'], $ids, true)) { $ids[] = (int)$c['id']; $changed = true; } } }
    $sql .= ' AND p.category_id IN (' . implode(',', array_fill(0, count($ids), '?')) . ')'; array_push($params, ...$ids);
}
$sql .= ' ORDER BY p.id DESC LIMIT 100'; $query = db()->prepare($sql); $query->execute($params); $items = $query->fetchAll();
?>
<section class="page-hero"><div class="wrap"><p class="eyebrow">ЭКО-КЛИМАТ / ОБОРУДОВАНИЕ</p><h1>Каталог систем</h1><p>Подберите оборудование по разделу или найдите нужную модель.</p></div></section><section class="section wrap"><form class="search-bar" method="get"><input type="hidden" name="page" value="catalog"><input name="q" value="<?= e($search) ?>" placeholder="Модель, бренд или назначение"><button class="button">Найти <span>↗</span></button></form><div class="catalog-layout"><aside class="catalog-sidebar"><h3>Разделы</h3><a class="side-link <?= !$selected ? 'selected' : '' ?>" href="<?= e(site_path('index.php?page=catalog')) ?>">Все товары</a><?php foreach ($categories as $c): if (!empty($c['parent_id'])) continue; ?><a class="side-link <?= $selectedCode === $c['code'] ? 'selected' : '' ?>" href="<?= e(site_path('index.php?page=catalog&category=' . rawurlencode($c['code']))) ?>"><?= e($c['title']) ?></a><?php endforeach; ?></aside><div><div class="result-line"><span><?= $selected ? e($selected['title']) : 'Все разделы' ?></span><span><?= count($items) ?> позиций</span></div><div class="product-grid">
<?php foreach ($items as $item): ?><a class="product-card" href="<?= e(site_path('index.php?page=product&id=' . (int)$item['id'])) ?>"><div class="product-image"><img src="<?= e(media_url((string)$item['image_url'], 'assets/images/conditioners.jpg')) ?>" alt=""><span class="badge"><?= $item['is_demo'] ? 'ДЕМО · НЕ ДЛЯ ПРОДАЖИ' : e($item['category_title'] ?: 'ОБОРУДОВАНИЕ') ?></span></div><div class="product-meta"><?= e($item['brand_name'] ?: 'Бренд не указан') ?></div><h3><?= e($item['model']) ?></h3><p class="card-description"><?= e($item['description']) ?></p><div class="product-bottom"><strong><?= number_format((float)$item['price'], 0, ',', ' ') ?> ₽</strong><span>Подробнее ↗</span></div></a><?php endforeach; ?>
<?php if (!$items): ?><div class="empty-state">В этом разделе пока нет товаров. Напишите нам — поможем подобрать оборудование.</div><?php endif; ?>
</div></div></div></section>
<?php elseif ($page === 'product'): ?>
<?php $query = db()->prepare('SELECT p.*, b.name brand_name, c.title category_title FROM products p LEFT JOIN brands b ON b.id=p.brand_id LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=? AND p.active=1'); $query->execute([(int)($_GET['id'] ?? 0)]); $item = $query->fetch(); if (!$item): http_response_code(404); ?><section class="section wrap"><h1>Товар не найден</h1><a href="<?= e(site_path('index.php?page=catalog')) ?>">Вернуться в каталог</a></section><?php else: $specs = json_decode((string)$item['specifications'], true) ?: []; ?>
<section class="section wrap product-detail"><div class="detail-image"><img src="<?= e(media_url((string)$item['image_url'], 'assets/images/conditioners.jpg')) ?>" alt="<?= e($item['model']) ?>"></div><div class="detail-info"><p class="eyebrow"><?= e($item['category_title'] ?: 'КАТАЛОГ') ?> / <?= e($item['brand_name'] ?: 'БРЕНД') ?></p><h1><?= e($item['model']) ?></h1><?php if ($item['is_demo']): ?><div class="notice warning">Демонстрационный товар: фотография, цена и параметры приведены для проверки каталога и не являются коммерческим предложением.</div><?php endif; ?><p class="detail-copy"><?= nl2br(e($item['description'])) ?></p><div class="detail-price"><?= number_format((float)$item['price'], 0, ',', ' ') ?> ₽</div><a class="button" href="<?= e(site_path('index.php?page=contact')) ?>">Уточнить наличие <span>↗</span></a><?php if ($specs): ?><h3 class="spec-heading">Характеристики</h3><dl class="spec-list"><?php foreach ($specs as $spec): ?><div><dt><?= e($spec[0] ?? '') ?></dt><dd><?= e($spec[1] ?? '') ?> <?= e($spec[2] ?? '') ?></dd></div><?php endforeach; ?></dl><?php endif; ?></div></section>
<?php endif; ?>
<?php elseif ($page === 'news' || $page === 'article'): ?>
<?php if ($page === 'article'): $query = db()->prepare('SELECT * FROM news WHERE slug=? AND published=1'); $query->execute([(string)($_GET['slug'] ?? '')]); $article = $query->fetch(); if (!$article): http_response_code(404); ?><section class="section wrap"><h1>Публикация не найдена</h1><a href="<?= e(site_path('index.php?page=news')) ?>">Все новости</a></section><?php else: ?><article class="article section wrap"><p class="eyebrow">НОВОСТИ / <?= e(date('d.m.Y', strtotime($article['published_at'] ?: $article['created_at']))) ?></p><h1><?= e($article['title']) ?></h1><?php if ($article['image_url']): ?><img class="article-cover" src="<?= e(media_url((string)$article['image_url'])) ?>" alt=""><?php endif; ?><div class="rich-content"><?= safe_html((string)$article['content']) ?></div></article><?php endif; ?>
<?php else: $items = db()->query('SELECT * FROM news WHERE published=1 ORDER BY published_at DESC, id DESC LIMIT 30')->fetchAll(); ?><section class="page-hero"><div class="wrap"><p class="eyebrow">ЖУРНАЛ / ЭКО-КЛИМАТ</p><h1>Новости и материалы</h1><p>Полезная информация о климатической технике и инженерных решениях.</p></div></section><section class="section wrap"><div class="news-grid"><?php foreach ($items as $article): ?><a class="news-card" href="<?= e(site_path('index.php?page=article&slug=' . rawurlencode($article['slug']))) ?>"><?php if ($article['image_url']): ?><img src="<?= e(media_url((string)$article['image_url'])) ?>" alt=""><?php else: ?><div class="news-placeholder">ЭК <span>·</span> HVAC</div><?php endif; ?><div class="news-card-body"><small><?= e(date('d.m.Y', strtotime($article['published_at'] ?: $article['created_at']))) ?></small><h2><?= e($article['title']) ?></h2><p><?= e($article['excerpt']) ?></p><span class="text-link">Читать ↗</span></div></a><?php endforeach; ?><?php if (!$items): ?><div class="empty-state">Публикации появятся здесь после добавления в панели управления.</div><?php endif; ?></div></section><?php endif; ?>
<?php elseif ($page === 'calculator'): ?>
<?php $calc = null; if ($_SERVER['REQUEST_METHOD'] === 'POST') { verify_csrf(); $area = max(0, min(10000, (float)($_POST['area'] ?? 0))); $height = max(2, min(10, (float)($_POST['height'] ?? 2.7))); $people = max(0, min(500, (int)($_POST['people'] ?? 0))); $sun = isset($_POST['sun']) ? 1.15 : 1; $calc = ['area' => $area, 'height' => $height, 'people' => $people, 'kw' => $area * 0.1 * ($height / 2.7) * $sun + $people * 0.1]; } ?><section class="page-hero"><div class="wrap"><p class="eyebrow">ИНЖЕНЕРНЫЕ ИНСТРУМЕНТЫ</p><h1>Предварительный расчёт</h1><p>Оцените ориентировочную холодопроизводительность для помещения.</p></div></section><section class="section wrap calc-layout"><div class="calc-card"><p class="eyebrow">КОНДИЦИОНИРОВАНИЕ</p><h2>Нагрузка помещения</h2><p class="muted">Упрощённая предварительная оценка. Для точного подбора требуется инженерный расчёт.</p><form method="post"><?= '<input type="hidden" name="_csrf" value="' . e(csrf_token()) . '">' ?><label>Площадь помещения, м²<input type="number" name="area" min="1" max="10000" step="0.1" required value="<?= e($calc['area'] ?? '25') ?>"></label><label>Высота потолка, м<input type="number" name="height" min="2" max="10" step="0.1" required value="<?= e($calc['height'] ?? '2.7') ?>"></label><label>Количество людей<input type="number" name="people" min="0" max="500" step="1" required value="<?= e($calc['people'] ?? '2') ?>"></label><label class="check-label"><input type="checkbox" name="sun" <?= !empty($calc['sun']) ? 'checked' : '' ?>> Солнечная сторона или большие окна</label><button class="button">Рассчитать <span>↗</span></button></form></div><div class="calc-result"><?php if ($calc): ?><p class="eyebrow">ОРИЕНТИРОВОЧНЫЙ РЕЗУЛЬТАТ</p><strong><?= number_format($calc['kw'], 1, ',', ' ') ?> <small>кВт</small></strong><p>Перед покупкой проверьте результат с инженером: учитываются окна, техника, ориентация и режим работы.</p><?php else: ?><div class="result-orbit">kW</div><p>Введите параметры комнаты, чтобы получить предварительную оценку.</p><?php endif; ?></div></section>
<?php elseif ($page === 'ventilation-calculator'): ?>
<?php require __DIR__ . '/app/ventilation_calculator_view.php'; ?>
<?php elseif ($page === 'refrigerant-ruler'): ?>
<?php require __DIR__ . '/app/refrigerant_ruler_view.php'; ?>
<?php elseif ($page === 'contact'): ?>
<section class="page-hero"><div class="wrap"><p class="eyebrow">КОНСУЛЬТАЦИЯ / СЕРВИС</p><h1>Обсудим вашу задачу</h1><p>Оставьте контакты — поможем с подбором оборудования, монтажом или обслуживанием.</p></div></section><section class="section wrap contact-layout"><div class="contact-details"><p class="eyebrow">НА СВЯЗИ</p><h2>Ответим и подскажем следующий шаг</h2><p class="contact-big"><?= e(setting('phone', '+7 (000) 000-00-00')) ?></p><p><?= e(setting('email', 'info@example.ru')) ?></p><p class="muted"><?= e(setting('address', 'Ваш город · выезд по договорённости')) ?></p></div><form class="contact-form" method="post"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><label>Как к вам обращаться<input name="name" maxlength="120" required></label><label>Телефон<input name="phone" maxlength="80" required></label><label>Электронная почта<input type="email" name="email" maxlength="190"></label><label>Что нужно сделать?<textarea name="message" rows="5" maxlength="4000" placeholder="Подбор, монтаж, обслуживание или ремонт"></textarea></label><button class="button">Отправить заявку <span>↗</span></button><small>Нажимая кнопку, вы соглашаетесь на обработку данных для ответа на заявку.</small></form></section>
<?php elseif ($page === 'content'): ?>
<?php $query = db()->prepare('SELECT * FROM pages WHERE slug=? AND published=1'); $query->execute([(string)($_GET['slug'] ?? '')]); $contentPage = $query->fetch(); if (!$contentPage): http_response_code(404); ?><section class="section wrap"><h1>Страница не найдена</h1></section><?php else: ?><article class="article section wrap"><p class="eyebrow">ЭКО-КЛИМАТ / ИНФОРМАЦИЯ</p><h1><?= e($contentPage['title']) ?></h1><div class="rich-content"><?= safe_html((string)$contentPage['content']) ?></div></article><?php endif; ?>
<?php endif; ?>
<?php public_footer(); ?>
