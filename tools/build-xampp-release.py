from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile
import hashlib
import json
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "shared_hosting_php"
OUTPUT_DIR = ROOT / "dist"
DOWNLOAD_DIR = ROOT / "theme/assets/downloads"
BUILD_DATE = date.today().isoformat()
ARCHIVE_NAME = "KlimaEco-XAMPP-{}.zip".format(BUILD_DATE)
DATABASE_NAME = "KlimaEco-Database-{}.sql".format(BUILD_DATE)
ARCHIVE = OUTPUT_DIR / ARCHIVE_NAME
DATABASE_DUMP = PACKAGE / "database/klimaeco.sql"
ADMIN_PASSWORD_HASH = "$2y$12$s19R1hzYQcetC4Y7lbmQ1eUJ4e55ABQYGho6cIshSc1rc.DbMTWXW"


def sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    text = str(value)
    if text == "":
        return "''"
    encoded = text.encode("utf-8").hex()
    return "CONVERT(0x{} USING utf8mb4)".format(encoded)


def insert_sql(table: str, columns: list[str], values: list[object]) -> str:
    if len(columns) != len(values):
        raise ValueError("Mismatched SQL row for {}".format(table))
    return "INSERT INTO `{}` ({}) VALUES ({});".format(
        table,
        ", ".join("`{}`".format(column) for column in columns),
        ", ".join(sql_value(value) for value in values),
    )


def schema_statements() -> list[str]:
    source_files = [
        PACKAGE / "app/database_setup.php",
        PACKAGE / "app/engineering_schema.php",
        PACKAGE / "app/anvil_import.php",
    ]
    statements: list[str] = []
    for source in source_files:
        text = source.read_text(encoding="utf-8")
        statements.extend(re.findall(r'"(CREATE TABLE IF NOT EXISTS .*?)"', text, re.DOTALL))
    if len(statements) != 18:
        raise SystemExit("Ожидалось 18 таблиц схемы, найдено {}".format(len(statements)))
    return statements


def category_seed_rows() -> list[str]:
    categories = json.loads((PACKAGE / "data/categories.json").read_text(encoding="utf-8"))
    ids = {str(row["code"]): index for index, row in enumerate(categories, start=1)}
    pending = list(categories)
    ordered: list[dict] = []
    available: set[str] = set()
    while pending:
        remaining = []
        for row in pending:
            parent = str(row.get("parent_code") or "")
            if parent and parent not in available:
                remaining.append(row)
                continue
            ordered.append(row)
            available.add(str(row["code"]))
        if len(remaining) == len(pending):
            raise SystemExit("В categories.json есть отсутствующая или циклическая parent_code.")
        pending = remaining

    result = []
    for row in ordered:
        source_image = str(row.get("image_url") or "")
        basename = PurePosixPath(urlparse(source_image).path).name
        local_image = PACKAGE / "assets/images" / basename
        if source_image and local_image.is_file():
            image = "assets/images/" + basename
        elif source_image.lower().startswith("https://"):
            image = source_image
        else:
            image = ""
        parent_code = str(row.get("parent_code") or "")
        result.append(insert_sql("categories", ["id", "code", "title", "parent_id", "image_url", "sort_order", "active"], [
            ids[str(row["code"])], row["code"], row["title"], ids.get(parent_code) if parent_code else None,
            image, int(row.get("sort_order", 100)), 1,
        ]))
    return result


def seed_statements() -> list[str]:
    result = [
        insert_sql("admins", ["id", "login", "password_hash", "created_at"], [1, "admin", ADMIN_PASSWORD_HASH, "2026-01-01 00:00:00"]),
    ]
    result.extend(category_seed_rows())

    formulas = json.loads((PACKAGE / "data/formulas.json").read_text(encoding="utf-8"))
    for row in formulas:
        input_schema = json.dumps(row["input_schema"], ensure_ascii=False, separators=(",", ":"))
        result.append(insert_sql("formulas", ["code", "module", "title", "expression", "input_schema"], [
            row["code"], row["module"], row["title"], row["expression"], input_schema,
        ]))

    defaults = {
        "site_title": "ЭКО-КЛИМАТ",
        "site_tagline": "Инженерные системы, климатическая техника и профессиональный монтаж.",
        "phone": "+7 (000) 000-00-00",
        "email": "info@example.ru",
        "address": "Ваш город · выезд по договорённости",
    }
    for key, value in defaults.items():
        result.append(insert_sql("settings", ["setting_key", "setting_value"], [key, value]))

    pages = json.loads((PACKAGE / "data/price_pages.json").read_text(encoding="utf-8"))
    for page in pages:
        result.append(insert_sql("pages", ["title", "slug", "content", "published", "updated_at"], [
            page["title"], page["slug"], page["content"], 1, "2026-01-01 00:00:00",
        ]))

    hisense = json.loads((PACKAGE / "data/hisense_catalog.json").read_text(encoding="utf-8"))
    category_ids = {str(row["code"]): index for index, row in enumerate(
        json.loads((PACKAGE / "data/categories.json").read_text(encoding="utf-8")), start=1
    )}
    result.append(insert_sql("brands", ["id", "name", "logo_url", "description", "active"], [
        1, "Hisense", "", "Импортировано из каталога исходного проекта", 1,
    ]))
    products = hisense.get("products", [])
    if len(products) != int(hisense.get("product_count", -1)):
        raise SystemExit("Снимок каталога Hisense повреждён или имеет неверное число записей.")
    for product in products:
        code = str(product.get("category_code") or "")
        category_id = category_ids.get(code)
        if not category_id:
            raise SystemExit("Для Hisense не найдена категория {}".format(code))
        specs = json.dumps(product.get("specifications") or {}, ensure_ascii=False, separators=(",", ":"))
        result.append(insert_sql("products", [
            "model", "sku", "brand_id", "category_id", "description", "price", "image_url",
            "specifications", "is_demo", "active", "created_at",
        ], [
            product["model"], product["sku"], 1, category_id, product.get("description", ""),
            Decimal(str(product.get("price", 0))), product.get("image_url", ""), specs, 0, 1,
            "2026-01-01 00:00:00",
        ]))
    return result


def build_database_dump() -> Path:
    statements = schema_statements()
    sql = [
        "-- КлимаЭко: полная начальная база для MySQL / MariaDB.",
        "-- Импортируйте файл в phpMyAdmin. Начальный логин и пароль: admin / admin.",
        "-- Перед импортом в непустую базу создайте резервную копию.",
        "SET NAMES utf8mb4;",
        "CREATE DATABASE IF NOT EXISTS `klimaeco` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        "USE `klimaeco`;",
    ]
    sql.extend(statement.rstrip().rstrip(";") + ";" for statement in statements)
    sql.extend(seed_statements())
    DATABASE_DUMP.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_DUMP.write_text("\n\n".join(sql) + "\n", encoding="utf-8")
    return DATABASE_DUMP


def include_file(path: Path) -> bool:
    relative = path.relative_to(PACKAGE).as_posix()
    if relative.startswith("install/"):
        return False
    if relative.startswith("storage/backups/") and path.name != ".htaccess":
        return False
    if relative.startswith("storage/imports/") and path.name not in {".htaccess", ".keep"}:
        return False
    if relative.startswith("storage/uploads/") and path.name not in {".htaccess", ".keep"}:
        return False
    if any(part in {".git", "node_modules", "__pycache__"} for part in path.parts):
        return False
    if path.suffix.lower() in {".pyc", ".log", ".tmp", ".enc"}:
        return False
    if path.suffix.lower() == ".sql" and relative != "database/klimaeco.sql":
        return False
    return path.is_file()


def main() -> None:
    if not PACKAGE.is_dir():
        raise SystemExit("Не найдена папка PHP-пакета: {}".format(PACKAGE))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    database_file = build_database_dump()
    files = sorted(path for path in PACKAGE.rglob("*") if include_file(path))
    if not files:
        raise SystemExit("PHP-пакет пуст.")
    manifest_lines = [
        "КлимаЭко — готовый архив для XAMPP",
        "Собран: {}".format(datetime.now(timezone.utc).isoformat(timespec="seconds")),
        "Файлов: {}".format(len(files)),
        "Веб-установщик удалён: первый запуск открывает сайт и подготавливает локальную БД.",
        "Полная база для ручного импорта: database/klimaeco.sql",
        "Начальный локальный вход в админку: admin / admin",
        "Секреты и пользовательские файлы исключены.",
        "Инструкция: INSTALL_XAMPP_RU.md",
        "",
    ]
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(PACKAGE).as_posix())
        bundle.writestr("BUILD-MANIFEST.txt", "\n".join(manifest_lines))

    database_asset = DOWNLOAD_DIR / DATABASE_NAME
    shutil.copy2(database_file, database_asset)
    shutil.copy2(ARCHIVE, DOWNLOAD_DIR / ARCHIVE_NAME)
    shutil.copy2(PACKAGE / "INSTALL_XAMPP_RU.md", DOWNLOAD_DIR / "INSTALL_XAMPP_RU.md")
    archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    database_hash = hashlib.sha256(database_asset.read_bytes()).hexdigest()
    print("Архив готов: {}".format(ARCHIVE))
    print("Размер: {} байт".format(ARCHIVE.stat().st_size))
    print("SHA-256 ZIP: {}".format(archive_hash))
    print("База для импорта: {}".format(database_asset))
    print("Размер SQL: {} байт".format(database_asset.stat().st_size))
    print("SHA-256 SQL: {}".format(database_hash))
    print("Файлов пакета: {}".format(len(files)))


if __name__ == "__main__":
    main()
