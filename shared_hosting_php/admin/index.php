<?php
declare(strict_types=1);
require dirname(__DIR__) . '/app/bootstrap.php';
$tabs = ['dashboard'=>'Обзор','categories'=>'Категории','brands'=>'Бренды','products'=>'Товары','news'=>'Новости','pages'=>'Страницы','gallery'=>'Галерея','leads'=>'Заявки','settings'=>'Настройки','formulas'=>'Формулы'];
$ventilationSettingFields = [
    'ventilation_people_airflow' => ['ventilation.people_airflow','Воздухообмен на человека, м³/ч',40,0,1000],
    'ventilation_supply_factor' => ['ventilation.supply_factor','Коэффициент притока',1,0,5],
    'ventilation_exhaust_factor' => ['ventilation.exhaust_factor','Коэффициент вытяжки',1,0,5],
    'ventilation_fan_reserve_percent' => ['ventilation.fan_reserve_percent','Резерв вентилятора, %',15,0,100],
    'ventilation_duct_velocity' => ['ventilation.duct_velocity','Скорость в воздуховоде, м/с',4,0.1,30],
    'ventilation_rounding_step' => ['ventilation.rounding_step','Шаг округления цены, ₽',10,1,100000],
    'ventilation_duct_rounding_step' => ['ventilation.duct_rounding_step','Шаг округления диаметра, мм',5,1,1000],
    'ventilation_price_equipment_base' => ['ventilation.price_equipment_base','Базовая стоимость установки, ₽',20000,0,100000000],
    'ventilation_price_automation' => ['ventilation.price_automation','Комплект автоматики, ₽',40000,0,100000000],
    'ventilation_price_ducts_m2' => ['ventilation.price_ducts_m2','Воздуховоды за метр, ₽',155,0,1000000],
    'ventilation_price_grille' => ['ventilation.price_grille','Решётка, ₽',480,0,10000000],
    'ventilation_price_diffuser' => ['ventilation.price_diffuser','Диффузор, ₽',650,0,10000000],
    'ventilation_price_fan' => ['ventilation.price_fan','Вентилятор, ₽',18000,0,100000000],
    'ventilation_price_recovery' => ['ventilation.price_recovery','Рекуператор, ₽',85000,0,100000000],
    'ventilation_price_filter' => ['ventilation.price_filter','Фильтр, ₽',6500,0,10000000],
    'ventilation_price_silencer' => ['ventilation.price_silencer','Шумоглушитель, ₽',8500,0,10000000],
    'ventilation_price_valve' => ['ventilation.price_valve','Клапан, ₽',3200,0,10000000],
    'ventilation_price_cooling' => ['ventilation.price_cooling','Охлаждающий блок, ₽',45000,0,100000000],
    'ventilation_cooling_capacity_per_unit' => ['ventilation.cooling_capacity_per_unit','Мощность одного охлаждающего блока, кВт',8,0.1,1000],
    'ventilation_heat_capacity' => ['ventilation.heat_capacity','Тепловой коэффициент',0.335,0,10],
    'ventilation_price_materials_percent' => ['ventilation.price_materials_percent','Материалы, %',15,0,300],
    'ventilation_installation_percent' => ['ventilation.installation_percent','Монтаж оборудования, %',50,0,300],
    'ventilation_duct_installation_percent' => ['ventilation.duct_installation_percent','Монтаж воздуховодов, %',80,0,300],
    'ventilation_commissioning_percent' => ['ventilation.commissioning_percent','Пусконаладка, %',10,0,300],
    'ventilation_additional_percent' => ['ventilation.additional_percent','Дополнительные расходы, %',3,0,300],
    'ventilation_recovery_default' => ['ventilation.recovery_default','Эффективность рекуперации, %',70,0,100],
];
$tab = (string)($_GET['tab'] ?? 'dashboard');
if (!isset($tabs[$tab])) $tab = 'dashboard';
function slug_value(string $value): string {
    $map=['а'=>'a','б'=>'b','в'=>'v','г'=>'g','д'=>'d','е'=>'e','ё'=>'e','ж'=>'zh','з'=>'z','и'=>'i','й'=>'i','к'=>'k','л'=>'l','м'=>'m','н'=>'n','о'=>'o','п'=>'p','р'=>'r','с'=>'s','т'=>'t','у'=>'u','ф'=>'f','х'=>'h','ц'=>'c','ч'=>'ch','ш'=>'sh','щ'=>'sch','ъ'=>'','ы'=>'y','ь'=>'','э'=>'e','ю'=>'yu','я'=>'ya'];
    $ascii = function_exists('iconv') ? iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $value) : false;
    if ($ascii !== false) $value = strtolower($ascii);
    else $value = strtr(strtolower($value), $map);
    return trim(preg_replace('/[^a-z0-9]+/','-',$value) ?? '', '-') ?: 'page-'.bin2hex(random_bytes(3));
}
if ($_SERVER['REQUEST_METHOD']==='POST') {
    verify_csrf();
    $action=(string)($_POST['action']??'');
    if ($action==='login') {
        $attempt=$_SESSION['login_attempt']??['n'=>0,'time'=>time()];
        if (time()-(int)$attempt['time']>900) $attempt=['n'=>0,'time'=>time()];
        $q=db()->prepare('SELECT id,login,password_hash FROM admins WHERE login=? LIMIT 1'); $q->execute([trim((string)($_POST['login']??''))]); $admin=$q->fetch();
        if ((int)$attempt['n']>=8 || !$admin || !password_verify((string)($_POST['password']??''),$admin['password_hash'])) {
            $attempt['n']=(int)$attempt['n']+1; $attempt['time']=time(); $_SESSION['login_attempt']=$attempt;
            flash('Неверный логин или пароль. Проверьте реквизиты, заданные в установщике.','error'); redirect_to(site_path('admin/'));
        }
        session_regenerate_id(true); unset($_SESSION['login_attempt']); $_SESSION['admin_id']=(int)$admin['id']; redirect_to(site_path('admin/'));
    }
    if ($action==='logout') { unset($_SESSION['admin_id']); session_regenerate_id(true); redirect_to(site_path('admin/')); }
    if ($action==='change_credentials') {
        $current=admin_user();
        if (!$current) redirect_to(site_path('admin/'));
        $login=trim((string)($_POST['login']??'')); $old=(string)($_POST['current_password']??''); $new=(string)($_POST['new_password']??'');
        $q=db()->prepare('SELECT password_hash FROM admins WHERE id=?'); $q->execute([(int)$current['id']]); $hash=(string)$q->fetchColumn();
        if ($login==='' || strlen($login)>120 || !password_verify($old,$hash) || ($new!=='' && strlen($new)<10)) {
            flash('Проверьте логин, текущий пароль и длину нового пароля (не менее 10 символов).','error'); redirect_to(site_path('admin/?tab=settings'));
        }
        $q=db()->prepare('SELECT id FROM admins WHERE login=? AND id<>?'); $q->execute([$login,(int)$current['id']]);
        if ($q->fetchColumn()) { flash('Этот логин уже используется.','error'); redirect_to(site_path('admin/?tab=settings')); }
        if ($new==='') { $q=db()->prepare('UPDATE admins SET login=? WHERE id=?'); $q->execute([$login,(int)$current['id']]); }
        else { $q=db()->prepare('UPDATE admins SET login=?,password_hash=? WHERE id=?'); $q->execute([$login,password_hash($new,PASSWORD_DEFAULT),(int)$current['id']]); }
        flash('Данные администратора обновлены.'); redirect_to(site_path('admin/?tab=settings'));
    }
    $user=admin_user();
    if ($user && isset($_POST['save_record'])) {
        try {
        $id=(int)($_POST['id']??0);
        if ($tab==='categories') {
            $title=trim((string)($_POST['title']??'')); if ($title==='') throw new UserInputException('Введите название категории.');
            $code=slug_value((string)($_POST['code']?:$title)); $parent=null;
            $check=db()->prepare('SELECT id FROM categories WHERE code=? AND id<>?'); $check->execute([$code,$id]); if ($check->fetchColumn()) throw new UserInputException('Категория с таким адресным кодом уже существует.');
            if (!empty($_POST['parent_code'])) { $q=db()->prepare('SELECT id FROM categories WHERE code=?'); $q->execute([$_POST['parent_code']]); $parent=$q->fetchColumn()?:null; }
            $image=image_upload()??trim((string)($_POST['image_url']??'')); $vals=[$code,$title,$parent,$image,(int)($_POST['sort_order']??100),isset($_POST['active'])?1:0];
            if ($id) { $q=db()->prepare('UPDATE categories SET code=?,title=?,parent_id=?,image_url=?,sort_order=?,active=? WHERE id=?'); $q->execute([...$vals,$id]); } else { $q=db()->prepare('INSERT INTO categories (code,title,parent_id,image_url,sort_order,active) VALUES (?,?,?,?,?,?)'); $q->execute($vals); }
        } elseif ($tab==='brands') {
            $name=trim((string)($_POST['name']??'')); if ($name==='') throw new UserInputException('Введите название бренда.');
            $check=db()->prepare('SELECT id FROM brands WHERE name=? AND id<>?'); $check->execute([$name,$id]); if ($check->fetchColumn()) throw new UserInputException('Такой бренд уже добавлен.');
            $vals=[$name,image_upload()??trim((string)($_POST['logo_url']??'')),trim((string)($_POST['description']??'')),isset($_POST['active'])?1:0];
            if ($id) { $q=db()->prepare('UPDATE brands SET name=?,logo_url=?,description=?,active=? WHERE id=?'); $q->execute([...$vals,$id]); } else { $q=db()->prepare('INSERT INTO brands (name,logo_url,description,active) VALUES (?,?,?,?)'); $q->execute($vals); }
        } elseif ($tab==='products') {
            $model=trim((string)($_POST['model']??'')); if ($model==='') throw new UserInputException('Укажите модель товара.');
            $raw=trim((string)($_POST['specifications']??'')); $specs=$raw===''?[]:json_decode($raw,true); if (!is_array($specs)) throw new UserInputException('Характеристики должны быть корректным JSON-массивом.');
            $sku=trim((string)($_POST['sku']??''));
            if ($sku!=='') { $check=db()->prepare('SELECT id FROM products WHERE sku=? AND id<>?'); $check->execute([$sku,$id]); if ($check->fetchColumn()) throw new UserInputException('Товар с таким артикулом уже существует.'); }
            $vals=[$model,$sku===''?null:$sku,($_POST['brand_id']??'')!==''?(int)$_POST['brand_id']:null,($_POST['category_id']??'')!==''?(int)$_POST['category_id']:null,trim((string)($_POST['description']??'')),max(0,(float)($_POST['price']??0)),image_upload()??trim((string)($_POST['image_url']??'')),json_encode($specs,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),isset($_POST['is_demo'])?1:0,isset($_POST['active'])?1:0];
            if ($id) { $q=db()->prepare('UPDATE products SET model=?,sku=?,brand_id=?,category_id=?,description=?,price=?,image_url=?,specifications=?,is_demo=?,active=? WHERE id=?'); $q->execute([...$vals,$id]); } else { $q=db()->prepare('INSERT INTO products (model,sku,brand_id,category_id,description,price,image_url,specifications,is_demo,active,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,NOW())'); $q->execute($vals); }
        } elseif (in_array($tab,['news','pages'],true)) {
            $title=trim((string)($_POST['title']??'')); if ($title==='') throw new UserInputException('Введите заголовок.');
            $slug=slug_value((string)($_POST['slug']?:$title)); $content=safe_html((string)($_POST['content']??'')); $published=isset($_POST['published'])?1:0;
            $tableName=$tab==='news'?'news':'pages'; $check=db()->prepare('SELECT id FROM '.$tableName.' WHERE slug=? AND id<>?'); $check->execute([$slug,$id]); if ($check->fetchColumn()) throw new UserInputException('Адрес страницы уже занят. Укажите другой slug.');
            if ($tab==='news') {
                $image=image_upload()??trim((string)($_POST['image_url']??'')); $excerpt=trim((string)($_POST['excerpt']??''));
                if ($id) { $q=db()->prepare('UPDATE news SET title=?,slug=?,excerpt=?,content=?,image_url=?,published=?,published_at=IF(?=1,COALESCE(published_at,NOW()),NULL) WHERE id=?'); $q->execute([$title,$slug,$excerpt,$content,$image,$published,$published,$id]); }
                else { $q=db()->prepare('INSERT INTO news (title,slug,excerpt,content,image_url,published,created_at,published_at) VALUES (?,?,?,?,?,?,NOW(),IF(?=1,NOW(),NULL))'); $q->execute([$title,$slug,$excerpt,$content,$image,$published,$published]); }
            } else {
                if ($id) { $q=db()->prepare('UPDATE pages SET title=?,slug=?,content=?,published=?,updated_at=NOW() WHERE id=?'); $q->execute([$title,$slug,$content,$published,$id]); }
                else { $q=db()->prepare('INSERT INTO pages (title,slug,content,published,updated_at) VALUES (?,?,?,?,NOW())'); $q->execute([$title,$slug,$content,$published]); }
            }
        } elseif ($tab==='gallery') {
            $title=trim((string)($_POST['title']??'')); $image=image_upload()??trim((string)($_POST['image_url']??'')); if ($title===''||$image==='') throw new UserInputException('Укажите название и изображение.');
            $vals=[$title,trim((string)($_POST['alt_text']??'')),$image,trim((string)($_POST['location']??'')),(int)($_POST['sort_order']??100),isset($_POST['published'])?1:0];
            if ($id) { $q=db()->prepare('UPDATE gallery SET title=?,alt_text=?,image_url=?,location=?,sort_order=?,published=? WHERE id=?'); $q->execute([...$vals,$id]); } else { $q=db()->prepare('INSERT INTO gallery (title,alt_text,image_url,location,sort_order,published) VALUES (?,?,?,?,?,?)'); $q->execute($vals); }
        } elseif ($tab==='settings') {
            $q=db()->prepare('INSERT INTO settings (setting_key,setting_value) VALUES (?,?) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)');
            if (array_intersect(['site_title','site_tagline','phone','email','address'], array_keys($_POST))) {
                foreach (['site_title','site_tagline','phone','email','address'] as $key) {
                    if (array_key_exists($key, $_POST)) $q->execute([$key,trim((string)$_POST[$key])]);
                }
            }
            foreach ($ventilationSettingFields as $field => [$key, $label, $default, $minimum, $maximum]) {
                if (!array_key_exists($field, $_POST)) continue;
                $raw = trim((string)$_POST[$field]);
                $normalised = str_replace(',', '.', $raw);
                if ($normalised === '' || !is_numeric($normalised) || !is_finite((float)$normalised) || (float)$normalised < $minimum || (float)$normalised > $maximum) {
                    throw new UserInputException('Проверьте настройку «' . $label . '»: допустимо от ' . $minimum . ' до ' . $maximum . '.');
                }
                $q->execute([$key, $normalised]);
            }
        } elseif ($tab==='leads') {
            $status=(string)($_POST['status']??'new'); if (!in_array($status,['new','in_progress','done'],true)) $status='new';
            $q=db()->prepare('UPDATE leads SET status=? WHERE id=?'); $q->execute([$status,$id]);
        }
        flash('Изменения сохранены.'); redirect_to(site_path('admin/?tab='.$tab));
        } catch (UserInputException $exception) {
            flash($exception->getMessage(), 'error');
            $return = !empty($_GET['edit']) ? '&edit=' . (int)$_GET['edit'] : '&new=1';
            redirect_to(site_path('admin/?tab=' . rawurlencode($tab) . $return));
        }
    }
    if ($user && isset($_POST['delete_record'])) {
        $tables=['categories'=>'categories','brands'=>'brands','products'=>'products','news'=>'news','pages'=>'pages','gallery'=>'gallery'];
        if (isset($tables[$tab])) { $q=db()->prepare('DELETE FROM '.$tables[$tab].' WHERE id=?'); $q->execute([(int)$_POST['id']]); }
        flash('Запись удалена.'); redirect_to(site_path('admin/?tab='.$tab));
    }
}
$user=admin_user();
if (!$user) {
    $message=take_flash(); ?>
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход · <?= e(setting('site_title','ЭКО-КЛИМАТ')) ?></title><link rel="stylesheet" href="<?= e(site_path('assets/style.css')) ?>"></head><body class="admin-login-body"><main class="login-card"><a class="brand" href="<?= e(site_path()) ?>"><span class="brand-mark">ЭК</span><span><?= e(setting('site_title','ЭКО-КЛИМАТ')) ?><small>ПАНЕЛЬ УПРАВЛЕНИЯ</small></span></a><p class="eyebrow">УПРАВЛЕНИЕ САЙТОМ</p><h1>Вход в админ-панель</h1><?php if ($message): ?><div class="notice error"><?= e($message['message']) ?></div><?php endif; ?><form method="post"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="action" value="login"><label>Логин<input name="login" autocomplete="username" required autofocus></label><label>Пароль<input type="password" name="password" autocomplete="current-password" required></label><button class="button login-submit">Войти ↗</button></form><a class="login-back" href="<?= e(site_path()) ?>">← На сайт</a></main></body></html><?php exit;
}
$counts=[]; foreach (['categories','brands','products','news','pages','gallery','leads','formulas'] as $t) $counts[$t]=(int)db()->query('SELECT COUNT(*) FROM '.$t)->fetchColumn();
$flashMessage=take_flash(); $edit=null;
if (!empty($_GET['edit']) && in_array($tab,['categories','brands','products','news','pages','gallery'],true)) { $q=db()->prepare('SELECT * FROM '.$tab.' WHERE id=?'); $q->execute([(int)$_GET['edit']]); $edit=$q->fetch()?:null; }
function admin_delete_control(int $id): void {
    echo '<form class="inline-delete" method="post" onsubmit="return confirm(\'Удалить эту запись?\')"><input type="hidden" name="_csrf" value="' . e(csrf_token()) . '"><input type="hidden" name="delete_record" value="1"><input type="hidden" name="id" value="' . $id . '"><button>Удалить</button></form>';
}
?>
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title><?= e($tabs[$tab]) ?> · Управление сайтом</title><link rel="stylesheet" href="<?= e(site_path('assets/style.css')) ?>"></head><body class="admin-body">
<header class="admin-topbar"><a class="brand" href="<?= e(site_path()) ?>"><span class="brand-mark">ЭК</span><span><?= e(setting('site_title','ЭКО-КЛИМАТ')) ?><small>УПРАВЛЕНИЕ САЙТОМ</small></span></a><div class="admin-top-actions"><a class="button button-small button-ghost" href="<?= e(site_path()) ?>" target="_blank">Открыть сайт ↗</a><span><?= e($user['login']) ?></span><form method="post"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="action" value="logout"><button class="logout-button">Выйти</button></form></div></header>
<div class="admin-shell"><aside class="admin-sidebar"><div class="admin-sidebar-label">РАЗДЕЛЫ САЙТА</div><?php foreach ($tabs as $key=>$label): ?><a class="admin-nav <?= $tab===$key?'active':'' ?>" href="<?= e(site_path('admin/?tab='.$key)) ?>"><span><?= e($label) ?></span><?php if (isset($counts[$key])): ?><small><?= $counts[$key] ?></small><?php endif; ?></a><?php endforeach; ?><div class="admin-sidebar-bottom">PHP CMS · <?= date('Y') ?></div></aside><main class="admin-main">
<?php if ($flashMessage): ?><div class="notice <?= e($flashMessage['kind']) ?>"><?= e($flashMessage['message']) ?></div><?php endif; ?><div class="admin-page-heading"><div><p class="eyebrow">ПАНЕЛЬ УПРАВЛЕНИЯ / <?= e(strtoupper($tab)) ?></p><h1><?= e($tabs[$tab]) ?></h1></div><?php if (in_array($tab,['categories','brands','products','news','pages','gallery'],true)): ?><a class="button button-small" href="<?= e(site_path('admin/?tab='.$tab.'&new=1')) ?>">＋ Добавить</a><?php endif; ?></div>
<?php if ($tab==='dashboard'): ?><div class="stats-grid"><?php foreach (['categories'=>'Категорий','brands'=>'Брендов','products'=>'Товаров','news'=>'Публикаций','gallery'=>'Фотографий','leads'=>'Заявок'] as $key=>$label): ?><a class="stat-card" href="<?= e(site_path('admin/?tab='.$key)) ?>"><span><?= e($label) ?></span><strong><?= $counts[$key] ?></strong><i>Открыть ↗</i></a><?php endforeach; ?></div><section class="admin-panel welcome-panel"><p class="eyebrow">ВАШ САЙТ УСТАНОВЛЕН</p><h2>Добавьте своё оборудование и проекты</h2><p>Заполните контакты, замените тестовые карточки и загрузите фотографии работ. Демо-товары помечены и не предназначены для продажи.</p><div class="quick-links"><a href="<?= e(site_path('admin/?tab=settings')) ?>">Настройки сайта ↗</a><a href="<?= e(site_path('admin/?tab=products&new=1')) ?>">Добавить товар ↗</a><a href="<?= e(site_path('admin/?tab=gallery&new=1')) ?>">Добавить работу ↗</a></div></section>
<?php elseif ($tab==='settings'): ?><section class="admin-panel"><form method="post"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="save_record" value="1"><div class="form-grid"><label>Название сайта<input name="site_title" value="<?= e(setting('site_title')) ?>"></label><label>Телефон<input name="phone" value="<?= e(setting('phone')) ?>"></label><label>Электронная почта<input name="email" value="<?= e(setting('email')) ?>"></label><label>Адрес<input name="address" value="<?= e(setting('address')) ?>"></label><label class="span-2">Краткое описание<textarea name="site_tagline" rows="3"><?= e(setting('site_tagline')) ?></textarea></label></div><button class="button">Сохранить настройки сайта</button></form></section><section class="admin-panel"><p class="eyebrow">ENGINEERING / VENTILATION</p><h2>Настройки калькулятора вентиляции</h2><p class="muted">Тарифы и коэффициенты используются только независимым калькулятором вентиляции. Они не изменяют расчёт кондиционирования или другие инструменты.</p><form method="post"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="save_record" value="1"><div class="form-grid"><?php foreach ($ventilationSettingFields as $field => [$key,$label,$default,$minimum,$maximum]): ?><label><?= e($label) ?><input type="number" name="<?= e($field) ?>" min="<?= e($minimum) ?>" max="<?= e($maximum) ?>" step="any" required value="<?= e(setting($key,(string)$default)) ?>"></label><?php endforeach; ?></div><button class="button">Сохранить тарифы вентиляции</button></form></section><section class="admin-panel account-panel"><p class="eyebrow">УЧЁТНАЯ ЗАПИСЬ</p><h2>Логин и пароль администратора</h2><form method="post"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="action" value="change_credentials"><div class="form-grid"><label>Новый логин<input name="login" maxlength="120" required value="<?= e($user['login']) ?>"></label><label>Текущий пароль<input name="current_password" type="password" autocomplete="current-password" required></label><label class="span-2">Новый пароль<input name="new_password" type="password" minlength="10" autocomplete="new-password"><small>Оставьте пустым, если меняете только логин. Новый пароль — не менее 10 символов.</small></label></div><button class="button">Обновить данные администратора</button></form></section>
<?php elseif (in_array($tab,['categories','brands','products','news','pages','gallery'],true) && (!empty($_GET['new'])||$edit)): $f=$edit?:[]; ?><section class="admin-panel edit-panel"><div class="panel-heading"><h2><?= $edit?'Редактировать':'Создать' ?> запись</h2><a href="<?= e(site_path('admin/?tab='.$tab)) ?>">Закрыть ×</a></div><form method="post" enctype="multipart/form-data"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="save_record" value="1"><input type="hidden" name="id" value="<?= (int)($f['id']??0) ?>">
<?php if ($tab==='categories'): ?><div class="form-grid"><label>Название<input name="title" required value="<?= e($f['title']??'') ?>"></label><label>Код / адрес<input name="code" value="<?= e($f['code']??'') ?>" placeholder="создастся автоматически"></label><label>Родительская категория<select name="parent_code"><option value="">Верхний уровень</option><?php foreach (db()->query('SELECT id,code,title FROM categories ORDER BY title') as $c): if ((int)$c['id']===(int)($f['id']??0)) continue; ?><option value="<?= e($c['code']) ?>" <?= (int)($f['parent_id']??0)===(int)$c['id']?'selected':'' ?>><?= e($c['title']) ?></option><?php endforeach; ?></select></label><label>Порядок<input type="number" name="sort_order" value="<?= e($f['sort_order']??100) ?>"></label><label class="span-2">Изображение<input type="file" name="image" accept="image/jpeg,image/png,image/webp"><input class="secondary-input" name="image_url" value="<?= e($f['image_url']??'') ?>" placeholder="или URL изображения"></label></div><label class="check-label"><input type="checkbox" name="active" <?= !isset($f['active'])||$f['active']?'checked':'' ?>> Показывать</label>
<?php elseif ($tab==='brands'): ?><div class="form-grid"><label>Название<input name="name" required value="<?= e($f['name']??'') ?>"></label><label>Логотип<input type="file" name="image" accept="image/jpeg,image/png,image/webp"><input class="secondary-input" name="logo_url" value="<?= e($f['logo_url']??'') ?>" placeholder="или URL логотипа"></label><label class="span-2">Описание<textarea name="description"><?= e($f['description']??'') ?></textarea></label></div><label class="check-label"><input type="checkbox" name="active" <?= !isset($f['active'])||$f['active']?'checked':'' ?>> Активный бренд</label>
<?php elseif ($tab==='products'): ?><div class="form-grid"><label>Модель<input name="model" required value="<?= e($f['model']??'') ?>"></label><label>Артикул<input name="sku" value="<?= e($f['sku']??'') ?>"></label><label>Бренд<select name="brand_id"><option value="">Не выбран</option><?php foreach (db()->query('SELECT id,name FROM brands ORDER BY name') as $b): ?><option value="<?= (int)$b['id'] ?>" <?= (int)($f['brand_id']??0)===(int)$b['id']?'selected':'' ?>><?= e($b['name']) ?></option><?php endforeach; ?></select></label><label>Категория<select name="category_id"><option value="">Не выбрана</option><?php foreach (db()->query('SELECT id,title FROM categories ORDER BY title') as $c): ?><option value="<?= (int)$c['id'] ?>" <?= (int)($f['category_id']??0)===(int)$c['id']?'selected':'' ?>><?= e($c['title']) ?></option><?php endforeach; ?></select></label><label>Цена, ₽<input type="number" name="price" min="0" step="0.01" value="<?= e($f['price']??0) ?>"></label><label>Фото<input type="file" name="image" accept="image/jpeg,image/png,image/webp"><input class="secondary-input" name="image_url" value="<?= e($f['image_url']??'') ?>" placeholder="или внешний URL"></label><label class="span-2">Описание<textarea name="description" rows="4"><?= e($f['description']??'') ?></textarea></label><label class="span-2">Характеристики (JSON)<textarea name="specifications" rows="4"><?= e($f['specifications']??'[]') ?></textarea></label></div><label class="check-label"><input type="checkbox" name="is_demo" <?= !empty($f['is_demo'])?'checked':'' ?>> Демонстрационный товар</label><label class="check-label"><input type="checkbox" name="active" <?= !isset($f['active'])||$f['active']?'checked':'' ?>> Показывать на сайте</label>
<?php elseif ($tab==='news'||$tab==='pages'): ?><div class="form-grid"><label class="span-2">Заголовок<input name="title" required value="<?= e($f['title']??'') ?>"></label><label>Адрес страницы<input name="slug" value="<?= e($f['slug']??'') ?>" placeholder="создастся автоматически"></label><?php if ($tab==='news'): ?><label>Обложка<input type="file" name="image" accept="image/jpeg,image/png,image/webp"><input class="secondary-input" name="image_url" value="<?= e($f['image_url']??'') ?>" placeholder="или URL обложки"></label><label class="span-2">Анонс<textarea name="excerpt" rows="3"><?= e($f['excerpt']??'') ?></textarea></label><?php endif; ?><label class="span-2">Содержание (разрешена базовая HTML-разметка)<textarea class="content-editor" name="content" rows="15"><?= e($f['content']??'') ?></textarea><small>Заголовки, абзацы, списки, ссылки и таблицы. Скрипты и HTML-атрибуты удаляются при сохранении.</small></label></div><label class="check-label"><input type="checkbox" name="published" <?= !isset($f['published'])||$f['published']?'checked':'' ?>> Опубликовать</label>
<?php else: ?><div class="form-grid"><label class="span-2">Название работы<input name="title" required value="<?= e($f['title']??'') ?>"></label><label>Локация<input name="location" value="<?= e($f['location']??'') ?>"></label><label>Порядок<input type="number" name="sort_order" value="<?= e($f['sort_order']??100) ?>"></label><label class="span-2">Фотография<input type="file" name="image" accept="image/jpeg,image/png,image/webp"><input class="secondary-input" name="image_url" value="<?= e($f['image_url']??'') ?>" placeholder="или URL фото"></label><label class="span-2">Alt-текст<input name="alt_text" value="<?= e($f['alt_text']??'') ?>"></label></div><label class="check-label"><input type="checkbox" name="published" <?= !isset($f['published'])||$f['published']?'checked':'' ?>> Показывать на сайте</label><?php endif; ?><div class="form-actions"><button class="button">Сохранить</button><a class="button button-ghost" href="<?= e(site_path('admin/?tab='.$tab)) ?>">Отмена</a></div></form></section>
<?php elseif ($tab==='categories'): $rows=db()->query('SELECT c.*,p.title parent_title FROM categories c LEFT JOIN categories p ON p.id=c.parent_id ORDER BY c.sort_order,c.title')->fetchAll(); ?><div class="admin-panel table-panel"><table><thead><tr><th>Категория</th><th>Родитель</th><th>Код</th><th>Статус</th><th></th></tr></thead><tbody><?php foreach($rows as $r): ?><tr><td><?= e($r['title']) ?></td><td><?= e($r['parent_title']??'Верхний уровень') ?></td><td><?= e($r['code']) ?></td><td><?= $r['active']?'Активна':'Скрыта' ?></td><td><a href="<?= e(site_path('admin/?tab=categories&edit='.$r['id'])) ?>">Изменить</a><?php admin_delete_control((int)$r['id']); ?></td></tr><?php endforeach; ?></tbody></table></div>
<?php elseif ($tab==='brands'): $rows=db()->query('SELECT * FROM brands ORDER BY name')->fetchAll(); ?><div class="admin-panel table-panel"><table><thead><tr><th>Бренд</th><th>Описание</th><th></th></tr></thead><tbody><?php foreach($rows as $r): ?><tr><td><?= e($r['name']) ?></td><td><?= e($r['description']) ?></td><td><a href="<?= e(site_path('admin/?tab=brands&edit='.$r['id'])) ?>">Изменить</a><?php admin_delete_control((int)$r['id']); ?></td></tr><?php endforeach; ?></tbody></table></div>
<?php elseif ($tab==='products'): $rows=db()->query('SELECT p.*,b.name brand_name,c.title category_title FROM products p LEFT JOIN brands b ON b.id=p.brand_id LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.id DESC LIMIT 500')->fetchAll(); ?><div class="admin-panel table-panel"><table><thead><tr><th>Товар</th><th>Бренд / категория</th><th>Цена</th><th></th></tr></thead><tbody><?php foreach($rows as $r): ?><tr><td><?= e($r['model']) ?><?= $r['is_demo']?'<small class="demo-label"> · ДЕМО</small>':'' ?><small><?= e($r['sku']) ?></small></td><td><?= e($r['brand_name']??'—') ?><small><?= e($r['category_title']??'—') ?></small></td><td><?= number_format((float)$r['price'],0,',',' ') ?> ₽</td><td><a href="<?= e(site_path('admin/?tab=products&edit='.$r['id'])) ?>">Изменить</a><?php admin_delete_control((int)$r['id']); ?></td></tr><?php endforeach; ?></tbody></table></div>
<?php elseif ($tab==='news'||$tab==='pages'): $table=$tab==='news'?'news':'pages'; $rows=db()->query('SELECT * FROM '.$table.' ORDER BY id DESC')->fetchAll(); ?><div class="admin-panel table-panel"><table><thead><tr><th>Материал</th><th>Адрес</th><th>Статус</th><th></th></tr></thead><tbody><?php foreach($rows as $r): ?><tr><td><?= e($r['title']) ?><small><?= e($r['excerpt']??'') ?></small></td><td><?= e($r['slug']) ?></td><td><?= $r['published']?'Опубликован':'Черновик' ?></td><td><a href="<?= e(site_path('admin/?tab='.$tab.'&edit='.$r['id'])) ?>">Изменить</a><?php admin_delete_control((int)$r['id']); ?></td></tr><?php endforeach; ?></tbody></table></div>
<?php elseif ($tab==='gallery'): $rows=db()->query('SELECT * FROM gallery ORDER BY sort_order,id DESC')->fetchAll(); ?><div class="admin-panel table-panel"><table><thead><tr><th>Работа</th><th>Место</th><th>Статус</th><th></th></tr></thead><tbody><?php foreach($rows as $r): ?><tr><td><?= e($r['title']) ?></td><td><?= e($r['location']) ?></td><td><?= $r['published']?'Опубликована':'Скрыта' ?></td><td><a href="<?= e(site_path('admin/?tab=gallery&edit='.$r['id'])) ?>">Изменить</a><?php admin_delete_control((int)$r['id']); ?></td></tr><?php endforeach; ?></tbody></table></div>
<?php elseif ($tab==='leads'): $rows=db()->query('SELECT * FROM leads ORDER BY created_at DESC LIMIT 500')->fetchAll(); ?><div class="admin-panel table-panel"><table><thead><tr><th>Имя и дата</th><th>Контакты</th><th>Сообщение</th><th>Статус</th></tr></thead><tbody><?php foreach($rows as $r): ?><tr><td><?= e($r['name']) ?><small><?= e($r['created_at']) ?></small></td><td><?= e($r['phone']) ?><small><?= e($r['email']) ?></small></td><td><?= e($r['message']) ?></td><td><form method="post" class="inline-status"><input type="hidden" name="_csrf" value="<?= e(csrf_token()) ?>"><input type="hidden" name="save_record" value="1"><input type="hidden" name="id" value="<?= (int)$r['id'] ?>"><select name="status"><option value="new" <?= $r['status']==='new'?'selected':'' ?>>Новая</option><option value="in_progress" <?= $r['status']==='in_progress'?'selected':'' ?>>В работе</option><option value="done" <?= $r['status']==='done'?'selected':'' ?>>Завершена</option></select><button class="mini-button">OK</button></form></td></tr><?php endforeach; ?></tbody></table></div>
<?php elseif ($tab==='formulas'): ?><div class="formula-list"><?php foreach(db()->query('SELECT * FROM formulas ORDER BY module,title') as $r): ?><details class="admin-panel formula-item"><summary><?= e($r['title']) ?> <small><?= e($r['module']) ?></small></summary><p class="code-cell"><?= e($r['expression']) ?></p></details><?php endforeach; ?></div><div class="notice">Это исходные расчётные формулы из пакета. Публичный предварительный калькулятор упрощён и служит только для ориентировочной оценки.</div>
<?php endif; ?></main></div><script src="<?= e(site_path('assets/app.js')) ?>" defer></script></body></html>
