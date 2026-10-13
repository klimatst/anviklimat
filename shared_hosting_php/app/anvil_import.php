<?php
declare(strict_types=1);

const KLIMA_ANVIL_EXPORT_FORMAT = 'klimaeco-anvil-export';
const KLIMA_ANVIL_EXPORT_MAX_COMPRESSED = 20 * 1024 * 1024;
const KLIMA_ANVIL_EXPORT_MAX_JSON = 40 * 1024 * 1024;
const KLIMA_ANVIL_EXPORT_MAX_ROWS = 20000;

const KLIMA_ANVIL_EXPORT_TABLES = [
    'ai_providers', 'ai_usage', 'audit_logs', 'bom', 'brands', 'calculations',
    'catalog_categories', 'catalog_documents', 'catalog_orders', 'catalog_series',
    'cms_modules', 'cms_pages', 'compatibility', 'crm_clients', 'crm_contacts',
    'crm_tasks', 'estimate_lines', 'estimates', 'files', 'formulas', 'gallery_items',
    'imports', 'import_logs', 'media_objects', 'objects', 'pdf_draft_items',
    'pdf_draft_pages', 'product_media', 'product_prices', 'product_sources', 'product_specs',
    'product_stock', 'products', 'projects', 'quotes', 'roles', 'rooms', 'service',
    'system_components', 'system_connections', 'system_settings', 'systems', 'users',
    'xlsx_upload_chunks'
];

/** Create tables that retain the source Anvil records without lossy SQL mapping. */
function ensure_anvil_export_schema(PDO $pdo): void
{
    $pdo->exec("CREATE TABLE IF NOT EXISTS anvil_export_rows (
        source_table VARCHAR(80) NOT NULL,
        source_id VARCHAR(190) NOT NULL,
        record_json LONGTEXT NOT NULL,
        imported_at DATETIME NOT NULL,
        PRIMARY KEY (source_table, source_id),
        INDEX idx_anvil_export_table (source_table, imported_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS anvil_export_imports (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        source_export_at VARCHAR(40) NOT NULL DEFAULT '',
        checksum CHAR(64) NOT NULL UNIQUE,
        table_count INT UNSIGNED NOT NULL,
        row_count INT UNSIGNED NOT NULL,
        imported_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
}

function anvil_export_canonicalize(mixed $value): mixed
{
    if ($value instanceof stdClass) {
        $properties = get_object_vars($value);
        ksort($properties, SORT_STRING);
        $normalized = new stdClass();
        foreach ($properties as $key => $item) {
            $normalized->{$key} = anvil_export_canonicalize($item);
        }
        return $normalized;
    }
    if (is_array($value)) {
        return array_map('anvil_export_canonicalize', $value);
    }
    return $value;
}

function anvil_export_canonical_json(mixed $value): string
{
    return json_encode(
        anvil_export_canonicalize($value),
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_LINE_TERMINATORS
            | JSON_PRESERVE_ZERO_FRACTION | JSON_THROW_ON_ERROR
    );
}

function anvil_export_collect_ids(stdClass $tables): array
{
    $ids = [];
    foreach (get_object_vars($tables) as $tableName => $records) {
        if (!is_array($records)) {
            throw new RuntimeException('В экспорте повреждён список таблицы ' . $tableName . '.');
        }
        $ids[$tableName] = [];
        foreach ($records as $record) {
            if (!$record instanceof stdClass || !isset($record->id) || !is_string($record->id) || $record->id === '') {
                throw new RuntimeException('В таблице ' . $tableName . ' найден некорректный ID.');
            }
            if (isset($ids[$tableName][$record->id])) {
                throw new RuntimeException('В таблице ' . $tableName . ' повторяется ID строки.');
            }
            if (!isset($record->values) || !$record->values instanceof stdClass) {
                throw new RuntimeException('В таблице ' . $tableName . ' повреждены значения строки.');
            }
            $ids[$tableName][$record->id] = true;
        }
    }
    return $ids;
}

function anvil_export_validate_refs(mixed $value, array $ids): void
{
    if ($value instanceof stdClass) {
        if (($value->{'$type'} ?? null) === 'ref') {
            $table = $value->table ?? null;
            $id = $value->id ?? null;
            if (!is_string($table) || !isset($ids[$table]) || !is_string($id) || !isset($ids[$table][$id])) {
                throw new RuntimeException('В экспорте обнаружена ссылка на отсутствующую строку.');
            }
            return;
        }
        foreach (get_object_vars($value) as $item) {
            anvil_export_validate_refs($item, $ids);
        }
    } elseif (is_array($value)) {
        foreach ($value as $item) {
            anvil_export_validate_refs($item, $ids);
        }
    }
}

function anvil_export_decode_value(mixed $value): mixed
{
    if (!$value instanceof stdClass) {
        if (is_array($value)) {
            return array_map('anvil_export_decode_value', $value);
        }
        return $value;
    }
    $kind = $value->{'$type'} ?? null;
    if ($kind === 'object' && ($value->value ?? null) instanceof stdClass) {
        $decoded = new stdClass();
        foreach (get_object_vars($value->value) as $key => $item) {
            $decoded->{$key} = anvil_export_decode_value($item);
        }
        return $decoded;
    }
    if ($kind === 'list' && is_array($value->value ?? null)) {
        return array_map('anvil_export_decode_value', $value->value);
    }
    if ($kind === 'ref') {
        return (object)['table' => $value->table ?? '', 'id' => $value->id ?? ''];
    }
    if (in_array($kind, ['date', 'datetime'], true)) {
        return is_string($value->value ?? null) ? $value->value : '';
    }
    return $value;
}

function anvil_export_ref_id(mixed $value, string $table): ?string
{
    return $value instanceof stdClass
        && ($value->table ?? null) === $table
        && is_string($value->id ?? null)
        ? $value->id
        : null;
}

function anvil_export_rows(stdClass $tables, string $tableName): array
{
    return $tables->{$tableName} ?? [];
}

function anvil_export_row_values(stdClass $record): stdClass
{
    $values = anvil_export_decode_value($record->values);
    return $values instanceof stdClass ? $values : new stdClass();
}

function anvil_export_public_url(mixed $value): string
{
    if (!is_string($value)) {
        return '';
    }
    $value = trim($value);
    if (preg_match('~^https?://~i', $value) && filter_var($value, FILTER_VALIDATE_URL)) {
        return $value;
    }
    if (preg_match('~^(?:assets|storage/uploads)/[A-Za-z0-9._/-]+$~D', $value)
        && !str_contains($value, '..')
    ) {
        return $value;
    }
    return '';
}

function anvil_export_save_image(mixed $value, string $root): string
{
    if (!$value instanceof stdClass || ($value->{'$type'} ?? null) !== 'media') {
        return '';
    }
    $mime = strtolower((string)($value->content_type ?? ''));
    $extensions = ['image/jpeg' => 'jpg', 'image/png' => 'png', 'image/webp' => 'webp'];
    if (!isset($extensions[$mime]) || !is_string($value->data ?? null)) {
        return '';
    }
    $bytes = base64_decode($value->data, true);
    if (!is_string($bytes) || $bytes === '' || strlen($bytes) > 20 * 1024 * 1024) {
        return '';
    }
    $directory = $root . '/storage/uploads';
    if (!is_dir($directory) && !mkdir($directory, 0750, true) && !is_dir($directory)) {
        throw new RuntimeException('Не удалось создать storage/uploads.');
    }
    $name = 'anvil-' . hash('sha256', $bytes) . '.' . $extensions[$mime];
    $target = $directory . '/' . $name;
    if (!is_file($target)) {
        $temporary = $target . '.tmp-' . bin2hex(random_bytes(4));
        if (file_put_contents($temporary, $bytes, LOCK_EX) !== strlen($bytes) || !rename($temporary, $target)) {
            if (is_file($temporary)) {
                @unlink($temporary);
            }
            throw new RuntimeException('Не удалось сохранить импортированное фото.');
        }
        @chmod($target, 0640);
    }
    return 'storage/uploads/' . $name;
}

function anvil_export_render_modules(array $modules, string $pageId, string $root): array
{
    $parts = [];
    $image = '';
    foreach ($modules as $module) {
        if (!$module instanceof stdClass) {
            continue;
        }
        $values = anvil_export_row_values($module);
        if (!anvil_export_ref_id($values->page ?? null, 'cms_pages') === $pageId) {
            continue;
        }
        if (($values->enabled ?? false) !== true) {
            continue;
        }
        $content = $values->content ?? new stdClass();
        if (!$content instanceof stdClass) {
            continue;
        }
        $code = is_string($values->code ?? null) ? $values->code : 'text';
        $title = trim((string)($content->title ?? $content->label ?? ''));
        $text = trim((string)($content->text ?? ''));
        $html = is_string($content->html ?? null) ? trim($content->html) : '';
        $imageUrl = anvil_export_public_url($content->image_url ?? '');
        if ($imageUrl === '') {
            $imageUrl = anvil_export_save_image($content->image ?? null, $root);
        }
        if ($image === '' && $imageUrl !== '') {
            $image = $imageUrl;
        }
        $url = anvil_export_public_url($content->url ?? '');
        $escape = static fn(string $value): string => htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
        if ($code === 'html' && $html !== '') {
            $parts[] = $html;
        } elseif ($code === 'image' && $imageUrl !== '') {
            $parts[] = '<p><img src="' . $escape($imageUrl) . '" alt="' . $escape((string)($content->image_alt ?? $title)) . '"></p>';
        } elseif (in_array($code, ['link', 'button', 'media_reference'], true) && $url !== '') {
            $parts[] = '<p><a href="' . $escape($url) . '">' . $escape((string)($content->link_label ?? $title ?: $url)) . '</a></p>';
        } else {
            $section = '';
            if ($title !== '') {
                $section .= '<h2>' . $escape($title) . '</h2>';
            }
            if ($text !== '') {
                $section .= '<p>' . nl2br($escape($text), false) . '</p>';
            }
            if ($section !== '') {
                $parts[] = $section;
            }
        }
    }
    return [implode("\n", $parts), $image];
}

/** Populate the PHP site's editable public tables from Anvil's catalog and CMS. */
function anvil_export_map_public_data(PDO $pdo, stdClass $tables, string $root): array
{
    $categoryCodes = [];
    $categoryIds = [];
    $categoryInsert = $pdo->prepare(
        'INSERT INTO categories (code,title,parent_id,image_url,sort_order,active) VALUES (?,?,NULL,?,?,?) '
        . 'ON DUPLICATE KEY UPDATE title=VALUES(title), image_url=IF(VALUES(image_url)=\'\',image_url,VALUES(image_url)), sort_order=VALUES(sort_order), active=VALUES(active)'
    );
    foreach (anvil_export_rows($tables, 'catalog_categories') as $record) {
        $values = anvil_export_row_values($record);
        $code = trim((string)($values->code ?? ''));
        $title = trim((string)($values->title ?? ''));
        if ($code === '' || $title === '') {
            continue;
        }
        $image = anvil_export_save_image($values->image ?? null, $root);
        $categoryInsert->execute([$code, $title, $image, (int)($values->sort_order ?? 100), !empty($values->active) ? 1 : 0]);
        $find = $pdo->prepare('SELECT id FROM categories WHERE code=?');
        $find->execute([$code]);
        $localId = (int)$find->fetchColumn();
        $categoryCodes[$record->id] = $code;
        $categoryIds[$record->id] = $localId;
    }
    $parentUpdate = $pdo->prepare('UPDATE categories SET parent_id=? WHERE id=?');
    foreach (anvil_export_rows($tables, 'catalog_categories') as $record) {
        $values = anvil_export_row_values($record);
        $parentSourceId = anvil_export_ref_id($values->parent ?? null, 'catalog_categories');
        if ($parentSourceId !== null && isset($categoryIds[$record->id], $categoryIds[$parentSourceId])) {
            $parentUpdate->execute([$categoryIds[$parentSourceId], $categoryIds[$record->id]]);
        }
    }

    $brandIds = [];
    $brandInsert = $pdo->prepare("INSERT INTO brands (name,logo_url,description,active) VALUES (?,'','',1) ON DUPLICATE KEY UPDATE name=VALUES(name)");
    foreach (anvil_export_rows($tables, 'brands') as $record) {
        $values = anvil_export_row_values($record);
        $name = trim((string)($values->name ?? ''));
        if ($name === '') {
            continue;
        }
        $brandInsert->execute([$name]);
        $find = $pdo->prepare('SELECT id FROM brands WHERE name=?');
        $find->execute([$name]);
        $brandIds[$record->id] = (int)$find->fetchColumn();
    }

    $prices = [];
    foreach (anvil_export_rows($tables, 'product_prices') as $record) {
        $values = anvil_export_row_values($record);
        $productId = anvil_export_ref_id($values->product ?? null, 'products');
        if ($productId === null) {
            continue;
        }
        $prices[$productId] = (float)($values->special_price ?? 0) ?: (float)($values->sale_price ?? 0) ?: (float)($values->purchase_price ?? 0);
    }
    $specs = [];
    foreach (anvil_export_rows($tables, 'product_specs') as $record) {
        $values = anvil_export_row_values($record);
        $productId = anvil_export_ref_id($values->product ?? null, 'products');
        if ($productId === null || ($values->visible ?? true) === false) {
            continue;
        }
        $specs[$productId][] = [
            trim((string)($values->key ?? '')),
            trim((string)($values->value ?? '')),
            trim((string)($values->unit ?? '')),
        ];
    }
    $media = [];
    foreach (anvil_export_rows($tables, 'product_media') as $record) {
        $values = anvil_export_row_values($record);
        $productId = anvil_export_ref_id($values->product ?? null, 'products');
        if ($productId === null) {
            continue;
        }
        $url = anvil_export_public_url($values->url ?? '');
        if ($url === '') {
            $url = anvil_export_save_image($values->file ?? null, $root);
        }
        if ($url !== '') {
            $media[$productId][] = [!empty($values->is_primary), (int)($values->sort_order ?? 100), $url];
        }
    }
    foreach ($media as &$items) {
        usort($items, static fn(array $left, array $right): int => [$right[0], $left[1]] <=> [$left[0], $right[1]]);
    }
    unset($items);

    $productQuery = $pdo->prepare('SELECT id FROM products WHERE (sku=? AND ? IS NOT NULL) OR (model=? AND ? IS NULL) ORDER BY id LIMIT 1');
    $productInsert = $pdo->prepare(
        'INSERT INTO products (model,sku,brand_id,category_id,description,price,image_url,specifications,is_demo,active,created_at) '
        . 'VALUES (?,?,?,?,?,?,?,?,0,?,NOW())'
    );
    $productUpdate = $pdo->prepare(
        'UPDATE products SET model=?, sku=?, brand_id=?, category_id=?, description=?, price=?, image_url=?, specifications=?, is_demo=0, active=? WHERE id=?'
    );
    $productIds = [];
    $seenSkus = [];
    foreach (anvil_export_rows($tables, 'products') as $record) {
        $values = anvil_export_row_values($record);
        $model = trim((string)($values->model ?? ''));
        if ($model === '') {
            continue;
        }
        $sku = trim((string)($values->sku ?? ''));
        if ($sku !== '' && isset($seenSkus[$sku])) {
            $sku = '';
        }
        if ($sku !== '') {
            $seenSkus[$sku] = true;
        }
        $brandSourceId = anvil_export_ref_id($values->brand ?? null, 'brands');
        $categorySourceId = anvil_export_ref_id($values->subcategory ?? null, 'catalog_categories')
            ?? anvil_export_ref_id($values->category ?? null, 'catalog_categories');
        $brandId = $brandIds[$brandSourceId] ?? null;
        $categoryId = $categoryIds[$categorySourceId] ?? null;
        $productPrice = max(0, (float)($prices[$record->id] ?? 0));
        $productImage = $media[$record->id][0][2] ?? '';
        $productSpecs = array_values(array_filter($specs[$record->id] ?? [], static fn(array $row): bool => $row[0] !== '' || $row[1] !== ''));
        $specJson = json_encode($productSpecs, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $active = !empty($values->active) ? 1 : 0;
        $productQuery->execute([$sku ?: null, $sku ?: null, $model, $sku ? null : null]);
        $localProductId = $productQuery->fetchColumn();
        $description = trim((string)($values->description ?? ''));
        if ($localProductId) {
            $productUpdate->execute([$model, $sku ?: null, $brandId, $categoryId, $description, $productPrice, $productImage, $specJson, $active, (int)$localProductId]);
            $productIds[$record->id] = (int)$localProductId;
        } else {
            $productInsert->execute([$model, $sku ?: null, $brandId, $categoryId, $description, $productPrice, $productImage, $specJson, $active]);
            $productIds[$record->id] = (int)$pdo->lastInsertId();
        }
    }

    $formulaInsert = $pdo->prepare(
        'INSERT INTO formulas (code,module,title,expression,input_schema) VALUES (?,?,?,?,?) '
        . 'ON DUPLICATE KEY UPDATE module=VALUES(module),title=VALUES(title),expression=VALUES(expression),input_schema=VALUES(input_schema)'
    );
    foreach (anvil_export_rows($tables, 'formulas') as $record) {
        $values = anvil_export_row_values($record);
        $code = trim((string)($values->code ?? ''));
        $title = trim((string)($values->title ?? ''));
        if ($code === '' || $title === '') {
            continue;
        }
        $inputSchema = anvil_export_decode_value($record->values->input_schema ?? null);
        $inputJson = json_encode($inputSchema ?? new stdClass(), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $formulaInsert->execute([$code, (string)($values->module ?? ''), $title, (string)($values->expression ?? ''), $inputJson]);
    }

    $modules = anvil_export_rows($tables, 'cms_modules');
    $pageInsert = $pdo->prepare(
        'INSERT INTO pages (title,slug,content,published,updated_at) VALUES (?,?,?,?,NOW()) '
        . 'ON DUPLICATE KEY UPDATE title=VALUES(title), content=VALUES(content), published=VALUES(published), updated_at=VALUES(updated_at)'
    );
    $newsInsert = $pdo->prepare(
        'INSERT INTO news (title,slug,excerpt,content,image_url,published,created_at,published_at) VALUES (?,?,?,?,?,?,NOW(),?) '
        . 'ON DUPLICATE KEY UPDATE title=VALUES(title), excerpt=VALUES(excerpt), content=VALUES(content), image_url=VALUES(image_url), published=VALUES(published), published_at=VALUES(published_at)'
    );
    foreach (anvil_export_rows($tables, 'cms_pages') as $record) {
        $values = anvil_export_row_values($record);
        $slug = trim((string)($values->slug ?? ''));
        $title = trim((string)($values->title ?? ''));
        if ($slug === '' || $title === '' || strlen($slug) > 220) {
            continue;
        }
        [$content, $imageUrl] = anvil_export_render_modules($modules, $record->id, $root);
        $settings = anvil_export_decode_value($record->values->settings ?? null);
        $settings = $settings instanceof stdClass ? $settings : new stdClass();
        $published = ($values->status ?? '') === 'published' ? 1 : 0;
        if (trim((string)($settings->news_category ?? '')) !== '') {
            $publishedAt = null;
            if (is_string($settings->publish_date ?? null)) {
                $date = DateTimeImmutable::createFromFormat('!d.m.Y', $settings->publish_date);
                if ($date instanceof DateTimeImmutable) {
                    $publishedAt = $date->format('Y-m-d H:i:s');
                }
            }
            $newsInsert->execute([
                $title, $slug, (string)($settings->excerpt ?? ''), $content,
                $imageUrl, $published, $publishedAt,
            ]);
        } else {
            $pageInsert->execute([$title, $slug, $content, $published]);
        }
    }

    $galleryInsert = $pdo->prepare(
        'INSERT INTO gallery (title,alt_text,image_url,location,sort_order,published) VALUES (?,?,?,?,?,?)'
    );
    $galleryUpdate = $pdo->prepare(
        'UPDATE gallery SET alt_text=?, image_url=?, location=?, sort_order=?, published=? WHERE id=?'
    );
    foreach (anvil_export_rows($tables, 'gallery_items') as $record) {
        $values = anvil_export_row_values($record);
        $title = trim((string)($values->title ?? ''));
        $imageUrl = anvil_export_public_url($values->image_url ?? '');
        if ($title === '' || $imageUrl === '') {
            continue;
        }
        $galleryFind = $pdo->prepare('SELECT id FROM gallery WHERE title=? ORDER BY id LIMIT 1');
        $galleryFind->execute([$title]);
        $localId = $galleryFind->fetchColumn();
        $alt = (string)($values->alt_text ?? '');
        $location = (string)($values->location ?? '');
        $sort = (int)($values->sort_order ?? 100);
        $published = !empty($values->published) ? 1 : 0;
        if ($localId) {
            $galleryUpdate->execute([$alt, $imageUrl, $location, $sort, $published, (int)$localId]);
        } else {
            $galleryInsert->execute([$title, $alt, $imageUrl, $location, $sort, $published]);
        }
    }

    return ['categories' => count($categoryCodes), 'brands' => count($brandIds), 'products' => count($productIds)];
}

/** Validate and merge a gzip JSON export into the protected source-data mirror. */
function import_anvil_export(PDO $pdo, string $filePath): array
{
    if (!is_file($filePath) || !is_readable($filePath)) {
        throw new RuntimeException('Не найден читаемый файл экспорта.');
    }
    $compressedSize = filesize($filePath);
    if ($compressedSize === false || $compressedSize > KLIMA_ANVIL_EXPORT_MAX_COMPRESSED) {
        throw new RuntimeException('Архив Anvil превышает допустимый размер 20 МБ.');
    }
    $compressed = file_get_contents($filePath);
    if (!is_string($compressed) || !function_exists('gzdecode')) {
        throw new RuntimeException('Не удалось прочитать GZIP. Включите PHP-расширение zlib.');
    }
    $json = @gzdecode($compressed, KLIMA_ANVIL_EXPORT_MAX_JSON + 1);
    if (!is_string($json) || strlen($json) > KLIMA_ANVIL_EXPORT_MAX_JSON) {
        throw new RuntimeException('Архив повреждён или содержит более 40 МБ распакованных данных.');
    }
    try {
        $envelope = json_decode($json, false, 512, JSON_THROW_ON_ERROR);
    } catch (JsonException $error) {
        throw new RuntimeException('Файл не является корректным JSON-экспортом Anvil.', 0, $error);
    }
    if (!$envelope instanceof stdClass
        || ($envelope->format ?? null) !== KLIMA_ANVIL_EXPORT_FORMAT
        || ($envelope->schema_version ?? null) !== 1
        || !(($envelope->tables ?? null) instanceof stdClass)
        || !is_string($envelope->sha256 ?? null)
    ) {
        throw new RuntimeException('Формат или версия экспорта Anvil не поддерживается.');
    }

    $tables = $envelope->tables;
    $tableNames = array_keys(get_object_vars($tables));
    $expectedNames = KLIMA_ANVIL_EXPORT_TABLES;
    sort($tableNames, SORT_STRING);
    sort($expectedNames, SORT_STRING);
    if ($tableNames !== $expectedNames) {
        throw new RuntimeException('В экспорте отсутствуют таблицы или найдены неизвестные таблицы.');
    }
    $canonicalTables = anvil_export_canonical_json($tables);
    $checksum = hash('sha256', $canonicalTables);
    if (!hash_equals($checksum, $envelope->sha256)) {
        throw new RuntimeException('Контрольная сумма экспорта не совпала.');
    }

    $ids = anvil_export_collect_ids($tables);
    $rowCount = 0;
    foreach (get_object_vars($tables) as $tableName => $records) {
        $rowCount += count($records);
        if ($rowCount > KLIMA_ANVIL_EXPORT_MAX_ROWS) {
            throw new RuntimeException('В экспорте больше 20 000 строк.');
        }
        foreach ($records as $record) {
            anvil_export_validate_refs($record->values, $ids);
        }
    }

    ensure_anvil_export_schema($pdo);
    $pdo->beginTransaction();
    try {
        $upsert = $pdo->prepare(
            'INSERT INTO anvil_export_rows (source_table,source_id,record_json,imported_at) VALUES (?,?,?,NOW()) '
            . 'ON DUPLICATE KEY UPDATE record_json=VALUES(record_json), imported_at=VALUES(imported_at)'
        );
        foreach (KLIMA_ANVIL_EXPORT_TABLES as $tableName) {
            foreach ($tables->{$tableName} as $record) {
                $values = clone $record->values;
                foreach (['api_key', 'secret_ref', 'password_hash', 'remembered_logins', 'n_password_failures'] as $privateColumn) {
                    unset($values->{$privateColumn});
                }
                $safeRecord = (object)['id' => $record->id, 'values' => $values];
                $upsert->execute([$tableName, $record->id, anvil_export_canonical_json($safeRecord)]);
            }
        }
        $publicCounts = anvil_export_map_public_data($pdo, $tables, dirname(__DIR__));
        $recordImport = $pdo->prepare(
            'INSERT INTO anvil_export_imports (source_export_at,checksum,table_count,row_count,imported_at) VALUES (?,?,?,?,NOW()) '
            . 'ON DUPLICATE KEY UPDATE source_export_at=VALUES(source_export_at), table_count=VALUES(table_count), row_count=VALUES(row_count), imported_at=VALUES(imported_at)'
        );
        $recordImport->execute([
            is_string($envelope->exported_at ?? null) ? $envelope->exported_at : '',
            $checksum,
            count(KLIMA_ANVIL_EXPORT_TABLES),
            $rowCount,
        ]);
        $pdo->commit();
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        throw $error;
    }

    return [
        'tables' => count(KLIMA_ANVIL_EXPORT_TABLES),
        'rows' => $rowCount,
        'public' => $publicCounts,
        'checksum' => $checksum,
        'exported_at' => is_string($envelope->exported_at ?? null) ? $envelope->exported_at : '',
    ];
}
