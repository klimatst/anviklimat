<?php
declare(strict_types=1);

/**
 * Idempotent schema additions for the local Engineering OS.
 * Safe to run during install or at startup: CREATE TABLE IF NOT EXISTS only.
 */
function ensure_engineering_schema(PDO $pdo): void
{
    $statements = [
        "CREATE TABLE IF NOT EXISTS projects (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(220) NOT NULL,
            client_name VARCHAR(190) NOT NULL DEFAULT '',
            phone VARCHAR(80) NOT NULL DEFAULT '',
            email VARCHAR(190) NOT NULL DEFAULT '',
            address VARCHAR(500) NOT NULL DEFAULT '',
            profile VARCHAR(120) NOT NULL DEFAULT '',
            goal TEXT NOT NULL,
            priority VARCHAR(20) NOT NULL DEFAULT 'normal',
            constraints_text TEXT NOT NULL,
            notes LONGTEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            INDEX idx_projects_status_updated (status, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS project_rooms (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            project_id INT UNSIGNED NOT NULL,
            name VARCHAR(190) NOT NULL,
            purpose VARCHAR(190) NOT NULL DEFAULT '',
            area_m2 DECIMAL(12,2) NOT NULL DEFAULT 0,
            height_m DECIMAL(8,2) NOT NULL DEFAULT 0,
            occupants INT UNSIGNED NOT NULL DEFAULT 0,
            notes TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            INDEX idx_project_rooms_project (project_id),
            CONSTRAINT fk_project_rooms_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS project_systems (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            project_id INT UNSIGNED NOT NULL,
            system_type VARCHAR(50) NOT NULL,
            title VARCHAR(220) NOT NULL,
            brand VARCHAR(190) NOT NULL DEFAULT '',
            model VARCHAR(190) NOT NULL DEFAULT '',
            capacity_kw DECIMAL(12,2) NOT NULL DEFAULT 0,
            quantity INT UNSIGNED NOT NULL DEFAULT 1,
            status VARCHAR(30) NOT NULL DEFAULT 'planned',
            notes TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            INDEX idx_project_systems_project (project_id),
            CONSTRAINT fk_project_systems_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS project_calculations (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            project_id INT UNSIGNED NOT NULL,
            system_type VARCHAR(50) NOT NULL,
            title VARCHAR(220) NOT NULL,
            input_json LONGTEXT NOT NULL,
            result_json LONGTEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            created_at DATETIME NOT NULL,
            INDEX idx_project_calculations_project (project_id),
            CONSTRAINT fk_project_calculations_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS project_estimates (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            project_id INT UNSIGNED NOT NULL,
            title VARCHAR(220) NOT NULL,
            amount DECIMAL(14,2) NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            notes TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            INDEX idx_project_estimates_project (project_id),
            CONSTRAINT fk_project_estimates_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    ];
    foreach ($statements as $statement) {
        $pdo->exec($statement);
    }
}
