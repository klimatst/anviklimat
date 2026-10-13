<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/app/anvil_import.php';

final class AnvilImportSmokeStatement extends PDOStatement
{
    private array $params = [];

    public function __construct(private readonly string $sql, private readonly AnvilImportSmokePdo $pdo) {}

    public function execute(?array $params = null): bool
    {
        $this->params = $params ?? [];
        if (str_starts_with($this->sql, 'INSERT INTO anvil_export_site_map')) {
            [$sourceTable, $sourceId, $targetTable, $targetId] = $this->params;
            $this->pdo->mappings[$sourceTable . ':' . $sourceId] = ['table' => $targetTable, 'id' => (int)$targetId];
        } elseif (str_starts_with($this->sql, 'DELETE FROM anvil_export_site_map')) {
            [$sourceTable, $sourceId] = $this->params;
            unset($this->pdo->mappings[$sourceTable . ':' . $sourceId]);
        } elseif (preg_match('/^INSERT INTO (projects|project_rooms|project_systems|project_calculations|project_estimates)\b/', $this->sql, $match)) {
            $id = ++$this->pdo->nextId;
            $this->pdo->lastId = $id;
            $this->pdo->targetRows[$match[1]][$id] = true;
            $this->pdo->insertCounts[$match[1]] = ($this->pdo->insertCounts[$match[1]] ?? 0) + 1;
        }
        return true;
    }

    public function fetchColumn(int $column = 0): mixed
    {
        if (str_contains($this->sql, 'SELECT target_id FROM anvil_export_site_map')) {
            [$sourceTable, $sourceId, $targetTable] = $this->params;
            $mapping = $this->pdo->mappings[$sourceTable . ':' . $sourceId] ?? null;
            return $mapping && $mapping['table'] === $targetTable ? $mapping['id'] : false;
        }
        if (preg_match('/^SELECT id FROM (projects|project_rooms|project_systems|project_calculations|project_estimates) WHERE id=/', $this->sql, $match)) {
            $id = (int)($this->params[0] ?? 0);
            return isset($this->pdo->targetRows[$match[1]][$id]) ? $id : false;
        }
        return false;
    }
}

final class AnvilImportSmokePdo extends PDO
{
    private bool $transaction = false;
    public array $mappings = [];
    public array $targetRows = [];
    public array $insertCounts = [];
    public int $nextId = 100;
    public int $lastId = 0;

    public function __construct() {}

    public function exec(string $statement): int|false
    {
        return 0;
    }

    public function prepare(string $query, array $options = []): PDOStatement|false
    {
        return new AnvilImportSmokeStatement($query, $this);
    }

    public function beginTransaction(): bool
    {
        $this->transaction = true;
        return true;
    }

    public function commit(): bool
    {
        $this->transaction = false;
        return true;
    }

    public function inTransaction(): bool
    {
        return $this->transaction;
    }

    public function rollBack(): bool
    {
        $this->transaction = false;
        return true;
    }

    public function lastInsertId(?string $name = null): string|false
    {
        return (string)$this->lastId;
    }
}

$tables = new stdClass();
foreach (KLIMA_ANVIL_EXPORT_TABLES as $table) {
    $tables->{$table} = [];
}
$tables->brands = [(object)[
    'id' => 'brand-1',
    'values' => (object)['name' => 'Тестовый бренд', 'name_key' => 'test-brand'],
]];
$tables->catalog_categories = [(object)[
    'id' => 'category-1',
    'values' => (object)[
        'code' => 'test-category', 'title' => 'Тестовая категория',
        'parent' => null, 'active' => true, 'sort_order' => 10, 'image' => null,
    ],
]];
$tables->products = [(object)[
    'id' => 'product-1',
    'values' => (object)[
        'model' => 'TEST-001', 'sku' => 'TEST-001', 'description' => 'Проверка переноса',
        'active' => true,
        'brand' => (object)['$type' => 'ref', 'table' => 'brands', 'id' => 'brand-1'],
        'category' => (object)['$type' => 'ref', 'table' => 'catalog_categories', 'id' => 'category-1'],
        'subcategory' => null,
    ],
]];
$objectValues = (object)[
    'name' => 'Офисный объект', 'object_type' => 'office', 'address' => 'Москва, ул. Тестовая, 1',
    'parameters' => (object)['$type' => 'object', 'value' => (object)['profile' => 'office']],
    'created_at' => (object)['$type' => 'datetime', 'value' => '2026-10-12T10:00:00+00:00'],
];
$tables->crm_clients = [(object)['id' => 'client-1', 'values' => (object)[
    'name' => 'ООО Проверка', 'email' => 'check@example.test', 'phone' => '+7 900 000-00-00',
]]];
$tables->objects = [(object)['id' => 'object-1', 'values' => $objectValues]];
$tables->projects = [(object)['id' => 'project-1', 'values' => (object)[
    'code' => 'P-1', 'title' => 'Тестовый проект', 'status' => 'active', 'version' => '1',
    'client' => (object)['$type' => 'ref', 'table' => 'crm_clients', 'id' => 'client-1'],
    'object' => (object)['$type' => 'ref', 'table' => 'objects', 'id' => 'object-1'],
    'created_at' => (object)['$type' => 'datetime', 'value' => '2026-10-12T10:00:00+00:00'],
    'updated_at' => (object)['$type' => 'datetime', 'value' => '2026-10-12T11:00:00+00:00'],
]]];
$tables->rooms = [(object)['id' => 'room-1', 'values' => (object)[
    'object' => (object)['$type' => 'ref', 'table' => 'objects', 'id' => 'object-1'],
    'name' => 'Переговорная', 'area' => 24, 'height' => 3,
    'parameters' => (object)['$type' => 'object', 'value' => (object)['occupants' => 6, 'purpose' => 'Рабочая']],
    'sort_order' => 1,
]]];
$tables->systems = [(object)['id' => 'system-1', 'values' => (object)[
    'project' => (object)['$type' => 'ref', 'table' => 'projects', 'id' => 'project-1'],
    'type' => 'ventilation', 'title' => 'Приточно-вытяжная установка',
    'parameters' => (object)['$type' => 'object', 'value' => (object)['brand' => 'Тест', 'model' => 'V-1', 'capacity_kw' => 4.5, 'quantity' => 1]],
    'status' => 'selected', 'version' => '1',
]]];
$tables->formulas = [(object)['id' => 'formula-1', 'values' => (object)[
    'code' => 'airflow', 'module' => 'ventilation', 'title' => 'Воздухообмен', 'expression' => 'area * rate',
]]];
$tables->calculations = [(object)['id' => 'calc-1', 'values' => (object)[
    'formula' => (object)['$type' => 'ref', 'table' => 'formulas', 'id' => 'formula-1'],
    'project' => (object)['$type' => 'ref', 'table' => 'projects', 'id' => 'project-1'],
    'system' => (object)['$type' => 'ref', 'table' => 'systems', 'id' => 'system-1'],
    'inputs' => (object)['$type' => 'object', 'value' => (object)['area' => 24, 'rate' => 3]],
    'coefficients' => (object)['$type' => 'object', 'value' => (object)[]],
    'units' => (object)['$type' => 'object', 'value' => (object)[]],
    'result' => 72, 'source' => 'smoke', 'version' => '1',
    'details' => (object)['$type' => 'object', 'value' => (object)['title' => 'Расчёт воздухообмена']],
    'created_at' => (object)['$type' => 'datetime', 'value' => '2026-10-12T12:00:00+00:00'],
]]];
$tables->estimates = [(object)['id' => 'estimate-1', 'values' => (object)[
    'project' => (object)['$type' => 'ref', 'table' => 'projects', 'id' => 'project-1'],
    'currency' => 'RUB', 'materials_cost' => 80000, 'labor_cost' => 20000,
    'consumables_cost' => 3000, 'total' => 103000,
    'details' => (object)['$type' => 'object', 'value' => (object)['title' => 'Смета проекта']],
    'version' => '1', 'updated_at' => (object)['$type' => 'datetime', 'value' => '2026-10-12T13:00:00+00:00'],
]]];
$tables->estimate_lines = [(object)['id' => 'line-1', 'values' => (object)[
    'estimate' => (object)['$type' => 'ref', 'table' => 'estimates', 'id' => 'estimate-1'],
    'line_key' => 'duct-1', 'product' => null, 'description' => 'Воздуховод',
    'quantity' => 10, 'unit' => 'м', 'unit_price' => 500, 'currency' => 'RUB',
    'line_total' => 5000, 'source' => 'smoke',
    'snapshot' => (object)['$type' => 'object', 'value' => (object)[]],
]]];

$envelope = (object)[
    'format' => KLIMA_ANVIL_EXPORT_FORMAT,
    'schema_version' => 1,
    'exported_at' => '2026-10-13T00:00:00+00:00',
    'sha256' => hash('sha256', anvil_export_canonical_json($tables)),
    'tables' => $tables,
];
$temporary = tempnam(sys_get_temp_dir(), 'klimaeco-anvil-');
if (!is_string($temporary)) {
    throw new RuntimeException('Could not create temporary fixture.');
}
$archivePath = $temporary . '.json.gz';
unlink($temporary);
if (file_put_contents($archivePath, gzencode(anvil_export_canonical_json($envelope), 6)) === false) {
    throw new RuntimeException('Could not write compressed fixture.');
}

try {
    $pdo = new AnvilImportSmokePdo();
    $result = import_anvil_export($pdo, $archivePath);
    if ($result['tables'] !== 44 || $result['rows'] !== 12
        || $result['public']['categories'] !== 1
        || $result['public']['brands'] !== 1
        || $result['public']['products'] !== 1
        || $result['public']['projects'] !== 1
        || $result['public']['rooms'] !== 1
        || $result['public']['systems'] !== 1
        || $result['public']['calculations'] !== 1
        || $result['public']['estimates'] !== 1
    ) {
        throw new RuntimeException('Export import counts or catalog/engineering mapping are incorrect.');
    }
    $targetCounts = $pdo->insertCounts;
    import_anvil_export($pdo, $archivePath);
    foreach (['projects', 'project_rooms', 'project_systems', 'project_calculations', 'project_estimates'] as $tableName) {
        if (($pdo->insertCounts[$tableName] ?? 0) !== ($targetCounts[$tableName] ?? 0)) {
            throw new RuntimeException('A repeated Anvil import created duplicate Engineering OS records.');
        }
    }

    $badEnvelope = clone $envelope;
    $badEnvelope->sha256 = str_repeat('0', 64);
    file_put_contents($archivePath, gzencode(anvil_export_canonical_json($badEnvelope), 6));
    try {
        import_anvil_export(new AnvilImportSmokePdo(), $archivePath);
        throw new RuntimeException('Invalid checksum was accepted.');
    } catch (RuntimeException $error) {
        if ($error->getMessage() === 'Invalid checksum was accepted.') {
            throw $error;
        }
    }
} finally {
    if (is_file($archivePath)) {
        unlink($archivePath);
    }
}

echo "PASS: 44-table gzip export validated, catalog and Engineering OS records mapped idempotently, and invalid checksums rejected.\n";
