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
    $pdo->exec("CREATE TABLE IF NOT EXISTS anvil_export_site_map (
        source_table VARCHAR(80) NOT NULL,
        source_id VARCHAR(190) NOT NULL,
        target_table VARCHAR(80) NOT NULL,
        target_id BIGINT UNSIGNED NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (source_table, source_id),
        INDEX idx_anvil_export_target (target_table, target_id)
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

function anvil_export_text(mixed $value, int $maximum = 65535): string
{
    if (!is_string($value) && !is_numeric($value)) {
        return '';
    }
    $text = trim((string)$value);
    if (function_exists('mb_strcut')) {
        return mb_strcut($text, 0, $maximum, 'UTF-8');
    }
    $cut = substr($text, 0, $maximum);
    if (function_exists('iconv')) {
        $valid = iconv('UTF-8', 'UTF-8//IGNORE', $cut);
        if ($valid !== false) {
            return $valid;
        }
    }
    return $cut;
}

function anvil_export_json_value(mixed $value): string
{
    return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
}

function anvil_export_mapped_id(PDO $pdo, string $sourceTable, string $sourceId, string $targetTable): ?int
{
    $allowedTargets = ['projects', 'project_rooms', 'project_systems', 'project_calculations', 'project_estimates'];
    if (!in_array($targetTable, $allowedTargets, true)) {
        throw new RuntimeException('Неизвестная целевая таблица сопоставления.');
    }
    $query = $pdo->prepare('SELECT target_id FROM anvil_export_site_map WHERE source_table=? AND source_id=? AND target_table=? LIMIT 1');
    $query->execute([$sourceTable, $sourceId, $targetTable]);
    $id = $query->fetchColumn();
    if ($id === false) {
        return null;
    }
    $exists = $pdo->prepare('SELECT id FROM ' . $targetTable . ' WHERE id=? LIMIT 1');
    $exists->execute([(int)$id]);
    if ($exists->fetchColumn() !== false) {
        return (int)$id;
    }
    $remove = $pdo->prepare('DELETE FROM anvil_export_site_map WHERE source_table=? AND source_id=? AND target_table=?');
    $remove->execute([$sourceTable, $sourceId, $targetTable]);
    return null;
}

function anvil_export_save_mapping(PDO $pdo, string $sourceTable, string $sourceId, string $targetTable, int $targetId): void
{
    $query = $pdo->prepare(
        'INSERT INTO anvil_export_site_map (source_table,source_id,target_table,target_id,updated_at) VALUES (?,?,?,?,NOW()) '
        . 'ON DUPLICATE KEY UPDATE target_table=VALUES(target_table), target_id=VALUES(target_id), updated_at=NOW()'
    );
    $query->execute([$sourceTable, $sourceId, $targetTable, $targetId]);
}

function anvil_export_number(mixed $value, float $minimum = 0, float $maximum = 1000000000000, float $fallback = 0): float
{
    if (!is_numeric($value)) {
        return $fallback;
    }
    $number = (float)$value;
    if (!is_finite($number)) {
        return $fallback;
    }
    return min($maximum, max($minimum, $number));
}

function anvil_export_datetime(mixed $value): string
{
    if (is_string($value) && trim($value) !== '') {
        try {
            return (new DateTimeImmutable($value))->format('Y-m-d H:i:s');
        } catch (Throwable) {
            // Anvil dates are optional on some legacy rows; use a valid local timestamp.
        }
    }
    return gmdate('Y-m-d H:i:s');
}

function anvil_export_pick(stdClass $values, array $keys, mixed $fallback = ''): mixed
{
    foreach ($keys as $key) {
        if (property_exists($values, $key) && $values->{$key} !== null && $values->{$key} !== '') {
            return $values->{$key};
        }
    }
    return $fallback;
}

function anvil_export_object(mixed $value): stdClass
{
    if ($value instanceof stdClass) {
        return $value;
    }
    return is_array($value) ? (object)$value : new stdClass();
}

/** Update or insert a known local Engineering OS row and remember its source ID. */
function anvil_export_upsert_engineering_row(PDO $pdo, string $sourceTable, string $sourceId, string $targetTable, array $values): int
{
    $columnsByTable = [
        'projects' => ['title', 'client_name', 'phone', 'email', 'address', 'profile', 'goal', 'priority', 'constraints_text', 'notes', 'status', 'created_at', 'updated_at'],
        'project_rooms' => ['project_id', 'name', 'purpose', 'area_m2', 'height_m', 'occupants', 'notes', 'created_at'],
        'project_systems' => ['project_id', 'system_type', 'title', 'brand', 'model', 'capacity_kw', 'quantity', 'status', 'notes', 'created_at'],
        'project_calculations' => ['project_id', 'system_type', 'title', 'input_json', 'result_json', 'status', 'created_at'],
        'project_estimates' => ['project_id', 'title', 'amount', 'status', 'notes', 'created_at', 'updated_at'],
    ];
    if (!isset($columnsByTable[$targetTable])) {
        throw new RuntimeException('Неизвестная таблица Engineering OS.');
    }
    $columns = $columnsByTable[$targetTable];
    foreach (array_keys($values) as $column) {
        if (!in_array($column, $columns, true)) {
            throw new RuntimeException('Недопустимое поле Engineering OS: ' . $column);
        }
    }
    $targetId = anvil_export_mapped_id($pdo, $sourceTable, $sourceId, $targetTable);
    if ($targetId !== null) {
        $assignments = array_map(static fn(string $column): string => $column . '=?', array_keys($values));
        $query = $pdo->prepare('UPDATE ' . $targetTable . ' SET ' . implode(',', $assignments) . ' WHERE id=?');
        $query->execute([...array_values($values), $targetId]);
    } else {
        $insertColumns = array_keys($values);
        $query = $pdo->prepare(
            'INSERT INTO ' . $targetTable . ' (' . implode(',', $insertColumns) . ') VALUES ('
            . implode(',', array_fill(0, count($insertColumns), '?')) . ')'
        );
        $query->execute(array_values($values));
        $targetId = (int)$pdo->lastInsertId();
    }
    anvil_export_save_mapping($pdo, $sourceTable, $sourceId, $targetTable, $targetId);
    return $targetId;
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
        if (anvil_export_ref_id($values->page ?? null, 'cms_pages') !== $pageId) {
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
            $linkLabel = trim((string)($content->link_label ?? ''));
            $linkLabel = $linkLabel !== '' ? $linkLabel : ($title !== '' ? $title : $url);
            $parts[] = '<p><a href="' . $escape($url) . '">' . $escape($linkLabel) . '</a></p>';
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
        $code = anvil_export_text(trim((string)($values->code ?? '')), 140);
        $title = anvil_export_text(trim((string)($values->title ?? '')), 190);
        if ($code === '' || $title === '') {
            continue;
        }
        $image = anvil_export_save_image($values->image ?? null, $root);
        $categoryInsert->execute([$code, $title, $image, (int)anvil_export_number($values->sort_order ?? 100, -1000000, 1000000, 100), !empty($values->active) ? 1 : 0]);
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
        $name = anvil_export_text(trim((string)($values->name ?? '')), 190);
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
        $prices[$productId] = anvil_export_number($values->special_price ?? 0, 0, 9999999999.99)
            ?: anvil_export_number($values->sale_price ?? 0, 0, 9999999999.99)
            ?: anvil_export_number($values->purchase_price ?? 0, 0, 9999999999.99);
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
        if ($url !== '' && strlen($url) <= 500) {
            $media[$productId][] = [!empty($values->is_primary), (int)($values->sort_order ?? 100), $url];
        }
    }
    foreach ($media as &$items) {
        usort($items, static function (array $left, array $right): int {
            if ($left[0] !== $right[0]) {
                return $left[0] ? -1 : 1;
            }
            return $left[1] <=> $right[1];
        });
    }
    unset($items);

    $productBySku = $pdo->prepare('SELECT id FROM products WHERE sku=? ORDER BY id LIMIT 1');
    $productByModel = $pdo->prepare('SELECT id FROM products WHERE model=? ORDER BY id LIMIT 1');
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
        $model = anvil_export_text(trim((string)($values->model ?? '')), 190);
        if ($model === '') {
            continue;
        }
        $sku = anvil_export_text(trim((string)($values->sku ?? '')), 120);
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
        $productPrice = anvil_export_number($prices[$record->id] ?? 0, 0, 9999999999.99);
        $productImage = $media[$record->id][0][2] ?? '';
        $productSpecs = array_values(array_filter($specs[$record->id] ?? [], static fn(array $row): bool => $row[0] !== '' || $row[1] !== ''));
        $specJson = json_encode($productSpecs, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $active = !empty($values->active) ? 1 : 0;
        if ($sku !== '') {
            $productBySku->execute([$sku]);
            $localProductId = $productBySku->fetchColumn();
        } else {
            $productByModel->execute([$model]);
            $localProductId = $productByModel->fetchColumn();
        }
        $description = anvil_export_text(trim((string)($values->description ?? '')), 65535);
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
        $code = anvil_export_text(trim((string)($values->code ?? '')), 140);
        $title = anvil_export_text(trim((string)($values->title ?? '')), 220);
        if ($code === '' || $title === '') {
            continue;
        }
        $inputSchema = anvil_export_decode_value($record->values->input_schema ?? null);
        $inputJson = json_encode($inputSchema ?? new stdClass(), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $formulaInsert->execute([
            $code, anvil_export_text($values->module ?? '', 100), $title,
            anvil_export_text($values->expression ?? '', 65535), $inputJson,
        ]);
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
        $slug = anvil_export_text(trim((string)($values->slug ?? '')), 220);
        $title = anvil_export_text(trim((string)($values->title ?? '')), 220);
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
                $title, $slug, anvil_export_text($settings->excerpt ?? '', 65535), $content,
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
        $title = anvil_export_text(trim((string)($values->title ?? '')), 220);
        $imageUrl = anvil_export_public_url($values->image_url ?? '');
        if ($imageUrl === '') {
            $imageUrl = anvil_export_save_image($values->image ?? null, $root);
        }
        if ($title === '' || $imageUrl === '' || strlen($imageUrl) > 500) {
            continue;
        }
        $galleryFind = $pdo->prepare('SELECT id FROM gallery WHERE title=? ORDER BY id LIMIT 1');
        $galleryFind->execute([$title]);
        $localId = $galleryFind->fetchColumn();
        $alt = anvil_export_text($values->alt_text ?? $values->description ?? '', 220);
        $location = anvil_export_text($values->location ?? '', 190);
        $sort = (int)anvil_export_number($values->sort_order ?? 100, -1000000, 1000000, 100);
        $published = !empty($values->published) ? 1 : 0;
        if ($localId) {
            $galleryUpdate->execute([$alt, $imageUrl, $location, $sort, $published, (int)$localId]);
        } else {
            $galleryInsert->execute([$title, $alt, $imageUrl, $location, $sort, $published]);
        }
    }

    $engineering = anvil_export_map_engineering_data($pdo, $tables);
    return [
        'categories' => count($categoryCodes), 'brands' => count($brandIds),
        'products' => count($productIds), ...$engineering,
    ];
}

/** Map the main Engineering OS records while preserving every source row in its mirror. */
function anvil_export_map_engineering_data(PDO $pdo, stdClass $tables): array
{
    $source = [];
    foreach (['crm_clients', 'objects', 'projects', 'rooms', 'systems', 'calculations', 'estimates', 'estimate_lines', 'formulas'] as $tableName) {
        $source[$tableName] = [];
        foreach (anvil_export_rows($tables, $tableName) as $record) {
            if ($record instanceof stdClass && is_string($record->id ?? null)) {
                $source[$tableName][$record->id] = anvil_export_row_values($record);
            }
        }
    }

    $mapped = ['projects' => 0, 'rooms' => 0, 'systems' => 0, 'calculations' => 0, 'estimates' => 0];
    foreach (anvil_export_rows($tables, 'projects') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)) {
            continue;
        }
        $values = $source['projects'][$record->id] ?? new stdClass();
        $clientId = anvil_export_ref_id($values->client ?? null, 'crm_clients');
        $client = $clientId !== null ? ($source['crm_clients'][$clientId] ?? new stdClass()) : new stdClass();
        $objectId = anvil_export_ref_id($values->object ?? null, 'objects');
        $object = $objectId !== null ? ($source['objects'][$objectId] ?? new stdClass()) : new stdClass();
        $objectParameters = anvil_export_object($object->parameters ?? null);
        $status = (string)($values->status ?? 'draft');
        if (!in_array($status, ['draft', 'active', 'installation', 'service', 'completed'], true)) {
            $status = in_array($status, ['done', 'closed', 'cancelled'], true) ? 'completed' : 'draft';
        }
        $title = anvil_export_text(trim((string)($values->title ?? '')), 220);
        if ($title === '') {
            $title = trim((string)($object->name ?? '')) ?: 'Проект ' . $record->id;
        }
        $localId = anvil_export_upsert_engineering_row($pdo, 'projects', $record->id, 'projects', [
            'title' => anvil_export_text($title, 220),
            'client_name' => anvil_export_text($client->name ?? '', 190),
            'phone' => anvil_export_text($client->phone ?? '', 80),
            'email' => anvil_export_text($client->email ?? '', 190),
            'address' => anvil_export_text($object->address ?? '', 500),
            'profile' => anvil_export_text(anvil_export_pick($objectParameters, ['profile', 'object_type', 'type'], ''), 120),
            'goal' => anvil_export_text(anvil_export_pick($objectParameters, ['goal', 'purpose'], ''), 65535),
            'priority' => 'normal',
            'constraints_text' => '',
            'notes' => anvil_export_text($values->code ?? '', 65535),
            'status' => $status,
            'created_at' => anvil_export_datetime($values->created_at ?? null),
            'updated_at' => anvil_export_datetime($values->updated_at ?? $values->created_at ?? null),
        ]);
        if ($objectId !== null && anvil_export_mapped_id($pdo, 'objects', $objectId, 'projects') === null) {
            anvil_export_save_mapping($pdo, 'objects', $objectId, 'projects', $localId);
        }
        $mapped['projects']++;
    }

    // Objects without a project remain usable as Engineering OS records when they own rooms.
    $objectsWithRooms = [];
    foreach (anvil_export_rows($tables, 'rooms') as $record) {
        $values = $source['rooms'][$record->id] ?? new stdClass();
        $objectId = anvil_export_ref_id($values->object ?? null, 'objects');
        if ($objectId !== null) {
            $objectsWithRooms[$objectId] = true;
        }
    }
    foreach (anvil_export_rows($tables, 'objects') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)
            || !isset($objectsWithRooms[$record->id])
            || anvil_export_mapped_id($pdo, 'objects', $record->id, 'projects') !== null
        ) {
            continue;
        }
        $values = $source['objects'][$record->id] ?? new stdClass();
        $parameters = anvil_export_object($values->parameters ?? null);
        $name = trim((string)($values->name ?? '')) ?: 'Объект ' . $record->id;
        anvil_export_upsert_engineering_row($pdo, 'objects', $record->id, 'projects', [
            'title' => anvil_export_text('Объект: ' . $name, 220),
            'client_name' => '', 'phone' => '', 'email' => '',
            'address' => anvil_export_text($values->address ?? '', 500),
            'profile' => anvil_export_text(anvil_export_pick($parameters, ['profile', 'object_type', 'type'], ''), 120),
            'goal' => anvil_export_text(anvil_export_pick($parameters, ['goal', 'purpose'], ''), 65535),
            'priority' => 'normal', 'constraints_text' => '',
            'notes' => 'Создано при переносе объекта Anvil без отдельного проекта.',
            'status' => 'draft',
            'created_at' => anvil_export_datetime($values->created_at ?? null),
            'updated_at' => anvil_export_datetime($values->updated_at ?? $values->created_at ?? null),
        ]);
        $mapped['projects']++;
    }

    foreach (anvil_export_rows($tables, 'rooms') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)) {
            continue;
        }
        $values = $source['rooms'][$record->id] ?? new stdClass();
        $objectId = anvil_export_ref_id($values->object ?? null, 'objects');
        $projectId = $objectId !== null ? anvil_export_mapped_id($pdo, 'objects', $objectId, 'projects') : null;
        if ($projectId === null) {
            continue;
        }
        $parameters = anvil_export_object($values->parameters ?? null);
        $notes = anvil_export_pick($parameters, ['notes', 'description'], '');
        $purpose = anvil_export_pick($parameters, ['purpose', 'room_type', 'type'], '');
        $mappedId = anvil_export_upsert_engineering_row($pdo, 'rooms', $record->id, 'project_rooms', [
            'project_id' => $projectId,
            'name' => anvil_export_text($values->name ?? '', 190) ?: 'Помещение ' . $record->id,
            'purpose' => anvil_export_text($purpose, 190),
            'area_m2' => anvil_export_number($values->area ?? 0, 0, 100000),
            'height_m' => anvil_export_number($values->height ?? 0, 0, 100),
            'occupants' => (int)anvil_export_number(anvil_export_pick($parameters, ['occupants', 'people', 'people_count'], 0), 0, 100000),
            'notes' => anvil_export_text($notes, 65535),
            'created_at' => anvil_export_datetime($values->created_at ?? null),
        ]);
        $mapped['rooms']++;
    }

    foreach (anvil_export_rows($tables, 'systems') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)) {
            continue;
        }
        $values = $source['systems'][$record->id] ?? new stdClass();
        $sourceProjectId = anvil_export_ref_id($values->project ?? null, 'projects');
        $projectId = $sourceProjectId !== null ? anvil_export_mapped_id($pdo, 'projects', $sourceProjectId, 'projects') : null;
        if ($projectId === null) {
            continue;
        }
        $parameters = anvil_export_object($values->parameters ?? null);
        $status = (string)($values->status ?? 'planned');
        if (!in_array($status, ['planned', 'selected', 'ordered', 'installed', 'service'], true)) {
            $status = 'planned';
        }
        anvil_export_upsert_engineering_row($pdo, 'systems', $record->id, 'project_systems', [
            'project_id' => $projectId,
            'system_type' => anvil_export_text($values->type ?? 'other', 50) ?: 'other',
            'title' => anvil_export_text($values->title ?? '', 220) ?: 'Система ' . $record->id,
            'brand' => anvil_export_text(anvil_export_pick($parameters, ['brand', 'manufacturer'], ''), 190),
            'model' => anvil_export_text(anvil_export_pick($parameters, ['model', 'model_name'], ''), 190),
            'capacity_kw' => anvil_export_number(anvil_export_pick($parameters, ['capacity_kw', 'capacity', 'power_kw'], 0), 0, 100000),
            'quantity' => (int)anvil_export_number(anvil_export_pick($parameters, ['quantity', 'count'], 1), 1, 10000, 1),
            'status' => $status,
            'notes' => anvil_export_text(anvil_export_pick($parameters, ['notes', 'description'], ''), 65535),
            'created_at' => anvil_export_datetime($values->created_at ?? null),
        ]);
        $mapped['systems']++;
    }

    foreach (anvil_export_rows($tables, 'calculations') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)) {
            continue;
        }
        $values = $source['calculations'][$record->id] ?? new stdClass();
        $sourceProjectId = anvil_export_ref_id($values->project ?? null, 'projects');
        $sourceSystemId = anvil_export_ref_id($values->system ?? null, 'systems');
        $system = $sourceSystemId !== null ? ($source['systems'][$sourceSystemId] ?? new stdClass()) : new stdClass();
        if ($sourceProjectId === null) {
            $sourceProjectId = anvil_export_ref_id($system->project ?? null, 'projects');
        }
        $projectId = $sourceProjectId !== null ? anvil_export_mapped_id($pdo, 'projects', $sourceProjectId, 'projects') : null;
        if ($projectId === null) {
            continue;
        }
        $formulaSourceId = anvil_export_ref_id($values->formula ?? null, 'formulas');
        $formula = $formulaSourceId !== null ? ($source['formulas'][$formulaSourceId] ?? new stdClass()) : new stdClass();
        $input = (object)[
            'inputs' => $values->inputs ?? new stdClass(),
            'coefficients' => $values->coefficients ?? new stdClass(),
            'units' => $values->units ?? new stdClass(),
            'formula' => $formulaSourceId,
            'version' => $values->version ?? '',
        ];
        $result = (object)['value' => $values->result ?? null, 'details' => $values->details ?? new stdClass()];
        $details = anvil_export_object($values->details ?? null);
        $status = anvil_export_pick($details, ['status'], 'completed');
        if (!in_array($status, ['draft', 'completed', 'needs_review'], true)) {
            $status = 'completed';
        }
        anvil_export_upsert_engineering_row($pdo, 'calculations', $record->id, 'project_calculations', [
            'project_id' => $projectId,
            'system_type' => anvil_export_text($system->type ?? $formula->module ?? 'other', 50) ?: 'other',
            'title' => anvil_export_text(anvil_export_pick($details, ['title'], $formula->title ?? 'Расчёт'), 220) ?: 'Расчёт ' . $record->id,
            'input_json' => anvil_export_json_value($input),
            'result_json' => anvil_export_json_value($result),
            'status' => (string)$status,
            'created_at' => anvil_export_datetime($values->created_at ?? null),
        ]);
        $mapped['calculations']++;
    }

    $estimateLines = [];
    foreach (anvil_export_rows($tables, 'estimate_lines') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)) {
            continue;
        }
        $values = $source['estimate_lines'][$record->id] ?? new stdClass();
        $estimateId = anvil_export_ref_id($values->estimate ?? null, 'estimates');
        if ($estimateId !== null) {
            $estimateLines[$estimateId][] = (object)[
                'line_key' => $values->line_key ?? '', 'description' => $values->description ?? '',
                'quantity' => $values->quantity ?? 0, 'unit' => $values->unit ?? '',
                'unit_price' => $values->unit_price ?? 0, 'currency' => $values->currency ?? '',
                'line_total' => $values->line_total ?? 0, 'source' => $values->source ?? '',
                'snapshot' => $values->snapshot ?? new stdClass(),
            ];
        }
    }
    foreach (anvil_export_rows($tables, 'estimates') as $record) {
        if (!$record instanceof stdClass || !is_string($record->id ?? null)) {
            continue;
        }
        $values = $source['estimates'][$record->id] ?? new stdClass();
        $sourceProjectId = anvil_export_ref_id($values->project ?? null, 'projects');
        $projectId = $sourceProjectId !== null ? anvil_export_mapped_id($pdo, 'projects', $sourceProjectId, 'projects') : null;
        if ($projectId === null) {
            continue;
        }
        $details = anvil_export_object($values->details ?? null);
        $status = anvil_export_pick($details, ['status'], 'draft');
        if (!in_array($status, ['draft', 'sent', 'approved', 'accepted'], true)) {
            $status = 'draft';
        }
        $estimateSummary = (object)[
            'currency' => $values->currency ?? 'RUB', 'materials_cost' => $values->materials_cost ?? 0,
            'labor_cost' => $values->labor_cost ?? 0, 'consumables_cost' => $values->consumables_cost ?? 0,
            'version' => $values->version ?? '',
            'title' => anvil_export_pick($details, ['title', 'name'], ''),
            'line_count' => count($estimateLines[$record->id] ?? []),
        ];
        anvil_export_upsert_engineering_row($pdo, 'estimates', $record->id, 'project_estimates', [
            'project_id' => $projectId,
            'title' => anvil_export_text(anvil_export_pick($details, ['title', 'name'], 'Смета'), 220) ?: 'Смета ' . $record->id,
            'amount' => anvil_export_number($values->total ?? 0, 0, 1000000000000),
            'status' => (string)$status,
            'notes' => anvil_export_text(anvil_export_json_value($estimateSummary), 65535),
            'created_at' => anvil_export_datetime($values->updated_at ?? null),
            'updated_at' => anvil_export_datetime($values->updated_at ?? null),
        ]);
        $mapped['estimates']++;
    }
    return $mapped;
}

/** Reapply edited mirror records to the PHP site's ordinary content and Engineering OS tables. */
function sync_anvil_export_mirror_to_site(PDO $pdo): array
{
    ensure_anvil_export_schema($pdo);
    $tables = new stdClass();
    foreach (KLIMA_ANVIL_EXPORT_TABLES as $tableName) {
        $tables->{$tableName} = [];
    }
    $rows = $pdo->query('SELECT source_table,source_id,record_json FROM anvil_export_rows ORDER BY source_table,source_id')->fetchAll(PDO::FETCH_ASSOC);
    if (!$rows) {
        throw new RuntimeException('Зеркало Anvil пусто. Сначала импортируйте экспорт из Anvil.');
    }
    foreach ($rows as $row) {
        $tableName = (string)($row['source_table'] ?? '');
        if (!in_array($tableName, KLIMA_ANVIL_EXPORT_TABLES, true)) {
            throw new RuntimeException('В зеркале обнаружена неизвестная таблица: ' . $tableName);
        }
        try {
            $record = json_decode((string)$row['record_json'], false, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $error) {
            throw new RuntimeException('JSON-запись зеркала повреждена: ' . $tableName . ' / ' . (string)$row['source_id'], 0, $error);
        }
        if (!$record instanceof stdClass || ($record->id ?? null) !== (string)$row['source_id'] || !(($record->values ?? null) instanceof stdClass)) {
            throw new RuntimeException('Структура записи зеркала повреждена: ' . $tableName . ' / ' . (string)$row['source_id']);
        }
        $tables->{$tableName}[] = $record;
    }
    $ownsTransaction = !$pdo->inTransaction();
    if ($ownsTransaction) {
        $pdo->beginTransaction();
    }
    try {
        $result = anvil_export_map_public_data($pdo, $tables, dirname(__DIR__));
        if ($ownsTransaction) {
            $pdo->commit();
        }
        return $result;
    } catch (Throwable $error) {
        if ($ownsTransaction && $pdo->inTransaction()) {
            $pdo->rollBack();
        }
        throw $error;
    }
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
    $tablesMarker = '"tables":';
    $tablesMarkerPosition = strpos($json, $tablesMarker);
    $outerClosingBrace = strrpos($json, '}');
    if ($tablesMarkerPosition === false || $outerClosingBrace === false) {
        throw new RuntimeException('В экспорте не найден блок таблиц.');
    }
    $tablesPayloadStart = $tablesMarkerPosition + strlen($tablesMarker);
    $tablesPayload = substr($json, $tablesPayloadStart, $outerClosingBrace - $tablesPayloadStart);
    if (!str_starts_with($tablesPayload, '{') || !str_ends_with($tablesPayload, '}')) {
        throw new RuntimeException('Блок таблиц в экспорте повреждён.');
    }
    $checksum = hash('sha256', $tablesPayload);
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
