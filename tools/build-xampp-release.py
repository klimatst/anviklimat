from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import hashlib


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "shared_hosting_php"
OUTPUT_DIR = ROOT / "dist"
ARCHIVE = OUTPUT_DIR / "KlimaEco-XAMPP-{}.zip".format(date.today().isoformat())
def include_file(path: Path) -> bool:
    relative = path.relative_to(PACKAGE).as_posix()
    if relative == "app/config.php":
        return False
    if relative.startswith("storage/backups/") and path.name != ".htaccess":
        return False
    if relative.startswith("storage/imports/") and path.name not in {".htaccess", ".keep"}:
        return False
    if relative.startswith("storage/uploads/") and path.name not in {".htaccess", ".keep"}:
        return False
    if any(part in {".git", "node_modules", "__pycache__"} for part in path.parts):
        return False
    if path.suffix.lower() in {".pyc", ".log", ".tmp", ".enc", ".sql"}:
        return False
    return path.is_file()


def main() -> None:
    if not PACKAGE.is_dir():
        raise SystemExit("Не найдена папка PHP-пакета: {}".format(PACKAGE))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in PACKAGE.rglob("*") if include_file(path))
    if not files:
        raise SystemExit("PHP-пакет пуст.")
    manifest_lines = [
        "КлимаЭко — архив для XAMPP",
        "Собран: {}".format(datetime.now(timezone.utc).isoformat(timespec="seconds")),
        "Файлов: {}".format(len(files)),
        "Секреты и пользовательские файлы исключены.",
        "Установка: INSTALL_XAMPP_RU.md",
        "",
    ]
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(PACKAGE).as_posix())
        bundle.writestr("BUILD-MANIFEST.txt", "\n".join(manifest_lines))
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    print("Архив готов: {}".format(ARCHIVE))
    print("Размер: {} байт".format(ARCHIVE.stat().st_size))
    print("SHA-256: {}".format(digest))
    print("Файлов пакета: {}".format(len(files)))


if __name__ == "__main__":
    main()
