import base64
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json

import anvil
import anvil.secrets
import anvil.server
import anvil.users
import Core
from anvil.tables import app_tables


FORMAT_NAME = "hvac-studio-backup"
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
BACKUP_SECRET = "HVAC_BACKUP_KEY"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_DATA_BYTES = 40 * 1024 * 1024
MAX_ROWS = 20000
LEGACY_BACKUP_TABLES = (
  "ai_providers", "bom", "brands", "calculations", "catalog_categories",
  "cms_modules", "cms_pages", "compatibility", "crm_clients", "crm_contacts",
  "crm_tasks", "estimate_lines", "estimates", "formulas", "imports",
  "gallery_items", "media_objects", "objects", "product_media", "product_prices",
  "product_sources", "product_specs", "product_stock", "products", "projects",
  "quotes", "roles", "rooms", "service", "system_components",
  "system_connections", "system_settings", "systems", "users"
)
BACKUP_TABLES = (
  "ai_providers", "bom", "brands", "calculations", "catalog_categories",
  "catalog_documents", "catalog_orders", "catalog_series", "cms_modules", "cms_pages", "compatibility", "crm_clients",
  "crm_contacts", "crm_tasks", "estimate_lines", "estimates", "formulas",
  "gallery_items", "imports", "import_logs", "media_objects", "objects",
  "product_media", "product_prices", "product_sources", "product_specs",
  "product_stock", "products", "projects", "quotes", "roles", "rooms",
  "service", "system_components", "system_connections", "system_settings",
  "systems", "users"
)
LINK_TARGETS = {
  "bom": {"system": "systems", "product": "products"},
  "calculations": {"formula": "formulas", "project": "projects", "system": "systems", "created_by": "users"},
  "catalog_documents": {"product": "products", "series": "catalog_series"},
  "catalog_orders": {"product": "products"},
  "catalog_categories": {"parent": "catalog_categories"},
  "catalog_series": {"category": "catalog_categories"},
  "cms_modules": {"page": "cms_pages"},
  "cms_pages": {"updated_by": "users"},
  "compatibility": {"product": "products", "compatible_product": "products"},
  "crm_clients": {"assigned_to": "users"},
  "crm_contacts": {"client": "crm_clients"},
  "crm_tasks": {"client": "crm_clients", "project": "projects", "assigned_to": "users"},
  "estimate_lines": {"estimate": "estimates", "product": "products"},
  "estimates": {"project": "projects", "updated_by": "users"},
  "formulas": {"updated_by": "users"},
  "gallery_items": {"updated_by": "users"},
  "imports": {"created_by": "users"},
  "import_logs": {"import": "imports"},
  "objects": {"created_by": "users"},
  "product_media": {"product": "products"},
  "product_prices": {"product": "products"},
  "product_sources": {"product": "products"},
  "product_specs": {"product": "products"},
  "product_stock": {"product": "products"},
  "products": {"brand": "brands", "category": "catalog_categories", "subcategory": "catalog_categories", "series": "catalog_series"},
  "projects": {"client": "crm_clients", "object": "objects", "owner": "users"},
  "quotes": {"project": "projects", "client": "crm_clients", "estimate": "estimates"},
  "rooms": {"object": "objects"},
  "service": {"project": "projects", "system": "systems", "product": "products", "assigned_to": "users"},
  "system_components": {"system": "systems", "product": "products", "parent": "system_components"},
  "system_connections": {"system": "systems", "source_component": "system_components", "target_component": "system_components"},
  "system_settings": {"updated_by": "users"},
  "systems": {"project": "projects"},
  "users": {"role": "roles"}
}


class BackupInputError(Exception):
  pass


def _admin_user():
  return Core.get_admin_user()


def _encode_value(value, target=None):
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  if target is not None:
    return {"$type": "ref", "table": target, "id": value.get_id()}
  if isinstance(value, anvil.Media):
    return {
      "$type": "media", "content_type": value.content_type,
      "name": value.name,
      "data": base64.b64encode(value.get_bytes()).decode("ascii")
    }
  if isinstance(value, datetime):
    return {"$type": "datetime", "value": value.isoformat()}
  if isinstance(value, date):
    return {"$type": "date", "value": value.isoformat()}
  if isinstance(value, dict):
    return {"$type": "object", "value": {
      str(key): _encode_value(item) for key, item in value.items()
    }}
  if isinstance(value, (list, tuple)):
    return {"$type": "list", "value": [_encode_value(item) for item in value]}
  raise BackupInputError("В таблице найдено значение неподдерживаемого типа.")


def _decode_value(value):
  if not isinstance(value, dict) or "$type" not in value:
    return value
  kind = value["$type"]
  if kind == "datetime":
    return datetime.fromisoformat(value["value"])
  if kind == "date":
    return date.fromisoformat(value["value"])
  if kind == "media":
    content_type = value.get("content_type")
    name = value.get("name")
    encoded = value.get("data")
    if (
      not isinstance(content_type, str) or not content_type
      or len(content_type) > 120
      or (name is not None and (not isinstance(name, str) or len(name) > 255))
      or not isinstance(encoded, str)
      or len(encoded) > MAX_DATA_BYTES * 2
    ):
      raise BackupInputError("Данные медиафайла в архиве повреждены.")
    content = base64.b64decode(encoded, validate=True)
    if len(content) > MAX_DATA_BYTES:
      raise BackupInputError("Медиафайл в архиве превышает допустимый размер.")
    return anvil.BlobMedia(content_type, content, name=name)
  if kind == "object" and isinstance(value.get("value"), dict):
    return {key: _decode_value(item) for key, item in value["value"].items()}
  if kind == "list" and isinstance(value.get("value"), list):
    return [_decode_value(item) for item in value["value"]]
  if kind == "ref":
    return value
  raise BackupInputError("В архиве найден неизвестный тип значения.")


def _snapshot():
  tables = {}
  row_count = 0
  for table_name in BACKUP_TABLES:
    table = getattr(app_tables, table_name)
    records = []
    for row in table.search():
      values = {}
      for column, value in row:
        if table_name == "users" and column == "remembered_logins":
          continue
        target = LINK_TARGETS.get(table_name, {}).get(column)
        values[column] = _encode_value(value, target=target)
      records.append({"id": row.get_id(), "values": values})
      row_count += 1
      if row_count > MAX_ROWS:
        raise BackupInputError("Встроенный backup поддерживает не более 20 000 строк.")
    tables[table_name] = records
  return tables, row_count


def _canonical_json(value):
  try:
    return json.dumps(
      value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
      allow_nan=False
    ).encode("utf-8")
  except (TypeError, ValueError):
    raise BackupInputError("Архив содержит данные, которые нельзя сериализовать.")


def _archive_string(snapshot):
  raw = _canonical_json(snapshot)
  if len(raw) > MAX_DATA_BYTES:
    raise BackupInputError("Резервная копия превышает лимит 40 МБ до сжатия.")
  digest = hashlib.sha256(raw).hexdigest()
  compressed = gzip.compress(raw, compresslevel=6)
  if len(compressed) > MAX_FILE_BYTES - 1024:
    raise BackupInputError("Зашифрованная резервная копия превысит лимит 20 МБ.")
  envelope = {
    "format": FORMAT_NAME,
    "schema_version": SCHEMA_VERSION,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "sha256": digest,
    "payload": base64.b64encode(compressed).decode("ascii")
  }
  archive = json.dumps(envelope, separators=(",", ":"), allow_nan=False)
  if len(archive.encode("utf-8")) > MAX_FILE_BYTES:
    raise BackupInputError("Резервная копия превышает лимит 20 МБ до шифрования.")
  return archive, digest


def _read_archive(uploaded_file):
  if not isinstance(uploaded_file, anvil.Media):
    raise BackupInputError("Выберите зашифрованный архив HVAC.")
  if uploaded_file.length > MAX_FILE_BYTES:
    raise BackupInputError("Зашифрованный архив превышает лимит 20 МБ.")
  try:
    raw_encrypted = uploaded_file.get_bytes()
    if len(raw_encrypted) > MAX_FILE_BYTES:
      raise BackupInputError("Зашифрованный архив превышает лимит 20 МБ.")
    encrypted = raw_encrypted.decode("utf-8")
    plain = anvil.secrets.decrypt_with_key(BACKUP_SECRET, encrypted)
  except anvil.secrets.SecretError:
    raise BackupInputError("Не удалось расшифровать архив. Проверьте Anvil Secret HVAC_BACKUP_KEY.")
  except UnicodeDecodeError:
    raise BackupInputError("Файл не является архивом HVAC Studio.")
  try:
    envelope = json.loads(plain)
    if not isinstance(envelope, dict):
      raise BackupInputError("Архив повреждён или имеет неподдерживаемую структуру.")
    schema_version = envelope.get("schema_version")
    if (
      envelope.get("format") != FORMAT_NAME
      or isinstance(schema_version, bool)
      or schema_version not in (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION)
    ):
      raise BackupInputError("Формат или версия архива не поддерживается.")
    compressed = base64.b64decode(envelope["payload"], validate=True)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
      raw = stream.read(MAX_DATA_BYTES + 1)
    if len(raw) > MAX_DATA_BYTES:
      raise BackupInputError("Распакованный архив превышает лимит 40 МБ.")
    if hashlib.sha256(raw).hexdigest() != envelope.get("sha256"):
      raise BackupInputError("Контрольная сумма архива не совпала.")
    snapshot = json.loads(raw.decode("utf-8"))
    if schema_version == LEGACY_SCHEMA_VERSION:
      if not isinstance(snapshot, dict) or set(snapshot) != set(LEGACY_BACKUP_TABLES):
        raise BackupInputError("Состав таблиц старого архива не совпадает с версией 1.")
      snapshot["catalog_orders"] = []
      snapshot["import_logs"] = []
  except BackupInputError:
    raise
  except (KeyError, TypeError, ValueError, OSError, EOFError):
    raise BackupInputError("Архив повреждён или имеет неподдерживаемую структуру.")
  return envelope, snapshot


def _validate_snapshot(snapshot):
  if not isinstance(snapshot, dict) or set(snapshot) != set(BACKUP_TABLES):
    return "В архиве отсутствует часть таблиц или присутствуют неизвестные таблицы."
  ids_by_table = {}
  total = 0
  for table_name, records in snapshot.items():
    if not isinstance(records, list):
      return "Данные таблицы «{}» повреждены.".format(table_name)
    ids = set()
    for record in records:
      if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
        return "В таблице «{}» найден некорректный идентификатор.".format(table_name)
      if record["id"] in ids or not isinstance(record.get("values"), dict):
        return "В таблице «{}» повторяются строки или повреждены поля.".format(table_name)
      ids.add(record["id"])
      total += 1
      if total > MAX_ROWS:
        return "В архиве больше 20 000 строк."
    ids_by_table[table_name] = ids
  for table_name, records in snapshot.items():
    for record in records:
      for column, value in record["values"].items():
        target = LINK_TARGETS.get(table_name, {}).get(column)
        if value is None:
          continue
        if target is not None:
          reference_id = value.get("id") if isinstance(value, dict) else None
          if (
            not isinstance(value, dict) or value.get("$type") != "ref"
            or value.get("table") != target
            or not isinstance(reference_id, str)
            or reference_id not in ids_by_table[target]
          ):
            return "Связь «{}.{}» повреждена.".format(table_name, column)
        elif isinstance(value, dict) and value.get("$type") == "ref":
          return "Неожиданная ссылка в поле «{}.{}».".format(table_name, column)
        else:
          try:
            _decode_value(value)
          except (BackupInputError, TypeError, ValueError, KeyError):
            return "Значение «{}.{}» повреждено.".format(table_name, column)
  for record in snapshot["system_connections"]:
    try:
      properties = _decode_value(record["values"].get("properties"))
    except (BackupInputError, TypeError, ValueError, KeyError):
      return "Параметры связи в архиве повреждены."
    if properties is None:
      continue
    if not isinstance(properties, dict):
      return "Параметры связи должны быть JSON-объектом."
    product_id = properties.get("material_product_id")
    if product_id is not None and (
      not isinstance(product_id, str) or product_id not in ids_by_table["products"]
    ):
      return "Ссылка на материал в параметрах связи повреждена."
  return None


def _remap_embedded_ids(table_name, row, row_map):
  if table_name == "system_connections":
    properties = row["properties"] or {}
    product_id = properties.get("material_product_id")
    product = row_map.get(("products", product_id)) if isinstance(product_id, str) else None
    if product is not None:
      properties = dict(properties)
      properties["material_product_id"] = product.get_id()
      row["properties"] = properties
  elif table_name == "bom":
    line_key = row["line_key"]
    if not isinstance(line_key, str):
      return
    parts = line_key.split(":", 3)
    if len(parts) == 2 and parts[0] == "component":
      component = row_map.get(("system_components", parts[1]))
      if component is not None:
        row["line_key"] = "component:" + component.get_id()
    elif len(parts) == 4 and parts[0] == "route":
      source = row_map.get(("system_components", parts[1]))
      target = row_map.get(("system_components", parts[2]))
      if source is not None and target is not None:
        row["line_key"] = "route:{}:{}:{}".format(
          source.get_id(), target.get_id(), parts[3]
        )


@anvil.server.callable(require_user=True)
@Core.admin_guard
def create_database_backup():
  user = _admin_user()
  if user is None:
    return {"ok": False, "message": "Создавать backup может только администратор."}
  try:
    key_exists = bool(anvil.secrets.get_secret(BACKUP_SECRET))
  except anvil.secrets.SecretError:
    key_exists = False
  if not key_exists:
    return {"ok": False, "message": "Добавьте секрет HVAC_BACKUP_KEY в Anvil Secrets перед созданием backup."}
  try:
    tables, row_count = _snapshot()
    plain, digest = _archive_string(tables)
  except BackupInputError as error:
    return {"ok": False, "message": str(error)}
  encrypted = anvil.secrets.encrypt_with_key(BACKUP_SECRET, plain)
  encrypted_bytes = encrypted.encode("utf-8")
  if len(encrypted_bytes) > MAX_FILE_BYTES:
    return {
      "ok": False,
      "message": "Зашифрованная резервная копия превышает лимит 20 МБ. Уменьшите объём данных или используйте внешний способ резервного копирования."
    }
  stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  media = anvil.BlobMedia(
    "application/octet-stream", encrypted_bytes,
    name="hvac-backup-{}.enc".format(stamp)
  )
  return {
    "ok": True, "file": media, "checksum": digest,
    "rows": row_count, "tables": len(tables),
    "message": "Создан зашифрованный архив: {} строк в {} таблицах.".format(row_count, len(tables))
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def inspect_database_backup(uploaded_file):
  if _admin_user() is None:
    return {"ok": False, "message": "Проверять backup может только администратор."}
  try:
    envelope, snapshot = _read_archive(uploaded_file)
  except BackupInputError as error:
    return {"ok": False, "message": str(error)}
  error = _validate_snapshot(snapshot)
  if error:
    return {"ok": False, "message": error}
  return {
    "ok": True,
    "created_at": envelope["created_at"],
    "checksum": envelope["sha256"],
    "tables": len(snapshot),
    "rows": sum(len(rows) for rows in snapshot.values()),
    "message": "Контрольная сумма и структура архива проверены."
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def restore_database_backup(uploaded_file):
  user = _admin_user()
  if user is None:
    return {"ok": False, "message": "Восстанавливать backup может только администратор."}
  try:
    envelope, snapshot = _read_archive(uploaded_file)
  except BackupInputError as error:
    return {"ok": False, "message": str(error)}
  error = _validate_snapshot(snapshot)
  if error:
    return {"ok": False, "message": error}

  row_map = {}
  created = 0
  updated = 0
  for table_name in BACKUP_TABLES:
    table = getattr(app_tables, table_name)
    for record in snapshot[table_name]:
      scalar_values = {
        column: _decode_value(value)
        for column, value in record["values"].items()
        if column not in LINK_TARGETS.get(table_name, {})
      }
      row = table.get_by_id(record["id"])
      if row is None:
        row = table.add_row(**scalar_values)
        created += 1
      else:
        row.update(**scalar_values)
        updated += 1
      row_map[(table_name, record["id"])] = row

  for table_name in BACKUP_TABLES:
    for record in snapshot[table_name]:
      row = row_map[(table_name, record["id"])]
      links = {}
      for column, target in LINK_TARGETS.get(table_name, {}).items():
        value = record["values"].get(column)
        if value is None:
          links[column] = None
        else:
          links[column] = row_map[(target, value["id"])]
      if table_name == "users":
        links.pop("remembered_logins", None)
      if links:
        row.update(**links)
      _remap_embedded_ids(table_name, row, row_map)

  now = datetime.now(timezone.utc)
  Core.log_audit(
    actor=user, action="backup.restored", entity_type="database",
    entity_id="", details={"created": created, "updated": updated,
                            "checksum": envelope["sha256"]},
    created_at=now
  )
  return {
    "ok": True, "created": created, "updated": updated,
    "checksum": envelope["sha256"],
    "message": "Восстановлено: добавлено {}, обновлено {}. Новые строки вне архива не удалялись.".format(created, updated)
  }
