<?php
declare(strict_types=1);

/**
 * Import the source-controlled Hisense snapshot into the local PHP catalogue.
 * Existing administrator edits are preserved; only missing data and placeholder
 * images are filled for rows whose SKU already exists.
 */
function import_hisense_catalog(PDO $pdo, string $catalogPath): int
{
    if (!is_file($catalogPath)) {
        throw new RuntimeException('Не найден снимок каталога Hisense: ' . basename($catalogPath));
    }
    $catalog = json_decode((string)file_get_contents($catalogPath), true, 512, JSON_THROW_ON_ERROR);
    $products = $catalog['products'] ?? null;
    if (!is_array($products) || count($products) !== (int)($catalog['product_count'] ?? -1)) {
        throw new RuntimeException('Снимок каталога Hisense повреждён или имеет неверное число записей.');
    }

    $brandInsert = $pdo->prepare("INSERT INTO brands (name,description,active) VALUES ('Hisense','Импортировано из каталога исходного проекта',1) ON DUPLICATE KEY UPDATE name=VALUES(name)");
    $brandInsert->execute();
    $brandQuery = $pdo->prepare('SELECT id FROM brands WHERE name=? LIMIT 1');
    $brandQuery->execute(['Hisense']);
    $brandId = $brandQuery->fetchColumn();
    if (!$brandId) {
        throw new RuntimeException('Не удалось создать или найти бренд Hisense.');
    }

    $categoryQuery = $pdo->prepare('SELECT id FROM categories WHERE code=? LIMIT 1');
    $existingQuery = $pdo->prepare('SELECT id FROM products WHERE sku=? OR model=? ORDER BY (sku=?) DESC, id ASC LIMIT 1');
    $existingUpdate = $pdo->prepare(
        'UPDATE products SET '
        . 'brand_id=IFNULL(brand_id,?), category_id=IFNULL(category_id,?), '
        . 'description=IF(description=\'\',?,description), price=IF(price=0,?,price), '
        . 'image_url=IF(image_url=\'\' OR image_url IN (\'assets/images/conditioners.jpg\',\'assets/images/materials.jpg\',\'assets/images/ventilation.jpg\'),?,image_url), '
        . 'specifications=IF(specifications=\'\' OR specifications=\'[]\',?,specifications), is_demo=0 WHERE id=?'
    );
    $productInsert = $pdo->prepare(
        'INSERT INTO products (model,sku,brand_id,category_id,description,price,image_url,specifications,is_demo,active,created_at) '
        . 'VALUES (?,?,?,?,?,?,?,?,0,1,NOW()) '
        . 'ON DUPLICATE KEY UPDATE '
        . 'brand_id=IFNULL(brand_id,VALUES(brand_id)), category_id=IFNULL(category_id,VALUES(category_id)), '
        . 'description=IF(description=\'\',VALUES(description),description), price=IF(price=0,VALUES(price),price), '
        . 'image_url=IF(image_url=\'\' OR image_url IN (\'assets/images/conditioners.jpg\',\'assets/images/materials.jpg\',\'assets/images/ventilation.jpg\'),VALUES(image_url),image_url), '
        . 'specifications=IF(specifications=\'\' OR specifications=\'[]\',VALUES(specifications),specifications), is_demo=0'
    );

    $processed = 0;
    $seen = [];
    foreach ($products as $product) {
        if (!is_array($product)) {
            throw new RuntimeException('В снимке Hisense найдена некорректная запись.');
        }
        $model = trim((string)($product['model'] ?? ''));
        $sku = trim((string)($product['sku'] ?? ''));
        $categoryCode = trim((string)($product['category_code'] ?? ''));
        if ($model === '' || $sku === '' || $categoryCode === '' || isset($seen[$sku])) {
            throw new RuntimeException('В снимке Hisense найден пустой или повторяющийся артикул.');
        }
        $seen[$sku] = true;
        $categoryQuery->execute([$categoryCode]);
        $categoryId = $categoryQuery->fetchColumn();
        if (!$categoryId) {
            throw new RuntimeException('Не найдена категория ' . $categoryCode . ' для модели ' . $model . '.');
        }
        $price = max(0, (float)($product['price'] ?? 0));
        $image = trim((string)($product['image_url'] ?? ''));
        $specifications = $product['specifications'] ?? [];
        if (!is_array($specifications)) {
            $specifications = [];
        }
        $description = trim((string)($product['description'] ?? ''));
        $specJson = json_encode($specifications, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        $existingQuery->execute([$sku, $model, $sku]);
        $existingId = $existingQuery->fetchColumn();
        if ($existingId) {
            $existingUpdate->execute([(int)$brandId, (int)$categoryId, $description, $price, $image, $specJson, (int)$existingId]);
        } else {
            $productInsert->execute([$model, $sku, (int)$brandId, (int)$categoryId, $description, $price, $image, $specJson]);
        }
        $processed++;
    }

    return $processed;
}
