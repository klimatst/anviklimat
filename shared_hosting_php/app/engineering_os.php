<?php
declare(strict_types=1);

function engineering_projects_for_current_admin(): array
{
    if (!admin_user()) return [];
    try {
        return db()->query('SELECT id,title FROM projects ORDER BY updated_at DESC,id DESC LIMIT 100')->fetchAll();
    } catch (Throwable $error) {
        error_log('Engineering project selector unavailable: ' . $error->getMessage());
        return [];
    }
}

function save_engineering_calculation(PDO $pdo, int $projectId, string $systemType, string $title, array $inputs, array $result): void
{
    if (!admin_user()) {
        throw new RuntimeException('Войдите в админ-панель, чтобы сохранять расчёты в проекты.');
    }
    if ($projectId < 1) {
        throw new InvalidArgumentException('Выберите проект для сохранения расчёта.');
    }
    $allowedTypes = ['air_conditioning','multi_split','vrv_vrf','ventilation','refrigeration'];
    if (!in_array($systemType, $allowedTypes, true)) {
        throw new InvalidArgumentException('Неизвестный тип инженерной системы.');
    }
    $projectQuery = $pdo->prepare('SELECT id FROM projects WHERE id=? LIMIT 1');
    $projectQuery->execute([$projectId]);
    if (!$projectQuery->fetchColumn()) {
        throw new InvalidArgumentException('Выбранный проект не найден.');
    }
    $insert = $pdo->prepare('INSERT INTO project_calculations (project_id,system_type,title,input_json,result_json,status,created_at) VALUES (?,?,?,?,?,\'completed\',NOW())');
    $insert->execute([
        $projectId,
        $systemType,
        mb_substr($title, 0, 220, 'UTF-8'),
        json_encode($inputs, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
        json_encode($result, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
    ]);
    $pdo->prepare('UPDATE projects SET updated_at=NOW() WHERE id=?')->execute([$projectId]);
}
