import anvil.secrets
import csv
import base64
from datetime import datetime, timezone
import hashlib
import importlib
import ipaddress
import io
import json
import mimetypes
import math
import posixpath
import re
import tempfile
import time
from typing import Any, cast
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import anvil
import anvil.http
import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import CatalogService as Catalog
import Config
import AI
import AdminStudio
import Analytics


MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_PDF_SOURCE_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 8 * 1024 * 1024
MAX_XLSX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_XLSX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
XLSX_UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024
XLSX_BATCH_PAUSE_SECONDS = 0.2
MAX_XLSX_SHARED_STRINGS_BYTES = 128 * 1024 * 1024
MAX_RECORDS = 2500
BATCH_SIZE = 25
MAX_IMPORT_LOGS = 200
MAX_IMPORT_HISTORY = 100
MAX_ACTIVE_IMPORTS = 5
MAX_PDF_PAGES = 2000
MAX_PDF_BATCH_PAGES = 50
MAX_PDF_TEXT_CHARS = 500000
MAX_PDF_DRAFT_PRODUCTS = 1000
MAX_PDF_IMAGES = 300
MAX_PDF_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PDF_TOTAL_IMAGE_BYTES = 30 * 1024 * 1024
MAX_PDF_DRAFTS = 50
ALLOWED_FORMATS = {"csv", "xlsx", "xml", "json"}
CATEGORY_FIELDS = ("category", "category_code", "категория", "код_категории")
SPEC_FIELDS = {
  "capacity": ("capacity", "capacity_kw", "производительность", "мощность_охлаждения"),
  "airflow": ("airflow", "air_flow", "расход_воздуха"),
  "power": ("power", "input_power", "потребляемая_мощность"),
  "dimensions": ("dimensions", "размеры", "габариты"),
  "weight": ("weight", "масса", "вес"),
  "noise": ("noise", "noise_level", "шум"),
  "refrigerant": ("refrigerant", "хладагент"),
  "efficiency": ("efficiency", "eer", "cop", "эффективность"),
  "connections": ("connections", "подключения", "соединения")
}
FIELD_ALIASES = {
  "brand": ("brand", "manufacturer", "бренд", "производитель"),
  "model": ("model", "model_number", "модель", "обозначение"),
  "sku": ("sku", "part_number", "article", "артикул", "код_товара"),
  "type": ("type", "product_type", "тип", "тип_оборудования"),
  "description": ("description", "описание"),
  "subcategory": ("subcategory", "subcategory_code", "подкатегория", "код_подкатегории"),
  "series": ("series", "series_code", "серия", "код_серии"),
  "specifications": ("specifications", "specs", "характеристики"),
  "image_url": ("image_url", "image", "photo_url", "фото", "изображение"),
  "document_url": ("document_url", "manual_url", "инструкция_url", "документ_url"),
  "document_title": ("document_title", "название_документа", "инструкция"),
  "source_url": ("source_url", "product_url", "url_источника", "ссылка_на_источник"),
  "purchase_price": ("purchase_price", "закупочная_цена"),
  "sale_price": ("sale_price", "price", "цена", "цена_продажи"),
  "special_price": ("special_price", "специальная_цена"),
  "discount": ("discount", "скидка"),
  "markup": ("markup", "наценка"),
  "installation_price": ("installation_price", "цена_монтажа"),
  "currency": ("currency", "валюта"),
  "quantity": ("quantity", "stock", "остаток", "количество"),
  "minimum_stock": ("minimum_stock", "минимальный_остаток")
}


class ImportInputError(Exception):
  pass


def _admin_user():
  return Core.get_admin_user()


def _normal_key(value):
  return re.sub(r"[^a-z0-9а-яё]+", "_", str(value).strip().casefold()).strip("_")


def _value(record, aliases):
  normalized = {_normal_key(key): value for key, value in record.items()}
  for alias in aliases:
    value = normalized.get(_normal_key(alias))
    if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
      return str(value).strip()
    if isinstance(value, bool) and value:
      return "true"
  return ""


def _raw_value(record, aliases):
  normalized = {_normal_key(key): value for key, value in record.items()}
  for alias in aliases:
    key = _normal_key(alias)
    if key in normalized:
      return normalized[key]
  return None


def _decode_text(data):
  try:
    return data.decode("utf-8-sig")
  except UnicodeDecodeError:
    try:
      return data.decode("cp1251")
    except UnicodeDecodeError:
      raise ImportInputError("Файл должен быть в UTF-8 или Windows-1251.")


def _records_csv(data):
  text = _decode_text(data)
  try:
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
  except csv.Error:
    dialect = csv.excel
  return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def _records_json(data):
  try:
    document = json.loads(_decode_text(data))
  except json.JSONDecodeError:
    raise ImportInputError("Проверьте структуру JSON.")
  if isinstance(document, dict):
    for key in ("products", "items", "data"):
      value = document.get(key)
      if isinstance(value, list):
        document = value
        break
      if isinstance(value, dict):
        nested = next((value[name] for name in ("products", "items")
                       if isinstance(value.get(name), list)), None)
        if nested is not None:
          document = nested
          break
    else:
      document = [document]
  if not isinstance(document, list) or any(not isinstance(row, dict) for row in document):
    raise ImportInputError("JSON должен содержать список товарных объектов.")
  return document


def _records_xml(data):
  try:
    root = ET.fromstring(data)
  except ET.ParseError:
    raise ImportInputError("Проверьте структуру XML.")
  record_names = {"product", "item", "offer"}
  elements = [element for element in root.iter()
              if element.tag.rsplit("}", 1)[-1].casefold() in record_names]
  children = elements or ([root] if root.attrib else list(root))
  records = []
  for element in children:
    record = dict(element.attrib)
    for child in list(element):
      if list(child):
        for field in list(child):
          record[field.tag.rsplit("}", 1)[-1]] = field.text or ""
      else:
        record[child.tag.rsplit("}", 1)[-1]] = child.text or ""
    if record:
      records.append(record)
  if not records:
    raise ImportInputError("XML не содержит товарных записей.")
  return records


def _column_number(reference):
  letters = re.match(r"([A-Z]+)", reference)
  if letters is None:
    return 0
  number = 0
  for letter in letters.group(1):
    number = number * 26 + ord(letter) - 64
  return number - 1


def _xlsx_relationships(workbook, relationship_path, base_path):
  try:
    root = ET.fromstring(workbook.read(relationship_path))
  except (KeyError, ET.ParseError):
    return {}
  relationships = {}
  for item in root:
    if item.tag.rsplit("}", 1)[-1] != "Relationship":
      continue
    if item.attrib.get("TargetMode", "").casefold() == "external":
      continue
    target = unquote(item.attrib.get("Target", "")).replace("\\", "/")
    path = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                              else posixpath.join(base_path, target))
    if path.startswith("xl/"):
      relationships[item.attrib.get("Id")] = (item.attrib.get("Type", ""), path)
  return relationships


def _xlsx_images_by_row(workbook, names, sheet_path, drawing_id, image_budget):
  sheet_rels_path = posixpath.join(
    posixpath.dirname(sheet_path), "_rels", posixpath.basename(sheet_path) + ".rels"
  )
  sheet_rels = _xlsx_relationships(
    workbook, sheet_rels_path, posixpath.dirname(sheet_path)
  )
  drawing = sheet_rels.get(drawing_id)
  if drawing is None or not drawing[0].endswith("/drawing"):
    return {}
  drawing_path = drawing[1]
  try:
    if workbook.getinfo(drawing_path).file_size > 64 * 1024 * 1024:
      image_budget["limited"] = True
      return {}
  except KeyError:
    return {}
  drawing_rels_path = posixpath.join(
    posixpath.dirname(drawing_path), "_rels", posixpath.basename(drawing_path) + ".rels"
  )
  image_rels = _xlsx_relationships(
    workbook, drawing_rels_path, posixpath.dirname(drawing_path)
  )
  if drawing_path not in names:
    return {}
  try:
    drawing_root = ET.fromstring(workbook.read(drawing_path))
  except (KeyError, ET.ParseError):
    return {}
  result = {}
  for anchor in drawing_root:
    from_node = next((node for node in anchor
                      if node.tag.rsplit("}", 1)[-1] == "from"), None)
    row_node = next((node for node in from_node or ()
                     if node.tag.rsplit("}", 1)[-1] == "row"), None)
    if row_node is None or not (row_node.text or "").isdigit():
      continue
    row_number = int(row_node.text or "0") + 1
    for image_ref in anchor.iter():
      if image_ref.tag.rsplit("}", 1)[-1] != "blip":
        continue
      relation_id = next((value for key, value in image_ref.attrib.items()
                          if key.rsplit("}", 1)[-1] == "embed"), None)
      image_rel = image_rels.get(relation_id)
      if image_rel is None or not image_rel[0].endswith("/image"):
        continue
      image_path = image_rel[1]
      if image_path not in names:
        continue
      image_data = image_budget["data_by_path"].get(image_path)
      if image_data is None:
        try:
          image_info = workbook.getinfo(image_path)
        except KeyError:
          continue
        if (image_info.file_size < 64 or image_info.file_size > MAX_PDF_IMAGE_BYTES
            or image_budget["count"] >= MAX_PDF_IMAGES
            or image_budget["bytes"] + image_info.file_size > MAX_PDF_TOTAL_IMAGE_BYTES):
          image_budget["limited"] = True
          continue
        image_data = workbook.read(image_path)
        image_budget["count"] += 1
        image_budget["bytes"] += len(image_data)
        image_budget["data_by_path"][image_path] = image_data
      mime_type, _ = _pdf_image_mime(image_data, image_path)
      if mime_type:
        result.setdefault(row_number, []).append({
          "name": posixpath.basename(image_path)[:120],
          "mime_type": mime_type, "data": image_data
        })
  return result


def _xlsx_sheet_rows(workbook, sheet_path):
  try:
    stream = workbook.open(sheet_path)
  except KeyError:
    raise ImportInputError("Рабочий лист XLSX не найден.")
  try:
    with stream:
      stack = []
      for event, element in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
          stack.append(element)
          continue
        if element.tag.rsplit("}", 1)[-1] == "row":
          yield element
          element.clear()
          if len(stack) > 1:
            stack[-2].remove(element)
        stack.pop()
  except ET.ParseError:
    raise ImportInputError("Структура строк рабочего листа XLSX повреждена.")


def _xlsx_drawing_id(workbook, sheet_path):
  try:
    stream = workbook.open(sheet_path)
  except KeyError:
    return None
  drawing_id = None
  try:
    with stream:
      stack = []
      for event, element in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
          stack.append(element)
          continue
        if element.tag.rsplit("}", 1)[-1] == "drawing":
          drawing_id = next((value for key, value in element.attrib.items()
                             if key.rsplit("}", 1)[-1] == "id"), None)
        if element.tag.rsplit("}", 1)[-1] == "row":
          element.clear()
          if len(stack) > 1:
            stack[-2].remove(element)
        stack.pop()
  except ET.ParseError:
    raise ImportInputError("Структура рабочего листа XLSX повреждена.")
  return drawing_id


def _xlsx_cells(row, shared):
  try:
    row_number = int(row.attrib.get("r", "0"))
  except (TypeError, ValueError):
    row_number = 0
  cells = {}
  for cell in list(row):
    if cell.tag.rsplit("}", 1)[-1] != "c":
      continue
    index = _column_number(cell.attrib.get("r", ""))
    value_node = next((part for part in list(cell)
                       if part.tag.rsplit("}", 1)[-1] == "v"), None)
    value = value_node.text if value_node is not None else ""
    if cell.attrib.get("t") == "s" and value is not None:
      try:
        value = shared[int(value)]
      except (ValueError, IndexError):
        value = ""
    elif cell.attrib.get("t") == "inlineStr":
      value = "".join(part.text or "" for part in cell.iter()
                       if part.tag.rsplit("}", 1)[-1] == "t")
    elif cell.attrib.get("t") == "b":
      value = "Да" if value == "1" else "Нет" if value == "0" else value
    cells[index] = value or ""
  return row_number, cells


def _iter_xlsx_records(data):
  try:
    workbook = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
  except (zipfile.BadZipFile, OSError):
    raise ImportInputError("Файл XLSX повреждён.")
  with workbook:
    members = workbook.infolist()
    names = {item.filename for item in members}
    if len(members) > 10000 or sum(item.file_size for item in members) > MAX_XLSX_UNPACKED_BYTES:
      raise ImportInputError("Распакованный XLSX превышает лимит 2 ГБ или содержит слишком много частей.")
    try:
      workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
      relationships_root = ET.fromstring(
        workbook.read("xl/_rels/workbook.xml.rels")
      )
    except (KeyError, ET.ParseError):
      raise ImportInputError("В XLSX повреждены связи с рабочими листами.")
    workbook_rels = {
      item.attrib.get("Id"): item for item in relationships_root
      if item.tag.rsplit("}", 1)[-1] == "Relationship"
    }
    shared = []
    if "xl/sharedStrings.xml" in names:
      if workbook.getinfo("xl/sharedStrings.xml").file_size > MAX_XLSX_SHARED_STRINGS_BYTES:
        raise ImportInputError("Таблица строк XLSX превышает безопасный лимит 128 МБ.")
      try:
        shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
      except ET.ParseError:
        raise ImportInputError("Таблица строк XLSX повреждена.")
      shared = ["".join(part.text or "" for part in item.iter()
                        if part.tag.endswith("}t"))
                for item in shared_root]
    sheets = [item for item in workbook_root.iter()
              if item.tag.rsplit("}", 1)[-1] == "sheet"]
    if not sheets:
      raise ImportInputError("В XLSX нет рабочих листов.")
    image_budget = {"count": 0, "bytes": 0, "limited": False, "data_by_path": {}}
    warning_emitted = False
    record_count = 0
    for sheet_index, sheet_entry in enumerate(sheets, start=1):
      relationship_id = next((
        value for key, value in sheet_entry.attrib.items()
        if key.rsplit("}", 1)[-1] == "id"
      ), None)
      relationship = workbook_rels.get(relationship_id)
      if (relationship is None or not relationship.attrib.get("Type", "").endswith("/worksheet")
          or relationship.attrib.get("TargetMode", "").casefold() == "external"):
        continue
      target = unquote(relationship.attrib.get("Target", "")).replace("\\", "/")
      sheet_path = posixpath.normpath(
        target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
      )
      if not sheet_path.startswith("xl/worksheets/") or sheet_path not in names:
        continue
      sheet_name = str(sheet_entry.attrib.get("name", sheet_index))[:80]
      images_by_row = _xlsx_images_by_row(
        workbook, names, sheet_path, _xlsx_drawing_id(workbook, sheet_path), image_budget
      )
      header = None
      for row in _xlsx_sheet_rows(workbook, sheet_path):
        row_number, cells = _xlsx_cells(row, shared)
        if header is None:
          if not any(str(value).strip() for value in cells.values()):
            continue
          header = [cells.get(index, "") for index in range(max(cells) + 1)]
          continue
        record = {key: cells.get(index, "") for index, key in enumerate(header)
                  if isinstance(key, str) and key.strip()}
        if not any(str(value).strip() for value in record.values()):
          continue
        record["__source_sheet"] = sheet_name
        record["__source_row"] = row_number
        record["__embedded_images"] = images_by_row.get(row_number, [])
        if image_budget["limited"] and not warning_emitted:
          record["__source_warnings"] = [
            "Часть встроенных фотографий XLSX пропущена: лимит 300 изображений или 30 МБ."
          ]
          warning_emitted = True
        record_count += 1
        if record_count > MAX_RECORDS:
          raise ImportInputError("XLSX содержит более {} строк товаров.".format(MAX_RECORDS))
        yield record
  if not record_count:
    raise ImportInputError("В XLSX не найдено строк товаров после строки заголовков.")


def _records_xlsx(data):
  return list(_iter_xlsx_records(data))


def _parse_records(data, format_name):
  try:
    if format_name == "csv":
      records = _records_csv(data)
    elif format_name == "json":
      records = _records_json(data)
    elif format_name == "xml":
      records = _records_xml(data)
    elif format_name == "xlsx":
      records = _records_xlsx(data)
    else:
      raise ImportInputError("Формат источника не поддерживается.")
  except (csv.Error, zipfile.BadZipFile, KeyError):
    raise ImportInputError("Файл каталога повреждён или имеет неподдерживаемую структуру.")
  if not records or len(records) > MAX_RECORDS:
    raise ImportInputError("Источник должен содержать от 1 до 2500 записей.")
  return records


def _remote_url_error(url, resolve_host=False):
  if not isinstance(url, str) or len(url) > 1000:
    return "Укажите HTTPS-адрес длиной до 1000 символов."
  try:
    parts = urlsplit(url.strip())
    hostname = parts.hostname
    port = parts.port
  except ValueError:
    return "Проверьте адрес источника."
  normalized_host = (hostname or "").rstrip(".").casefold()
  if (
    parts.scheme != "https" or not hostname or parts.username or parts.password
    or parts.fragment or parts.query or port not in (None, 443, 8443)
    or normalized_host == "localhost"
    or normalized_host.endswith((".local", ".internal"))
  ):
    return "Источником может быть только публичный HTTPS URL без учётных данных."
  try:
    address = ipaddress.ip_address(normalized_host)
  except ValueError:
    address = None
  if address is not None and not address.is_global:
    return "Источник не может находиться на локальном или служебном IP-адресе."
  if resolve_host and address is None and not Config.is_public_host(hostname, port or 443):
    return "Источник не может разрешаться в локальный или служебный IP-адрес."
  return None


def _read_source(source_type, source_url, media, secret_ref):
  if source_type == "upload":
    if not isinstance(media, anvil.Media):
      raise ImportInputError("Выберите файл для импорта.")
    if media.length > MAX_SOURCE_BYTES:
      raise ImportInputError("Размер файла не должен превышать 2 МБ.")
    data = media.get_bytes()
    filename = media.name or "import"
  else:
    error = _remote_url_error(source_url, resolve_host=True)
    if error:
      raise ImportInputError(error)
    headers = {"Accept": "application/json, application/xml, text/csv, */*"}
    if source_type == "api" and secret_ref:
      if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", secret_ref):
        raise ImportInputError("Проверьте имя секрета API в Anvil Secrets.")
      token = Config.get_secret(secret_ref)
      if not isinstance(token, str) or not token:
        raise ImportInputError("Секрет API не найден в Anvil Secrets.")
      headers["Authorization"] = "Bearer " + token
    try:
      media_result = anvil.http.request(
        source_url, method="GET", headers=headers, timeout=12
      )
    except anvil.http.HttpError as error:
      raise ImportInputError("Источник вернул HTTP {}.".format(error.status))
    if media_result.length > MAX_SOURCE_BYTES:
      raise ImportInputError("Источник превышает лимит 2 МБ.")
    data = media_result.get_bytes()
    filename = urlsplit(source_url).path.rsplit("/", 1)[-1] or "feed.json"
  if not isinstance(data, bytes) or len(data) > MAX_SOURCE_BYTES:
    raise ImportInputError("Источник превышает лимит 2 МБ.")
  return data, filename


def _format_for(requested, filename):
  if requested in ALLOWED_FORMATS:
    return requested
  extension = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
  if extension in ALLOWED_FORMATS:
    return extension
  raise ImportInputError("Выберите формат CSV, XLSX, XML или JSON.")


def _preview_token(data, format_name):
  return hashlib.sha256(
    data + b"\x00catalog-preview\x00" + format_name.encode("ascii")
  ).hexdigest()


def _record_key(record):
  brand = _value(record, FIELD_ALIASES["brand"]).casefold()
  model = _value(record, FIELD_ALIASES["model"]).casefold()
  sku = _value(record, FIELD_ALIASES["sku"]).casefold()
  if brand and model:
    return "model", brand + "|" + model
  return ("sku", sku) if sku else None


def _duplicate_indexes(records):
  seen = set()
  duplicates = set()
  for index, record in enumerate(records):
    key = _record_key(record)
    if key is not None and key in seen:
      duplicates.add(index)
    elif key is not None:
      seen.add(key)
  return duplicates


def _number(value, label, maximum=None):
  if value == "":
    return None, None
  try:
    parsed = float(value.replace(" ", "").replace(",", "."))
  except ValueError:
    return None, "Поле «{}» должно быть числом.".format(label)
  if not math.isfinite(parsed) or parsed < 0 or (maximum is not None and parsed > maximum):
    return None, "Поле «{}» вне допустимого диапазона.".format(label)
  return parsed, None


def _match_category(value, categories, root=None):
  normalized = value.strip().casefold()
  if not normalized:
    return None

  def is_under_root(row):
    if root is None:
      return True
    parent = row["parent"]
    while parent is not None:
      if parent.get_id() == root.get_id():
        return True
      parent = parent["parent"]
    return False

  path_parts = [part.strip().casefold() for part in re.split(
    r"\s*(?:[/\\>|→»]+|::)\s*", value
  ) if part.strip()]
  if not path_parts:
    return None
  matches = [row for row in categories
             if ((row["code"] or "").casefold() == path_parts[-1]
                 or (row["title"] or "").casefold() == path_parts[-1])
             and is_under_root(row)]
  if len(matches) == 1:
    return matches[0]
  for ancestor_title in reversed(path_parts[:-1]):
    scoped = []
    for row in matches:
      parent = row["parent"]
      while parent is not None:
        if ((parent["code"] or "").casefold() == ancestor_title
            or (parent["title"] or "").casefold() == ancestor_title):
          scoped.append(row)
          break
        parent = parent["parent"]
    matches = scoped
    if len(matches) == 1:
      return matches[0]
  return matches[0] if len(matches) == 1 else None


def _prepare_record(record, categories, source_name, source_url, series_rows=None):
  brand = _value(record, FIELD_ALIASES["brand"])
  model = _value(record, FIELD_ALIASES["model"])
  if not model or len(model) > 120 or len(brand) > 80:
    return None, "Для товара нужна модель; длина не должна превышать 120 символов."
  sku = _value(record, FIELD_ALIASES["sku"])
  if not brand and not sku:
    return None, "Для поиска дублей укажите бренд или артикул."
  product_type = _value(record, FIELD_ALIASES["type"])
  description = _value(record, FIELD_ALIASES["description"])
  if len(sku) > 80 or len(product_type) > 80 or len(description) > 2000:
    return None, "Одно из текстовых полей товара превышает допустимую длину."

  category_value = _value(record, CATEGORY_FIELDS)
  category = _match_category(category_value, categories)
  subcategory_value = _value(record, FIELD_ALIASES["subcategory"])
  subcategory = None
  if category is not None and category["parent"] is not None:
    subcategory = category
    while category["parent"] is not None:
      category = category["parent"]
  if subcategory_value:
    subcategory = _match_category(subcategory_value, categories, category)
    if subcategory is None:
      return None, "Подкатегория не найдена внутри указанной категории."
  if category is None or category["parent"] is not None or not category["active"]:
    return None, "Укажите существующую активную категорию каталога."

  series_value = _value(record, FIELD_ALIASES["series"])
  series = None
  if series_value:
    if series_rows is None:
      series_rows = list(app_tables.catalog_series.search(active=True))
    series_scope = subcategory or category
    series_matches = []
    for row in series_rows:
      if (row["code"] or "").casefold() != series_value.casefold() and (
        row["title"] or ""
      ).casefold() != series_value.casefold():
        continue
      linked_category = row["category"]
      if linked_category is not None and cast(Any, Catalog)._category_is_within(
        linked_category, series_scope
      ):
        series_matches.append(row)
    if len(series_matches) != 1:
      return None, "Серия не найдена или неоднозначна внутри выбранной категории."
    series = series_matches[0]

  image_url = _value(record, FIELD_ALIASES["image_url"])
  if image_url:
    error = _remote_url_error(image_url)
    if error:
      return None, "Фото товара должно быть публичной HTTPS-ссылкой."
  document_url = _value(record, FIELD_ALIASES["document_url"])
  if document_url:
    error = _remote_url_error(document_url)
    if error:
      return None, "Документ должен быть доступен по публичной HTTPS-ссылке."
  document_title = _value(record, FIELD_ALIASES["document_title"])
  if len(document_title) > 120:
    return None, "Название документа не должно превышать 120 символов."

  prices = {}
  for field in ("purchase_price", "sale_price", "special_price", "discount", "markup", "installation_price"):
    aliases = FIELD_ALIASES[field]
    raw = _value(record, aliases)
    if raw:
      amount, error = _number(raw, field, 100 if field == "discount" else None)
      if error:
        return None, error
      prices[field] = amount
  currency = _value(record, FIELD_ALIASES["currency"]).upper()
  if currency and (len(currency) != 3 or not currency.isascii() or not currency.isalpha()):
    return None, "Код валюты должен содержать три латинские буквы."
  if currency:
    prices["currency"] = currency

  stock = {}
  for field in ("quantity", "minimum_stock"):
    raw = _value(record, FIELD_ALIASES[field])
    if raw:
      amount, error = _number(raw, field)
      if error:
        return None, error
      stock[field] = amount

  specs = {}
  for field, aliases in SPEC_FIELDS.items():
    value = _value(record, aliases)
    if value:
      if len(value) > 200:
        return None, "Характеристика «{}» слишком длинная.".format(field)
      specs[field] = value
  imported_spec_units = {}
  raw_specs = _raw_value(record, FIELD_ALIASES["specifications"])
  if raw_specs not in (None, ""):
    if isinstance(raw_specs, str):
      try:
        raw_specs = json.loads(raw_specs)
      except json.JSONDecodeError:
        return None, "Поле характеристик должно содержать корректный JSON-объект."
    if not isinstance(raw_specs, dict) or len(raw_specs) > 100:
      return None, "Характеристики должны быть JSON-объектом не более чем из 100 строк."
    for raw_key, raw_spec in raw_specs.items():
      if not isinstance(raw_key, str) or not raw_key.strip() or len(raw_key.strip()) > 80:
        return None, "Проверьте названия импортируемых характеристик."
      if isinstance(raw_spec, dict):
        raw_value = raw_spec.get("value", "")
        raw_unit = raw_spec.get("unit", "")
      else:
        raw_value, raw_unit = raw_spec, ""
      if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
        return None, "Значения характеристик должны быть текстом или числом."
      value_text = str(raw_value).strip()
      unit_text = str(raw_unit).strip() if isinstance(raw_unit, str) else ""
      if not value_text or len(value_text) > 200 or len(unit_text) > 32:
        return None, "Проверьте длину значения и единицы характеристики."
      specs[raw_key.strip()] = value_text
      imported_spec_units[raw_key.strip()] = unit_text
  spec_units = {}
  for field, aliases in {
    "capacity": ("capacity_unit", "unit", "единица_измерения"),
    "airflow": ("airflow_unit", "air_flow_unit", "единица_расхода_воздуха"),
    "power": ("power_unit", "единица_мощности"),
    "weight": ("weight_unit", "единица_массы"),
    "noise": ("noise_unit", "единица_шума")
  }.items():
    spec_units[field] = _value(record, aliases)
  spec_units.update(imported_spec_units)
  source_url_value = _value(record, FIELD_ALIASES["source_url"]) or source_url
  if source_url_value:
    error = _remote_url_error(source_url_value)
    if error:
      return None, "Ссылка на источник товара должна быть публичным HTTPS URL."
  return {
    "brand": brand, "model": model, "sku": sku,
    "type": product_type, "description": description,
    "category": category, "subcategory": subcategory,
    "series": series, "image_url": image_url,
    "document_url": document_url, "document_title": document_title,
    "prices": prices, "stock": stock, "specs": specs, "spec_units": spec_units,
    "source_url": source_url_value, "source_name": source_name
  }, None


def _upsert_values(table, product, values, now):
  row = table.get(product=product)
  changes = {key: value for key, value in values.items()
             if key != "updated_at"
             and (row is None or row[key] != value)}
  if not changes:
    return False
  if row is None:
    table.add_row(product=product, **values, updated_at=now)
  else:
    row.update(**changes, updated_at=now)
  return True


def _source_version(checkpoint):
  if not isinstance(checkpoint, dict):
    return ""
  digest = checkpoint.get("sha256", "")
  return "sha256:" + digest if isinstance(digest, str) and re.fullmatch(
    r"[a-f0-9]{64}", digest
  ) else ""


def _apply_record(record, categories, import_row, source_url, now, series_rows=None):
  prepared, error = _prepare_record(
    record, categories, import_row["source_name"], source_url, series_rows
  )
  if error:
    return "skipped", error
  brand_name = prepared["brand"]
  brand_key = brand_name.casefold()
  brand = app_tables.brands.get(name_key=brand_key) if brand_name else None
  sku_key = prepared["sku"].casefold()
  identity_key, product = Catalog.find_import_product(
    brand_name, prepared["model"], prepared["sku"]
  )
  if product is not None and not brand_name:
    existing_brand = product["brand"]
    if existing_brand is not None:
      brand = existing_brand
      brand_key = existing_brand["name_key"]
      identity_key = Catalog.product_identity_key(
        existing_brand["name"], prepared["model"], prepared["sku"]
      )
  identity_owner = app_tables.products.get(identity_key=identity_key)
  if identity_owner is not None and product is not None and identity_owner.get_id() != product.get_id():
    return "skipped", "Модель и артикул указывают на разные товары каталога."
  sku_owner = app_tables.products.get(sku_key=sku_key) if sku_key else None
  if sku_owner is not None and product is not None and sku_owner.get_id() != product.get_id():
    return "skipped", "Артикул уже связан с другой моделью."
  if brand_name and brand is None:
    brand = app_tables.brands.add_row(name=brand_name, name_key=brand_key)

  is_new = product is None
  current_subcategory = product["subcategory"] if product is not None else None
  subcategory = prepared["subcategory"]
  if product is not None and subcategory is None and current_subcategory is not None:
    current_parent = current_subcategory["parent"]
    if current_parent is not None and current_parent.get_id() == prepared["category"].get_id():
      subcategory = current_subcategory
  current_sku = product["sku"] if product is not None else ""
  final_sku = prepared["sku"] or current_sku or ""
  product_values = {
    "identity_key": identity_key, "brand": brand, "model": prepared["model"],
    "sku": final_sku, "sku_key": final_sku.casefold(),
    "category": prepared["category"], "subcategory": subcategory,
    "type": prepared["type"] or (product["type"] if product is not None else ""),
    "description": prepared["description"] or (product["description"] if product is not None else ""),
    "active": True
  }
  if prepared["series"] is not None:
    product_values["series"] = prepared["series"]
  elif product is not None and product["series"] is not None:
    product_values["series"] = product["series"]
  if product is None:
    product = app_tables.products.add_row(**product_values, updated_at=now)
    changed = True
  else:
    changes = {key: value for key, value in product_values.items()
               if value is not None and product[key] != value}
    if changes:
      product.update(**changes, updated_at=now)
      changed = True
    else:
      changed = False

  if prepared["prices"]:
    prices = dict(prepared["prices"])
    prices.setdefault("currency", Core.get_currency())
    changed = _upsert_values(app_tables.product_prices, product, prices, now) or changed
  if prepared["stock"]:
    changed = _upsert_values(app_tables.product_stock, product, prepared["stock"], now) or changed
  source_values = {
    "url": prepared["source_url"], "publisher": prepared["source_name"],
    "version": _source_version(import_row["checkpoint"] or {}),
    "checked_at": now
  }
  if any(source_values[key] for key in ("url", "publisher")):
    source_row = next(iter(app_tables.product_sources.search(product=product)), None)
    if source_row is None:
      app_tables.product_sources.add_row(product=product, **source_values)
      changed = True
    else:
      source_changes = {key: value for key, value in source_values.items()
                        if key != "checked_at" and value and source_row[key] != value}
      if source_changes:
        source_row.update(**source_changes, checked_at=now)
        changed = True
  for key, value in prepared["specs"].items():
    spec = app_tables.product_specs.get(product=product, key_key=key.casefold())
    spec_values = {
      "key": key, "key_key": key.casefold(), "value": value,
      "unit": prepared["spec_units"].get(key, ""),
      "source": prepared["source_url"] or prepared["source_name"]
    }
    if spec is None:
      app_tables.product_specs.add_row(product=product, **spec_values, updated_at=now)
      changed = True
    else:
      spec_changes = {field: value for field, value in spec_values.items()
                      if value and spec[field] != value}
      if spec_changes:
        spec.update(**spec_changes, updated_at=now)
        changed = True
  image_url = prepared["image_url"]
  if image_url:
    media_rows = list(app_tables.product_media.search(
      q.fetch_only("file", "url", "is_primary", "type"), product=product
    ))
    current_primary = next((
      row for row in media_rows
      if row["is_primary"] or (row["type"] or "").casefold() in ("primary", "main", "cover", "hero")
    ), None)
    if current_primary is None:
      app_tables.product_media.add_row(
        product=product, file=None, url=image_url, type="primary",
        is_primary=True, sort_order=0,
        alt_text="{} {}".format(brand_name, prepared["model"]).strip(),
        source=prepared["source_url"] or prepared["source_name"],
        created_at=now
      )
      changed = True
    elif current_primary["file"] is None and current_primary["url"] != image_url:
      current_primary.update(url=image_url, is_primary=True, type="primary")
      changed = True
  document_url = prepared["document_url"]
  if document_url and next(iter(app_tables.catalog_documents.search(
    product=product, url=document_url
  )), None) is None:
    cast(Any, app_tables.catalog_documents).add_row(
      title=prepared["document_title"] or "Документация модели",
      kind="instruction", product=product, series=None, file=None,
      url=document_url, sort_order=0, created_at=now
    )
    changed = True
  return ("imported", None) if changed or is_new else ("skipped", "Данные товара не изменились.")


def _log(import_row, level, message, record_number=None):
  values = {
    "import": import_row, "level": level, "message": message[:240],
    "record_number": record_number, "details": {},
    "created_at": datetime.now(timezone.utc)
  }
  app_tables.import_logs.add_row(**values)  # type: ignore[call-arg]
  if record_number is None:
    _trim_import_logs(import_row)


def _trim_import_logs(import_row):
  rows = list(app_tables.import_logs.search(
    order_by("created_at"), **{"import": import_row}
  )[:MAX_IMPORT_LOGS + BATCH_SIZE + 1])
  excess = min(len(rows) - MAX_IMPORT_LOGS, BATCH_SIZE + 1)
  for old in rows[:max(0, excess)]:
    old.delete()


def _trim_import_history():
  for status in ("completed", "source_changed", "failed", "paused"):
    rows = list(app_tables.imports.search(
      order_by("created_at"), status=status
    )[:MAX_IMPORT_HISTORY + 1])
    if len(rows) <= MAX_IMPORT_HISTORY:
      continue
    old_import = rows[0]
    for log in app_tables.import_logs.search(**{"import": old_import}):
      log.delete()
    old_import.delete()


def _has_active_import_capacity():
  active = 0
  for status in ("draft", "running", "pdf_processing", "xlsx_uploading", "xlsx_processing",
                 "xlsx_images_processing"):
    rows = list(app_tables.imports.search(
      q.fetch_only("status"), status=status
    )[:MAX_ACTIVE_IMPORTS + 1])
    active += len(rows)
  return active < MAX_ACTIVE_IMPORTS


def _process_batch(import_row, records):
  checkpoint = import_row["checkpoint"] or {}
  offset = int(checkpoint.get("offset", 0))
  duplicate_indexes = _duplicate_indexes(records)
  Catalog.ensure_catalog_categories()
  categories = list(app_tables.catalog_categories.search(active=True))
  series_rows = list(app_tables.catalog_series.search(active=True))
  batch = records[offset:offset + BATCH_SIZE]
  now = datetime.now(timezone.utc)
  imported = 0
  skipped = 0
  for index, record in enumerate(batch, start=offset):
    if index in duplicate_indexes:
      skipped += 1
      _log(import_row, "warning", "Повторная запись источника пропущена.", index + 1)
      continue
    state, message = _apply_record(
      record, categories, import_row, import_row["source_url"] or "", now,
      series_rows
    )
    if state == "imported":
      imported += 1
    else:
      skipped += 1
      _log(import_row, "warning", message or "Запись пропущена.", index + 1)
  _trim_import_logs(import_row)
  processed = offset + len(batch)
  done = processed >= len(records)
  import_row.update(
    checkpoint={"offset": processed, "sha256": checkpoint["sha256"],
                "format": checkpoint["format"],
                "secret_ref": checkpoint.get("secret_ref", "")},
    total=len(records), processed=processed,
    imported=(import_row["imported"] or 0) + imported,
    skipped=(import_row["skipped"] or 0) + skipped,
    status="completed" if done else "running",
    updated_at=now
  )
  return {
    "ok": True, "import_id": import_row.get_id(), "status": import_row["status"],
    "total": import_row["total"], "processed": processed,
    "imported": import_row["imported"], "skipped": import_row["skipped"],
    "has_more": not done,
    "message": "Пакет обработан: {} из {}.".format(processed, len(records))
  }


def _execute_import(import_row, media=None):
  checkpoint = import_row["checkpoint"] or {}
  try:
    data, filename = _read_source(
      import_row["source_type"], import_row["source_url"] or "", media,
      checkpoint.get("secret_ref", "")
    )
    digest = hashlib.sha256(data).hexdigest()
    if checkpoint.get("sha256") and digest != checkpoint["sha256"]:
      import_row.update(status="source_changed", updated_at=datetime.now(timezone.utc))
      return {"ok": False, "message": "Источник изменился. Создайте новый импорт для актуальных данных."}
    format_name = checkpoint.get("format") or _format_for(import_row["format"], filename)
    preview_token = checkpoint.get("preview_token")
    if preview_token and preview_token != _preview_token(data, format_name):
      return {
        "ok": False,
        "message": "Файл или источник изменился после предпросмотра. Проверьте данные ещё раз."
      }
    records = _parse_records(data, format_name)
  except ImportInputError as error:
    return {"ok": False, "message": str(error)}
  except anvil.http.HttpError as error:
    return {"ok": False, "message": "Источник вернул HTTP {}.".format(error.status)}
  if not checkpoint.get("sha256"):
    checkpoint.update({"sha256": digest, "format": format_name, "offset": 0})
    import_row.update(checkpoint=checkpoint, total=len(records), status="running")
  return _process_batch(import_row, records)


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def preview_product_import(source_type, source_name, source_url="", format_name="auto",
                           secret_ref="", uploaded_file=None):
  Core.require_permission("import.manage")
  if source_type not in ("upload", "url", "api"):
    return {"ok": False, "message": "Выберите файл, URL feed или API."}
  if not isinstance(source_name, str) or not source_name.strip() or len(source_name) > 120:
    return {"ok": False, "message": "Укажите название источника до 120 символов."}
  if not isinstance(format_name, str) or (
    format_name != "auto" and format_name not in ALLOWED_FORMATS
  ):
    return {"ok": False, "message": "Выберите CSV, XLSX, XML, JSON или автоопределение."}
  if source_type == "upload" and not isinstance(uploaded_file, anvil.Media):
    return {"ok": False, "message": "Выберите файл для предпросмотра."}
  if source_type in ("url", "api"):
    error = _remote_url_error(source_url, resolve_host=True)
    if error:
      return {"ok": False, "message": error}
  if source_type != "api":
    secret_ref = ""
  if not isinstance(secret_ref, str) or len(secret_ref) > 80:
    return {"ok": False, "message": "Проверьте имя секрета API."}
  try:
    data, filename = _read_source(source_type, source_url, uploaded_file, secret_ref)
    resolved_format = _format_for(format_name, filename)
    records = _parse_records(data, resolved_format)
  except ImportInputError as error:
    return {"ok": False, "message": str(error)}
  except anvil.http.HttpError as error:
    return {"ok": False, "message": "Источник вернул HTTP {}.".format(error.status)}

  Catalog.ensure_catalog_categories()
  categories = list(app_tables.catalog_categories.search(active=True))
  series_rows = list(app_tables.catalog_series.search(active=True))
  duplicate_indexes = _duplicate_indexes(records)
  preview_rows = []
  for index, record in enumerate(records[:25]):
    prepared, error = _prepare_record(
      record, categories, source_name.strip(), source_url or "", series_rows
    )
    if error:
      status, message = "Ошибка", error
      brand = _value(record, FIELD_ALIASES["brand"])
      model = _value(record, FIELD_ALIASES["model"])
      sku = _value(record, FIELD_ALIASES["sku"])
      category = ""
      sale_price = _value(record, FIELD_ALIASES["sale_price"])
    elif index in duplicate_indexes:
      status, message = "Дубль файла", "Такая модель или артикул повторяется в исходнике."
      brand, model, sku = prepared["brand"], prepared["model"], prepared["sku"]
      category = prepared["subcategory"]["title"] if prepared["subcategory"] is not None else prepared["category"]["title"]
      sale_price = prepared["prices"].get("sale_price")
    else:
      _, existing = Catalog.find_import_product(
        prepared["brand"], prepared["model"], prepared["sku"]
      )
      status = "Обновление" if existing is not None else "Создание"
      message = "Товар будет обновлён." if existing is not None else "Будет создан товар."
      brand, model, sku = prepared["brand"], prepared["model"], prepared["sku"]
      category = prepared["subcategory"]["title"] if prepared["subcategory"] is not None else prepared["category"]["title"]
      sale_price = prepared["prices"].get("sale_price")
    preview_rows.append({
      "line": record.get("__source_row", index + 2), "brand": brand, "model": model, "sku": sku,
      "category": category,
      "sale_price": "" if sale_price is None else str(sale_price),
      "status": status, "message": message
    })

  source_headers = [header for header in records[0].keys()
                    if not (isinstance(header, str) and header.startswith("__"))]
  mapping_aliases = dict(FIELD_ALIASES)
  mapping_aliases["category"] = CATEGORY_FIELDS
  mapping = []
  for field, aliases in mapping_aliases.items():
    alias_keys = {_normal_key(alias) for alias in aliases}
    source_column = next((
      header for header in source_headers if _normal_key(header) in alias_keys
    ), "")
    if source_column:
      mapping.append({"field": field, "source_column": str(source_column)[:100]})
  invalid_count = sum(row["status"] == "Ошибка" for row in preview_rows)
  duplicate_count = sum(row["status"] == "Дубль файла" for row in preview_rows)
  return {
    "ok": True,
    "preview_token": _preview_token(data, resolved_format),
    "format": resolved_format,
    "total": len(records),
    "preview_rows": preview_rows,
    "mapping": mapping,
    "has_more_preview": len(records) > len(preview_rows),
    "message": "Записей: {} · в просмотре ошибок: {} · дублей: {}{}".format(
      len(records), invalid_count, duplicate_count,
      " · показаны первые 25" if len(records) > len(preview_rows) else ""
    )
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def start_product_import(source_type, source_name, source_url="", format_name="auto",
                         secret_ref="", uploaded_file=None, preview_token=None):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if source_type not in ("upload", "url", "api"):
    return {"ok": False, "message": "Выберите файл, URL feed или API."}
  if not isinstance(source_name, str) or not source_name.strip() or len(source_name) > 120:
    return {"ok": False, "message": "Укажите название источника до 120 символов."}
  if not isinstance(format_name, str) or (
    format_name != "auto" and format_name not in ALLOWED_FORMATS
  ):
    return {"ok": False, "message": "Выберите CSV, XLSX, XML, JSON или автоопределение."}
  if not isinstance(preview_token, str) or not re.fullmatch(r"[a-f0-9]{64}", preview_token):
    return {"ok": False, "message": "Перед импортом сначала проверьте предпросмотр файла."}
  if source_type == "upload" and not isinstance(uploaded_file, anvil.Media):
    return {"ok": False, "message": "Выберите файл для импорта."}
  if source_type in ("url", "api"):
    error = _remote_url_error(source_url)
    if error:
      return {"ok": False, "message": error}
  if source_type != "api":
    secret_ref = ""
  if not isinstance(secret_ref, str) or len(secret_ref) > 80:
    return {"ok": False, "message": "Проверьте имя секрета API."}
  if not _has_active_import_capacity():
    return {
      "ok": False,
      "message": "Одновременно можно вести не более пяти импортов. Продолжите checkpoint или дождитесь завершения активного импорта."
    }

  _trim_import_history()
  now = datetime.now(timezone.utc)
  import_row = app_tables.imports.add_row(
    source_type=source_type, source_name=source_name.strip(),
    source_url=source_url.strip() if source_type in ("url", "api") else "",
    format=format_name, status="draft",
    checkpoint={
      "offset": 0, "format": "", "sha256": "",
      "secret_ref": secret_ref, "preview_token": preview_token
    },
    total=0, processed=0, imported=0, skipped=0,
    created_by=user, created_at=now, updated_at=now
  )
  result = _execute_import(import_row, uploaded_file)
  if not result["ok"]:
    import_row.update(status="failed", updated_at=datetime.now(timezone.utc))
    _log(import_row, "error", result["message"])
  return result


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def resume_product_import(import_id, uploaded_file=None):
  Core.require_permission("import.manage")
  if not isinstance(import_id, str) or not import_id:
    return {"ok": False, "message": "Выберите импорт для продолжения."}
  import_row = app_tables.imports.get_by_id(import_id)
  if import_row is None:
    return {"ok": False, "message": "Импорт не найден."}
  if import_row["status"] == "completed":
    return {"ok": False, "message": "Этот импорт уже завершён."}
  if import_row["status"] == "source_changed":
    return {"ok": False, "message": "Создайте новый импорт для изменившегося источника."}
  result = _execute_import(import_row, uploaded_file)
  if not result["ok"]:
    if import_row["status"] != "source_changed":
      import_row.update(status="paused", updated_at=datetime.now(timezone.utc))
    _log(import_row, "error", result["message"])
  return result


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def get_product_imports():
  Core.require_permission("import.manage")
  fields = q.fetch_only(
    "source_type", "source_name", "format", "status", "total", "processed",
    "imported", "skipped", "created_at"
  )
  recent_rows = list(app_tables.imports.search(
    fields,
    order_by("created_at", ascending=False)
  )[:30])
  recent_rows = [row for row in recent_rows if row["format"] != "pdf"]
  active_rows = []
  for status in ("running", "draft", "paused"):
    active_rows.extend(app_tables.imports.search(
      fields, order_by("created_at", ascending=False), status=status
    )[:MAX_IMPORT_HISTORY if status == "paused" else MAX_ACTIVE_IMPORTS + 1])
  active_rows = [row for row in active_rows if row["format"] != "pdf"]
  active_ids = {row.get_id() for row in active_rows}
  active_rows.sort(key=lambda row: row["created_at"] or datetime.min.replace(
    tzinfo=timezone.utc
  ), reverse=True)
  rows = active_rows[:30]
  rows.extend([
    row for row in recent_rows if row.get_id() not in active_ids
  ][:max(0, 30 - len(rows))])
  return {"ok": True, "rows": [
    {"id": row.get_id(), "source_type": row["source_type"],
     "source_name": row["source_name"], "status": row["status"],
     "total": row["total"] or 0, "processed": row["processed"] or 0,
     "imported": row["imported"] or 0, "skipped": row["skipped"] or 0,
     "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M UTC")
     if row["created_at"] else ""}
    for row in rows
  ]}


def _pdf_image_mime(data, name=""):
  if data.startswith(b"\xff\xd8\xff"):
    return "image/jpeg", ".jpg"
  if data.startswith(b"\x89PNG\r\n\x1a\n"):
    return "image/png", ".png"
  if data.startswith((b"GIF87a", b"GIF89a")):
    return "image/gif", ".gif"
  if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
    return "image/webp", ".webp"
  mime_type, _ = mimetypes.guess_type(name or "")
  if mime_type in ("image/jpeg", "image/png", "image/webp", "image/gif"):
    return mime_type, mimetypes.guess_extension(mime_type) or ".jpg"
  return "", ""


def _cloudinary_settings():
  cloud_name = Config.get_secret("CLOUDINARY_CLOUD_NAME")
  api_key = Config.get_secret("CLOUDINARY_API_KEY")
  api_secret = Config.get_secret("CLOUDINARY_API_SECRET")
  if not isinstance(cloud_name, str) or not cloud_name.strip():
    return None
  if not isinstance(api_key, str) or not api_key.strip():
    return None
  if not isinstance(api_secret, str) or not api_secret.strip():
    return None
  if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cloud_name):
    raise ImportInputError("Проверьте имя облака Cloudinary в секретах Anvil.")
  if len(api_key) > 120 or len(api_secret) > 240:
    raise ImportInputError("Проверьте ключи Cloudinary в секретах Anvil.")
  return cloud_name, api_key, api_secret


def _cloudinary_upload(data, mime_type, import_id, digest):
  settings = _cloudinary_settings()
  if settings is None:
    return None
  cloud_name, api_key, api_secret = settings
  timestamp = str(int(datetime.now(timezone.utc).timestamp()))
  folder = "catalog/pdf-imports/" + re.sub(r"[^A-Za-z0-9_-]", "", str(import_id))[:80]
  public_id = digest[:48]
  signed_values = {"folder": folder, "public_id": public_id, "timestamp": timestamp}
  signature_text = "&".join(
    "{}={}".format(key, signed_values[key]) for key in sorted(signed_values)
  ) + api_secret
  signature = hashlib.sha1(signature_text.encode("utf-8")).hexdigest()
  boundary = "----AnvilPdfUpload{}".format(digest[:24])
  fields = {
    "api_key": api_key, "timestamp": timestamp, "folder": folder,
    "public_id": public_id, "signature": signature
  }
  parts = []
  for key, value in fields.items():
    parts.extend([
      "--" + boundary,
      'Content-Disposition: form-data; name="{}"'.format(key), "", str(value)
    ])
  extension = mimetypes.guess_extension(mime_type) or ".img"
  filename = digest[:24] + extension
  parts.extend([
    "--" + boundary,
    'Content-Disposition: form-data; name="file"; filename="{}"'.format(filename),
    "Content-Type: " + mime_type, ""
  ])
  body = ("\r\n".join(parts) + "\r\n").encode("utf-8") + data + (
    "\r\n--{}--\r\n".format(boundary).encode("ascii")
  )
  request = Request(
    "https://api.cloudinary.com/v1_1/{}/image/upload".format(cloud_name),
    data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
    method="POST"
  )
  try:
    with urlopen(request, timeout=45) as response:
      result = json.loads(response.read(1024 * 1024).decode("utf-8"))
  except HTTPError as error:
    raise ImportInputError("Cloudinary отклонил изображение (HTTP {}).".format(error.code))
  except (URLError, TimeoutError, OSError):
    raise ImportInputError("Не удалось связаться с Cloudinary. Проверьте настройки облака.")
  except (UnicodeDecodeError, json.JSONDecodeError):
    raise ImportInputError("Cloudinary вернул неподдерживаемый ответ.")
  secure_url = result.get("secure_url") if isinstance(result, dict) else None
  if not isinstance(secure_url, str) or not secure_url.startswith("https://"):
    raise ImportInputError("Cloudinary не вернул защищённую ссылку на изображение.")
  return secure_url


def _imagekit_settings():
  private_key = Config.get_secret("IMAGEKIT_PRIVATE_KEY")
  if not isinstance(private_key, str) or not private_key.strip():
    return None
  if len(private_key) > 240:
    raise ImportInputError("Проверьте IMAGEKIT_PRIVATE_KEY в Anvil Secrets.")
  return private_key.strip()


def _imagekit_upload(data, mime_type, import_id, digest):
  private_key = _imagekit_settings()
  if private_key is None:
    return None
  boundary = "----AnvilImageKitUpload{}".format(digest[:24])
  folder = "/catalog/pdf-imports/" + re.sub(r"[^A-Za-z0-9_-]", "", str(import_id))[:80]
  extension = mimetypes.guess_extension(mime_type) or ".img"
  filename = digest[:48] + extension
  fields = {
    "fileName": filename, "folder": folder,
    "useUniqueFileName": "false"
  }
  parts = []
  for key, value in fields.items():
    parts.extend([
      "--" + boundary,
      'Content-Disposition: form-data; name="{}"'.format(key), "", value
    ])
  parts.extend([
    "--" + boundary,
    'Content-Disposition: form-data; name="file"; filename="{}"'.format(filename),
    "Content-Type: " + mime_type, ""
  ])
  body = ("\r\n".join(parts) + "\r\n").encode("utf-8") + data + (
    "\r\n--{}--\r\n".format(boundary).encode("ascii")
  )
  authorization = base64.b64encode((private_key + ":").encode("utf-8")).decode("ascii")
  request = Request(
    "https://upload.imagekit.io/api/v1/files/upload", data=body,
    headers={"Content-Type": "multipart/form-data; boundary=" + boundary,
             "Authorization": "Basic " + authorization}, method="POST"
  )
  try:
    with urlopen(request, timeout=45) as response:
      result = json.loads(response.read(1024 * 1024).decode("utf-8"))
  except HTTPError as error:
    raise ImportInputError("ImageKit отклонил изображение (HTTP {}).".format(error.code))
  except (URLError, TimeoutError, OSError):
    raise ImportInputError("Не удалось связаться с ImageKit.")
  except (UnicodeDecodeError, json.JSONDecodeError):
    raise ImportInputError("ImageKit вернул неподдерживаемый ответ.")
  secure_url = result.get("url") if isinstance(result, dict) else None
  if not isinstance(secure_url, str) or not secure_url.startswith("https://"):
    raise ImportInputError("ImageKit не вернул защищённую ссылку на изображение.")
  return secure_url


def _upload_pdf_image(data, mime_type, import_id, digest):
  failures = []
  primary = AdminStudio.get_admin_studio_setting(
    "media.storage_primary", "auto"
  )
  fallback = AdminStudio.get_admin_studio_setting(
    "media.storage_fallback", "imagekit"
  )
  external_enabled = AdminStudio.get_admin_studio_setting(
    "media.external_uploads", True
  ) is not False
  if not external_enabled or primary == "none":
    raise ImportInputError("Внешняя загрузка изображений отключена в настройках медиахранилища.")
  if primary == "auto":
    providers = ["cloudinary", "imagekit"]
  else:
    providers = [primary]
    if fallback not in ("none", primary):
      providers.append(fallback)
  uploaders = {
    "cloudinary": (_cloudinary_settings, _cloudinary_upload),
    "imagekit": (_imagekit_settings, _imagekit_upload)
  }
  for provider in providers:
    settings_fn, upload_fn = uploaders.get(provider, (None, None))
    if settings_fn is None or settings_fn() is None:
      continue
    try:
      return upload_fn(data, mime_type, import_id, digest), provider
    except ImportInputError as error:
      failures.append(str(error))
  if failures:
    raise ImportInputError("Облачная загрузка не удалась: {}".format(" ".join(failures)))
  raise ImportInputError(
    "Облачное хранилище не настроено. Добавьте секреты Cloudinary или IMAGEKIT_PRIVATE_KEY в Anvil."
  )


def _record_external_media(digest, url, provider, mime_type, size):
  row = app_tables.media_objects.get(checksum=digest)
  values = {
    "file_id": digest[:48], "url": url, "source": provider,
    "type": mime_type, "size": size, "checksum": digest,
    "created_at": datetime.now(timezone.utc)
  }
  if row is None:
    app_tables.media_objects.add_row(**values)
  else:
    row.update(**values)


def _pdf_draft_rows(import_row):
  rows = list(app_tables.pdf_draft_items.search(
    q.fetch_only("position", "data"), **{"import": import_row}
  ))
  return [dict(row["data"] or {}) for row in sorted(
    rows, key=lambda item: item["position"] or 0
  )]


def _save_pdf_draft_rows(import_row, products):
  existing = list(app_tables.pdf_draft_items.search(
    q.fetch_only("position", "data"), **{"import": import_row}
  ))
  existing.sort(key=lambda row: row["position"] or 0)
  for position, product in enumerate(products):
    if position < len(existing):
      row = existing[position]
      if row["position"] != position or row["data"] != product:
        row.update(position=position, data=product)
    else:
      cast(Any, app_tables.pdf_draft_items).add_row(
        **{"import": import_row, "position": position, "data": product}
      )
  for row in existing[len(products):]:
    row.delete()


def _xlsx_draft_product(record, category_rows, image_context, warnings):
  prepared_category = _match_category(_value(record, CATEGORY_FIELDS), category_rows)
  category = prepared_category
  subcategory = None
  if category is not None and category.get("parent") is not None:
    subcategory = category
    while category.get("parent") is not None:
      category = category["parent"]
  subcategory_value = _value(record, FIELD_ALIASES["subcategory"])
  if subcategory_value and category is not None:
    subcategory = _match_category(subcategory_value, category_rows, category)
    if subcategory is None:
      warnings.append("Лист «{}», строка {}: подкатегория не сопоставлена.".format(
        record.get("__source_sheet", ""), record.get("__source_row", "")
      ))

  field_aliases = dict(FIELD_ALIASES)
  field_aliases["category"] = CATEGORY_FIELDS
  consumed = {_normal_key(alias) for aliases in field_aliases.values() for alias in aliases}
  image_header_tokens = ("image", "photo", "picture", "фото", "изображение", "картин")
  document_header_tokens = (
    "document", "manual", "certificate", "instruction", "pdf",
    "документ", "инструкц", "сертификат", "паспорт", "руководств"
  )
  specs = {}
  for key, value in record.items():
    header_key = _normal_key(key)
    if (key.startswith("__") or header_key in consumed
        or any(token in header_key for token in image_header_tokens + document_header_tokens)):
      continue
    if value in (None, "") or not str(value).strip():
      continue
    title = str(key).strip()[:80]
    if title and len(specs) < 100:
      specs[title] = str(value).strip()[:1000]
  raw_specs = _raw_value(record, FIELD_ALIASES["specifications"])
  if isinstance(raw_specs, str) and raw_specs.strip():
    try:
      extra_specs = json.loads(raw_specs)
    except json.JSONDecodeError:
      extra_specs = None
    if isinstance(extra_specs, dict):
      for key, value in extra_specs.items():
        if isinstance(key, str) and key.strip() and len(specs) < 100:
          specs[key.strip()[:80]] = value

  image_urls = []
  source_image = _value(record, FIELD_ALIASES["image_url"])
  if source_image and not _remote_url_error(source_image):
    image_urls.append(source_image)
  documents = []
  document_url = _value(record, FIELD_ALIASES["document_url"])
  document_title = _value(record, FIELD_ALIASES["document_title"])
  if document_url and not _remote_url_error(document_url):
    documents.append({"title": document_title or "Документ из XLSX", "url": document_url})
  for header, raw_value in record.items():
    if not isinstance(header, str) or not isinstance(raw_value, str) or not raw_value.strip():
      continue
    header_key = _normal_key(header)
    parts = [part.strip() for part in re.split(r"[\r\n;,]+", raw_value) if part.strip()]
    if any(token in header_key for token in image_header_tokens):
      for part in parts:
        if part.startswith("https://") and not _remote_url_error(part) and part not in image_urls:
          image_urls.append(part)
    if any(token in header_key for token in document_header_tokens):
      structured_documents = []
      if raw_value.lstrip().startswith(("[", "{")):
        try:
          parsed_documents = json.loads(raw_value)
        except json.JSONDecodeError:
          parsed_documents = None
        if isinstance(parsed_documents, dict):
          parsed_documents = [parsed_documents]
        if isinstance(parsed_documents, list):
          structured_documents = [item for item in parsed_documents if isinstance(item, dict)]
      if structured_documents:
        for item in structured_documents:
          url = item.get("url") or item.get("href") or ""
          title = item.get("title") or item.get("name") or header
          if (isinstance(url, str) and url.startswith("https://")
              and not _remote_url_error(url) and isinstance(title, str)):
            documents.append({"title": title.strip()[:120] or header[:120], "url": url})
      else:
        for part in parts:
          if part.startswith("https://") and not _remote_url_error(part):
            documents.append({"title": header.strip()[:120], "url": part})
  for image in record.get("__embedded_images", [])[:12]:
    image_data = image.get("data") if isinstance(image, dict) else None
    mime_type = image.get("mime_type") if isinstance(image, dict) else ""
    if not isinstance(image_data, bytes) or not mime_type:
      continue
    digest = hashlib.sha256(image_data).hexdigest()
    if digest in image_context["seen"]:
      prior_url = image_context["seen_urls"].get(digest)
      if prior_url and prior_url not in image_urls:
        image_urls.append(prior_url)
      continue
    image_context["seen"].add(digest)
    image_context["count"] += 1
    image_context["bytes"] += len(image_data)
    if (image_context["count"] > MAX_PDF_IMAGES
        or len(image_data) > MAX_PDF_IMAGE_BYTES
        or image_context["bytes"] > MAX_PDF_TOTAL_IMAGE_BYTES):
      if not image_context["limited"]:
        warnings.append("Загрузка XLSX-изображений ограничена: максимум {} файлов и {} МБ.".format(
          MAX_PDF_IMAGES, MAX_PDF_TOTAL_IMAGE_BYTES // (1024 * 1024)
        ))
      image_context["limited"] = True
      image_context["failed"] = True
      continue
    existing_media = app_tables.media_objects.get(checksum=digest)
    if existing_media is not None and existing_media["url"]:
      url = existing_media["url"]
      image_context["uploaded"] += 1
    else:
      try:
        url, provider = _upload_pdf_image(
          image_data, mime_type, image_context["import_id"], digest
        )
        _record_external_media(digest, url, provider, mime_type, len(image_data))
        image_context["uploaded"] += 1
      except ImportInputError as error:
        image_context["failed"] = True
        warnings.append("Изображение {} · строка {}: {}".format(
          image.get("name", ""), record.get("__source_row", ""), str(error)
        ))
        continue
    image_context["seen_urls"][digest] = url
    if url not in image_urls:
      image_urls.append(url)
  image_urls = image_urls[:12]
  unique_documents = []
  seen_documents = set()
  for document in documents:
    identity = document["url"]
    if identity not in seen_documents and len(unique_documents) < 20:
      seen_documents.add(identity)
      unique_documents.append(document)
  documents = unique_documents
  source_row = record.get("__source_row")
  evidence = "Лист «{}» · строка {}".format(
    record.get("__source_sheet", ""), source_row or "?"
  )[:400]
  return {
    "brand": _value(record, FIELD_ALIASES["brand"]),
    "model": _value(record, FIELD_ALIASES["model"]),
    "sku": _value(record, FIELD_ALIASES["sku"]),
    "type": _value(record, FIELD_ALIASES["type"]),
    "series": _value(record, FIELD_ALIASES["series"]),
    "description": _value(record, FIELD_ALIASES["description"]),
    "category_code": category["code"] if category is not None else "",
    "subcategory_code": subcategory["code"] if subcategory is not None else "",
    "specs_json": json.dumps(specs, ensure_ascii=False, indent=2),
    "sale_price": _value(record, FIELD_ALIASES["sale_price"]),
    "purchase_price": _value(record, FIELD_ALIASES["purchase_price"]),
    "special_price": _value(record, FIELD_ALIASES["special_price"]),
    "discount": _value(record, FIELD_ALIASES["discount"]),
    "markup": _value(record, FIELD_ALIASES["markup"]),
    "installation_price": _value(record, FIELD_ALIASES["installation_price"]),
    "currency": _value(record, FIELD_ALIASES["currency"]).upper()[:3],
    "quantity": _value(record, FIELD_ALIASES["quantity"]),
    "minimum_stock": _value(record, FIELD_ALIASES["minimum_stock"]),
    "image_url": image_urls[0] if image_urls else "",
    "extra_image_urls": "\n".join(image_urls[1:]),
    "documents_json": json.dumps(documents, ensure_ascii=False, indent=2),
    "source_page": source_row if isinstance(source_row, int) and 1 <= source_row <= MAX_PDF_PAGES else None,
    "confidence": None, "evidence": evidence
  }


def _pdf_category_path(row, categories_by_code):
  parts = [row["title"]]
  parent_code = row.get("parent_code")
  visited = {row["code"]}
  while parent_code and parent_code in categories_by_code and parent_code not in visited:
    visited.add(parent_code)
    parent = categories_by_code[parent_code]
    parts.insert(0, parent["title"])
    parent_code = parent.get("parent_code")
  return " / ".join(parts)


def _pdf_products_from_ai(ai_result, category_rows):
  if not ai_result.get("ok"):
    return [], [ai_result.get("message", "ИИ не настроен.")]
  result = ai_result.get("result") or {}
  raw_products = result.get("products", []) if isinstance(result, dict) else []
  if not isinstance(raw_products, list):
    return [], ["ИИ вернул список товаров в неподдерживаемом формате."]
  by_code = {row["code"]: row for row in category_rows}
  products = []
  for raw in raw_products[:12]:
    if not isinstance(raw, dict):
      continue
    category_code = raw.get("category_code", "")
    subcategory_code = raw.get("subcategory_code", "")
    if not isinstance(category_code, str):
      category_code = ""
    if not isinstance(subcategory_code, str):
      subcategory_code = ""
    selected_code = subcategory_code or category_code
    selected = by_code.get(selected_code) or by_code.get(category_code)
    root = selected
    while root is not None and root.get("parent_code"):
      root = by_code.get(root["parent_code"])
    normalized_subcategory = selected["code"] if selected and root and selected["code"] != root["code"] else ""
    raw_specs = raw.get("specs")
    specs = raw_specs if isinstance(raw_specs, dict) else {}
    safe_specs = {}
    for key, value in list(specs.items())[:100]:
      if not isinstance(key, str) or not key.strip() or len(key.strip()) > 80:
        continue
      if isinstance(value, dict):
        spec_value = value.get("value")
        unit = value.get("unit", "")
        if not isinstance(unit, str):
          unit = ""
        value = {"value": spec_value, "unit": unit[:32]}
      if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text_value = str(value).strip()
        if text_value and len(text_value) <= 200:
          safe_specs[key.strip()] = text_value
      elif isinstance(value, dict) and isinstance(value.get("value"), (str, int, float)) and not isinstance(value.get("value"), bool):
        text_value = str(value["value"]).strip()
        if text_value and len(text_value) <= 200:
          safe_specs[key.strip()] = {"value": text_value, "unit": value.get("unit", "")}
    availability = raw.get("availability")
    if isinstance(availability, str) and availability.strip() and len(safe_specs) < 100:
      safe_specs.setdefault("Наличие", availability.strip()[:200])
    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float, str)):
      confidence = None
    else:
      try:
        confidence = round(float(confidence), 2)
        if not math.isfinite(confidence):
          confidence = None
        else:
          confidence = min(1.0, max(0.0, confidence))
      except (TypeError, ValueError):
        confidence = None
    page_number = raw.get("source_page")
    if isinstance(page_number, bool) or not isinstance(page_number, (int, float, str)):
      page_number = None
    else:
      try:
        page_number = int(page_number)
        if page_number < 1 or page_number > MAX_PDF_PAGES:
          page_number = None
      except (TypeError, ValueError, OverflowError):
        page_number = None
    sale_price = raw.get("sale_price")
    if isinstance(sale_price, bool) or not isinstance(sale_price, (str, int, float)):
      sale_price = ""
    else:
      sale_price = str(sale_price).strip()[:40]
    currency = raw.get("currency")
    if not isinstance(currency, str):
      currency = ""
    quantity = raw.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, (str, int, float)):
      quantity = ""
    else:
      quantity = str(quantity).strip()[:40]
    documents = raw.get("documents")
    if not isinstance(documents, list):
      documents = []
    safe_documents = []
    for document in documents[:20]:
      if not isinstance(document, dict):
        continue
      title, url = document.get("title", ""), document.get("url", "")
      if isinstance(title, str) and isinstance(url, str):
        safe_documents.append({"title": title[:120], "url": url[:1000]})
    products.append({
      "brand": str(raw.get("brand") or "")[:80],
      "model": str(raw.get("model") or "")[:120],
      "sku": str(raw.get("sku") or "")[:80],
      "type": str(raw.get("type") or "")[:80],
      "series": str(raw.get("series") or "")[:100],
      "description": str(raw.get("description") or "")[:2000],
      "category_code": root["code"] if root is not None else "",
      "subcategory_code": normalized_subcategory,
      "specs_json": json.dumps(safe_specs, ensure_ascii=False, indent=2),
      "sale_price": sale_price, "currency": currency[:3].upper(),
      "quantity": quantity, "image_url": "", "extra_image_urls": "",
      "documents_json": json.dumps(safe_documents, ensure_ascii=False, indent=2),
      "source_page": page_number,
      "confidence": confidence,
      "evidence": str(raw.get("evidence") or "")[:400]
    })
  warnings = result.get("warnings", []) if isinstance(result, dict) else []
  if not isinstance(warnings, list):
    warnings = []
  warnings = [str(item)[:240] for item in warnings[:10] if isinstance(item, str)]
  summary = result.get("summary", "") if isinstance(result, dict) else ""
  if isinstance(summary, str) and summary.strip():
    warnings.insert(0, summary.strip()[:400])
  if not products and not warnings:
    warnings.append("ИИ не выделил из PDF карточки товара. Проверьте текст вручную.")
  return products, warnings


def _trim_pdf_import_history():
  terminal_statuses = {
    "pdf": ("pdf_approved", "pdf_rejected", "pdf_failed"),
    "xlsx": ("xlsx_approved", "xlsx_rejected", "xlsx_failed")
  }
  for format_name, statuses in terminal_statuses.items():
    rows = list(app_tables.imports.search(
      q.fetch_only("status", "created_at"),
      order_by("created_at"), format=format_name
    )[:MAX_PDF_DRAFTS + 20])
    while len(rows) > MAX_PDF_DRAFTS:
      old = next((row for row in rows if row["status"] in statuses), None)
      if old is None:
        break
      for log in app_tables.import_logs.search(**{"import": old}):
        log.delete()
      for item in app_tables.pdf_draft_items.search(**{"import": old}):
        item.delete()
      for page in app_tables.pdf_draft_pages.search(**{"import": old}):
        page.delete()
      _delete_xlsx_upload_chunks(old)
      old.delete()
      rows.remove(old)


def _pdf_ai_categories():
  Catalog.ensure_catalog_categories()
  category_rows = cast(Any, Catalog)._category_options()
  by_code = {row["code"]: row for row in category_rows}
  return category_rows, [{
    "code": row["code"], "title": _pdf_category_path(row, by_code),
    "parent_code": row.get("parent_code") or ""
  } for row in category_rows]


def _extract_page_images(page, page_number, import_id, seen, counters, warnings,
                         max_images=MAX_PDF_IMAGES,
                         max_image_bytes=MAX_PDF_IMAGE_BYTES,
                         max_total_bytes=MAX_PDF_TOTAL_IMAGE_BYTES,
                         upload_enabled=True):
  assets = []
  for image in getattr(page, "images", ()):
    image_data = image.data
    if not isinstance(image_data, bytes) or len(image_data) < 1800:
      continue
    mime_type, extension = _pdf_image_mime(image_data, getattr(image, "name", ""))
    if not mime_type:
      continue
    digest = hashlib.sha256(image_data).hexdigest()
    if digest in seen:
      asset = seen[digest]
      if asset and asset not in assets:
        assets.append(dict(asset, page=page_number))
      continue
    existing_media = app_tables.media_objects.get(checksum=digest)
    if existing_media is not None and existing_media["url"]:
      asset = {
        "page": page_number, "name": (getattr(image, "name", "") or "")[:120],
        "sha256": digest, "url": existing_media["url"],
        "provider": existing_media["source"] or "cloud",
        "mime_type": mime_type, "size": len(image_data)
      }
      seen[digest] = asset
      assets.append(asset)
      continue
    counters["count"] += 1
    counters["bytes"] += len(image_data)
    if counters["count"] > max_images or len(image_data) > max_image_bytes or counters["bytes"] > max_total_bytes:
      counters["limited"] = True
      break
    provider = ""
    try:
      if upload_enabled:
        url, provider = _upload_pdf_image(image_data, mime_type, import_id, digest)
        _record_external_media(digest, url, provider, mime_type, len(image_data))
      else:
        url, provider = None, ""
    except ImportInputError as error:
      warnings.append(str(error))
      url = None
      counters.setdefault("failed_pages", set()).add(page_number)
    asset = {
      "page": page_number, "name": (getattr(image, "name", "") or "")[:120],
      "sha256": digest, "url": url or "", "provider": provider if url else "",
      "mime_type": mime_type,
      "size": len(image_data)
    }
    seen[digest] = asset if url else None
    if url:
      assets.append(asset)
  return assets


def _pdf_text_chunks(page_number, text, max_chars=10500):
  for offset in range(0, len(text), max_chars):
    fragment = text[offset:offset + max_chars]
    yield "[Страница {} · фрагмент {}]\n{}".format(
      page_number, offset // max_chars + 1, fragment
    )


def _merge_pdf_products(products):
  merged = []
  by_sku = {}
  by_model = {}
  model_candidates = {}
  for product in products:
    brand = (product.get("brand") or "").strip().casefold()
    model = (product.get("model") or "").strip().casefold()
    sku = (product.get("sku") or "").strip().casefold()
    if not model and not sku:
      merged.append(product)
      continue
    existing_index = by_sku.get((brand, sku)) if sku else None
    if existing_index is None and sku and brand:
      existing_index = by_sku.get(("", sku))
    if existing_index is None and sku and not brand:
      candidates = model_candidates.get(("sku", sku), [])
      if len(candidates) == 1:
        existing_index = candidates[0]
    if existing_index is None and model:
      existing_index = by_model.get((brand, model))
      if existing_index is None and brand:
        existing_index = by_model.get(("", model))
      elif existing_index is None:
        candidates = model_candidates.get(("model", model), [])
        if len(candidates) == 1:
          existing_index = candidates[0]
    if existing_index is None:
      existing_index = len(merged)
      merged.append(product)
    else:
      existing = merged[existing_index]
      for field in ("brand", "model", "sku", "description", "type", "series",
                    "sale_price", "currency", "quantity", "category_code",
                    "subcategory_code", "image_url", "extra_image_urls"):
        if not existing.get(field) and product.get(field):
          existing[field] = product[field]
      try:
        specs = json.loads(existing["specs_json"] or "{}")
        specs.update(json.loads(product["specs_json"] or "{}"))
        existing["specs_json"] = json.dumps(specs, ensure_ascii=False, indent=2)
      except json.JSONDecodeError:
        pass
      pages = [existing.get("source_page"), product.get("source_page")]
      existing["source_page"] = next((number for number in pages if number), None)
      evidence = [existing.get("evidence", ""), product.get("evidence", "")]
      existing["evidence"] = " · ".join(item for item in dict.fromkeys(evidence) if item)[:400]
    if sku:
      by_sku.setdefault((brand, sku), existing_index)
      model_candidates.setdefault(("sku", sku), [])
      if existing_index not in model_candidates[("sku", sku)]:
        model_candidates[("sku", sku)].append(existing_index)
    if model:
      by_model.setdefault((brand, model), existing_index)
      model_candidates.setdefault(("model", model), [])
      if existing_index not in model_candidates[("model", model)]:
        model_candidates[("model", model)].append(existing_index)
  return merged


def _pdf_setting_int(key, default, minimum, maximum):
  value = AdminStudio.get_admin_studio_setting(key, default)
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return default
  value = int(value)
  return max(minimum, min(value, maximum))


def _render_pdf_page_for_ocr(pdfium_document, page_number):
  page = pdfium_document[page_number - 1]
  bitmap = page.render(scale=1.6, rotation=0)
  image = bitmap.to_pil()
  image.thumbnail((1800, 1800))
  output = io.BytesIO()
  image.convert("RGB").save(output, format="JPEG", quality=82, optimize=True)
  data = output.getvalue()
  if len(data) > 3 * 1024 * 1024:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=64, optimize=True)
    data = output.getvalue()
  return data


def _process_pdf_pages(import_row, data):
  pypdf = importlib.import_module("pypdf")
  try:
    reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted and reader.decrypt("") == 0:
      raise ImportInputError("PDF защищён паролем. Загрузите незапароленную спецификацию.")
    page_count = len(reader.pages)
    max_pages = _pdf_setting_int("pdf.max_pages", MAX_PDF_PAGES, 1, MAX_PDF_PAGES)
    if page_count < 1 or page_count > max_pages:
      raise ImportInputError("PDF должен содержать от 1 до {} страниц.".format(max_pages))
  except ImportInputError:
    raise
  except (pypdf.errors.PdfReadError, EOFError, OSError, ValueError):
    raise ImportInputError("PDF повреждён или имеет неподдерживаемую структуру.")

  user = import_row["created_by"]
  category_rows, ai_categories = _pdf_ai_categories()
  max_products = min(MAX_PDF_DRAFT_PRODUCTS, _pdf_setting_int(
    "pdf.max_products", MAX_PDF_DRAFT_PRODUCTS, 1, MAX_PDF_DRAFT_PRODUCTS
  ))
  max_images = min(MAX_PDF_IMAGES, _pdf_setting_int("pdf.max_images", MAX_PDF_IMAGES, 1, MAX_PDF_IMAGES))
  max_image_bytes = min(MAX_PDF_IMAGE_BYTES, _pdf_setting_int(
    "pdf.max_image_size_mb", 8, 1, 8
  ) * 1024 * 1024)
  max_total_image_bytes = min(MAX_PDF_TOTAL_IMAGE_BYTES, _pdf_setting_int(
    "pdf.max_total_image_size_mb", 30, 1, 30
  ) * 1024 * 1024)
  chunk_size = _pdf_setting_int("pdf.ai_chunk_chars", 8500, 1000, 10500)
  batch_size = _pdf_setting_int(
    "pdf.pages_per_batch", 10, 1, MAX_PDF_BATCH_PAGES
  )
  ocr_enabled = AdminStudio.get_admin_studio_setting("pdf.ocr_enabled", True) is not False
  cloud_upload_enabled = AdminStudio.get_admin_studio_setting("pdf.auto_cloud_media", True) is not False
  resume_enabled = AdminStudio.get_admin_studio_setting("pdf.resume_from_checkpoint", True) is not False
  retain_source = AdminStudio.get_admin_studio_setting("pdf.retain_source_for_review", False) is True
  cloud_ready = cloud_upload_enabled and (
    _cloudinary_settings() is not None or _imagekit_settings() is not None
  )

  checkpoint = import_row["checkpoint"] or {}
  resume_matches = checkpoint.get("page_total") in (None, 0, page_count)
  if not resume_enabled or not resume_matches:
    for old in list(app_tables.pdf_draft_pages.search(**{"import": import_row})):
      old.delete()
    for old in list(app_tables.pdf_draft_items.search(**{"import": import_row})):
      old.delete()
    checkpoint = {"sha256": checkpoint.get("sha256", ""), "format": "pdf"}
  checkpoint.setdefault("page_progress", 0)
  checkpoint.setdefault("warnings", [])
  checkpoint["page_total"] = page_count
  import_row.update(checkpoint=checkpoint, total=page_count, updated_at=datetime.now(timezone.utc))

  warnings = list(checkpoint.get("warnings", []))
  if not cloud_upload_enabled:
    warnings.append("Загрузка изображений в облако выключена в настройках PDF.")
  elif not cloud_ready:
    warnings.append(
      "Внешнее хранилище не настроено: фотографии не сохранялись. Добавьте секреты Cloudinary или IMAGEKIT_PRIVATE_KEY в Anvil Secrets."
    )
  products = _pdf_draft_rows(import_row)
  page_rows = list(app_tables.pdf_draft_pages.search(
    q.fetch_only("page_number", "image_assets"), **{"import": import_row}
  ))
  image_seen = {}
  for row in page_rows:
    for asset in row["image_assets"] or []:
      if asset.get("sha256") and asset.get("url"):
        image_seen[asset["sha256"]] = asset
  image_counters = {"count": 0, "bytes": 0, "limited": False, "failed_pages": set()}
  text_preview = [checkpoint.get("pdf_text", "")] if checkpoint.get("pdf_text") else []
  try:
    text_char_count = min(MAX_PDF_TEXT_CHARS, max(0, int(checkpoint.get("text_char_count", 0) or 0)))
  except (TypeError, ValueError, OverflowError):
    text_char_count = 0
  failed_pages = set(
    page for page in checkpoint.get("failed_pages", [])
    if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= page_count
  )
  failed_image_pages = set(
    page for page in checkpoint.get("failed_image_pages", [])
    if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= page_count
  )
  page_progress = min(page_count, int(checkpoint.get("page_progress") or 0))
  if "pending_pages" in checkpoint:
    pending = checkpoint.get("pending_pages")
    pages_to_process = sorted(set(
      page for page in pending
      if isinstance(pending, list) and isinstance(page, int)
      and not isinstance(page, bool) and 1 <= page <= page_count
    )) if isinstance(pending, list) else []
  else:
    pages_to_process = sorted(
      failed_pages.union(range(page_progress + 1, page_count + 1))
    )
    if not pages_to_process and checkpoint.get("needs_cloud_retry"):
      pages_to_process = list(range(1, page_count + 1))
  batch_pages = pages_to_process[:batch_size]
  ai_available = True
  pdfium_module = None
  pdfium_document = None
  pdfium_unavailable = False
  unassigned_assets = list(checkpoint.get("unassigned_images", []))

  for batch_offset, page_number in enumerate(batch_pages):
    checkpoint = import_row["checkpoint"] or checkpoint
    if checkpoint.get("pause_requested"):
      checkpoint["pause_requested"] = False
      checkpoint["failed_pages"] = sorted(failed_pages)
      checkpoint["warnings"] = list(dict.fromkeys(warnings))[-100:]
      if pdfium_document is not None:
        pdfium_document.close()
      import_row.update(checkpoint=checkpoint, processed=page_progress,
                        status="pdf_paused", updated_at=datetime.now(timezone.utc))
      return {"ok": True, "paused": True, "products": len(products), "pages": page_progress}

    page = reader.pages[page_number - 1]
    old_page = next(iter(app_tables.pdf_draft_pages.search(
      **{"import": import_row, "page_number": page_number}
    )), None)
    old_page_text = old_page["text"] or "" if old_page is not None else ""
    text_char_count = max(0, text_char_count - len(old_page_text))
    page_error = False
    try:
      raw_page_text = page.extract_text() or ""
      raw_page_text = "".join(
        char for char in raw_page_text
        if char in "\n\t" or ord(char) >= 32
      ).strip()
    except (pypdf.errors.PdfReadError, EOFError, OSError, ValueError, KeyError):
      raw_page_text = ""
      page_error = True
      warnings.append("Страница {} повреждена: текст не прочитан.".format(page_number))
    has_text_layer = bool(raw_page_text)
    page_text = raw_page_text[:max(0, MAX_PDF_TEXT_CHARS - text_char_count)]
    text_char_count += len(page_text)
    if has_text_layer and not page_text and not any(
      warning.startswith("Достигнут общий предел текста PDF") for warning in warnings
    ):
      warnings.append("Достигнут общий предел текста PDF в 500 000 символов; оставшиеся страницы сохранены для просмотра.")
    if page_text and sum(len(part) for part in text_preview) < 40000:
      text_preview.append("[Страница {}]\n{}".format(page_number, page_text[:40000]))
    try:
      page_assets = _extract_page_images(
        page, page_number, import_row.get_id(), image_seen,
        image_counters, warnings, max_images=max_images,
        max_image_bytes=max_image_bytes, max_total_bytes=max_total_image_bytes,
        upload_enabled=cloud_upload_enabled
      )
    except (OSError, ValueError, AttributeError, KeyError):
      page_assets = []
      page_error = True
      warnings.append("Не удалось извлечь изображения страницы {}.".format(page_number))
    if page_number in image_counters["failed_pages"]:
      page_error = True
      failed_image_pages.add(page_number)
    else:
      failed_image_pages.discard(page_number)

    page_ai_failed = False
    product_limit_reached = len(products) >= max_products
    if page_text and ai_available and not product_limit_reached:
      for chunk in _pdf_text_chunks(page_number, page_text, chunk_size):
        result = AI.extract_pdf_page_for_import(user, chunk, ai_categories)
        if not result.get("ok"):
          warnings.append("Страница {}: {}".format(
            page_number, result.get("message", "ИИ не смог разобрать текст PDF.")
          )[:240])
          page_ai_failed = True
          ai_available = False
          break
        extracted, result_warnings = _pdf_products_from_ai(result, category_rows)
        for product in extracted:
          if product.get("source_page") is None:
            product["source_page"] = page_number
        products.extend(extracted)
        warnings.extend(result_warnings)
        if len(products) >= max_products:
          warnings.append("Достигнут лимит черновика в {} товаров.".format(max_products))
          products = products[:max_products]
          ai_available = False
          break
    elif not has_text_layer and ocr_enabled and ai_available and not product_limit_reached:
      image_asset = max(
        (item for item in getattr(page, "images", ()) if item.data),
        key=lambda item: len(item.data), default=None
      )
      raw_image = None
      mime_type = ""
      if image_asset is not None:
        candidate = image_asset.data
        candidate_mime, _ = _pdf_image_mime(
          candidate, getattr(image_asset, "name", "")
        )
        if candidate_mime in ("image/jpeg", "image/png", "image/webp") and len(candidate) <= 3 * 1024 * 1024:
          raw_image, mime_type = candidate, candidate_mime
      if raw_image is None and not pdfium_unavailable:
        try:
          if pdfium_module is None:
            pdfium_module = importlib.import_module("pypdfium2")
          if pdfium_document is None:
            pdfium_document = pdfium_module.PdfDocument(data)
          raw_image = _render_pdf_page_for_ocr(pdfium_document, page_number)
          mime_type = "image/jpeg"
        except ImportError:
          pdfium_unavailable = True
          warnings.append("Для OCR сканов не установлены pypdfium2 и Pillow; страницу можно повторить после настройки зависимостей.")
        except (OSError, RuntimeError, ValueError):
          warnings.append("Не удалось отрисовать страницу {} для OCR.".format(page_number))
      if raw_image is not None and len(raw_image) <= 3 * 1024 * 1024:
        image_data = "data:{};base64,{}".format(
          mime_type, base64.b64encode(raw_image).decode("ascii")
        )
        result = AI.extract_pdf_page_for_import(
          user, "[Страница {} · изображение для OCR]".format(page_number),
          ai_categories, image_data
        )
        if result.get("ok"):
          extracted, result_warnings = _pdf_products_from_ai(result, category_rows)
          for product in extracted:
            if product.get("source_page") is None:
              product["source_page"] = page_number
          products.extend(extracted)
          warnings.extend(result_warnings)
        else:
          warnings.append("Страница {}: OCR не выполнен: {}".format(
            page_number, result.get("message", "модель не поддерживает изображения")
          )[:240])
          page_ai_failed = True
          ai_available = False
      else:
        if raw_image is None and not pdfium_unavailable:
          warnings.append("На странице {} нет подходящего изображения для OCR.".format(page_number))
        elif raw_image is not None:
          warnings.append("Изображение страницы {} превышает размер, поддерживаемый OCR.".format(page_number))
        page_ai_failed = True
    elif not has_text_layer and ocr_enabled and not ai_available and not product_limit_reached:
      warnings.append("Страница {} пропущена: ИИ недоступен, страница будет доступна для повтора.".format(page_number))
      page_ai_failed = True
    elif not has_text_layer and not ocr_enabled:
      warnings.append("На странице {} нет текстового слоя; OCR выключен в настройках.".format(page_number))
    elif has_text_layer and not ai_available and not product_limit_reached:
      page_ai_failed = True

    if page_error or page_ai_failed:
      failed_pages.add(page_number)
    else:
      failed_pages.discard(page_number)

    merged_products = _merge_pdf_products(products)[:max_products]
    page_products = [item for item in merged_products if item.get("source_page") == page_number]
    image_urls = [asset["url"] for asset in page_assets if asset.get("url")]
    if image_urls and len(page_products) == 1:
      page_products[0]["image_url"] = page_products[0].get("image_url") or image_urls[0]
      existing_urls = [url for url in (page_products[0].get("extra_image_urls") or "").splitlines() if url]
      page_products[0]["extra_image_urls"] = "\n".join(
        list(dict.fromkeys(existing_urls + image_urls[1:]))
      )[:12000]
    elif image_urls:
      known = {asset.get("sha256") for asset in unassigned_assets}
      unassigned_assets.extend(
        asset for asset in page_assets if asset.get("sha256") not in known
      )
    products = merged_products

    page_values = {
      "import": import_row, "page_number": page_number,
      "text": page_text[:50000], "image_assets": page_assets
    }
    if old_page is None:
      cast(Any, app_tables.pdf_draft_pages).add_row(**page_values)
    else:
      old_page.update(text=page_values["text"], image_assets=page_values["image_assets"])
    _save_pdf_draft_rows(import_row, products)
    page_progress = max(page_progress, page_number)
    checkpoint["page_progress"] = page_progress
    checkpoint["failed_pages"] = sorted(failed_pages)
    checkpoint["failed_image_pages"] = sorted(failed_image_pages)
    checkpoint["warnings"] = list(dict.fromkeys(warnings))[-100:]
    checkpoint["pdf_text"] = "\n\n".join(text_preview)[:40000]
    checkpoint["text_char_count"] = text_char_count
    checkpoint["image_count"] = max(
      checkpoint.get("image_count", 0) or 0,
      len(image_seen), image_counters["count"]
    )
    checkpoint["image_uploaded"] = len(image_seen)
    checkpoint["unassigned_images"] = unassigned_assets[:max_images]
    checkpoint["pending_pages"] = pages_to_process[batch_offset + 1:]
    latest_checkpoint = import_row["checkpoint"] or {}
    if latest_checkpoint.get("pause_requested"):
      checkpoint["pause_requested"] = True
    import_row.update(
      checkpoint=checkpoint, processed=page_progress,
      total=len(products), updated_at=datetime.now(timezone.utc)
    )

  checkpoint = import_row["checkpoint"] or checkpoint
  remaining_pages = checkpoint.get("pending_pages", [])
  if isinstance(remaining_pages, list) and remaining_pages:
    if checkpoint.get("pause_requested"):
      checkpoint["pause_requested"] = False
      if pdfium_document is not None:
        pdfium_document.close()
      import_row.update(
        checkpoint=checkpoint, processed=page_progress, status="pdf_paused",
        updated_at=datetime.now(timezone.utc)
      )
      return {"ok": True, "paused": True, "products": len(products), "pages": page_progress}
    import_row.update(
      checkpoint=checkpoint, processed=page_progress, status="pdf_processing",
      updated_at=datetime.now(timezone.utc)
    )
    if pdfium_document is not None:
      pdfium_document.close()
    _launch_pdf_processing(import_row)
    return {"ok": True, "continued": True, "products": len(products), "pages": page_progress}
  if pdfium_document is not None:
    pdfium_document.close()
  checkpoint.pop("pending_pages", None)
  if not text_preview:
    warnings.append("В документе нет извлекаемого текстового слоя. Для сканов требуется мультимодальная AI-модель.")
  if not products:
    warnings.append("ИИ не обнаружил товарные карточки. Проверьте текст страниц и добавьте строки вручную.")
  if image_counters["limited"]:
    warnings.append("Часть изображений не обработана: достигнут лимит медиа из настроек PDF.")
  uploaded_count = len(image_seen)
  image_count = max(
    checkpoint.get("image_count", 0) or 0,
    uploaded_count, image_counters["count"]
  )
  needs_cloud_retry = bool(cloud_upload_enabled and (
    failed_image_pages or (image_count > uploaded_count and not image_counters["limited"])
  ))
  checkpoint.update({
    "page_total": page_count, "page_progress": page_progress,
    "pdf_text": "\n\n".join(text_preview)[:40000],
    "warnings": list(dict.fromkeys(warnings))[-100:],
    "image_count": image_count, "image_uploaded": uploaded_count,
    "unassigned_images": unassigned_assets[:max_images],
    "failed_pages": sorted(failed_pages),
    "failed_image_pages": sorted(failed_image_pages),
    "needs_cloud_retry": needs_cloud_retry,
    "needs_retry": bool(failed_pages or needs_cloud_retry),
    "ai_configured": bool(products)
  })
  pause_requested = bool(checkpoint.get("pause_requested"))
  keep_pdf = bool(failed_pages or needs_cloud_retry or retain_source or pause_requested)
  final_status = "pdf_paused" if checkpoint.get("pause_requested") else "pdf_draft"
  checkpoint["pause_requested"] = False
  import_row.update(
    checkpoint=checkpoint,
    source_file=import_row["source_file"] if keep_pdf else None,
    total=len(products), processed=page_progress, status=final_status,
    updated_at=datetime.now(timezone.utc)
  )
  if warnings:
    _log(import_row, "warning", warnings[0])
  if final_status == "pdf_draft":
    Core.log_audit(
      actor=user, action="catalog.pdf_draft_created", entity_type="import",
      entity_id=import_row.get_id(),
      details={"filename": import_row["source_name"], "products": len(products),
               "pages": page_count, "failed_pages": len(failed_pages),
               "images": image_count},
      created_at=datetime.now(timezone.utc)
    )
    Analytics.notify_telegram_import(
      import_row["source_name"], len(products), page_count,
      len(failed_pages), image_count
    )
  _trim_pdf_import_history()
  return {"ok": True, "products": len(products), "pages": page_progress,
          "failed_pages": sorted(failed_pages)}


@anvil.server.background_task
def process_pdf_catalog_draft(draft_id):
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] != "pdf" or import_row["status"] != "pdf_processing":
    return
  try:
    source = import_row["source_file"]
    if source is None:
      raise ImportInputError("Исходный PDF недоступен для обработки.")
    data = source.get_bytes()
    max_pdf_bytes = _pdf_setting_int(
      "pdf.max_file_size_mb", 50, 1, MAX_PDF_SOURCE_BYTES // (1024 * 1024)
    ) * 1024 * 1024
    if not isinstance(data, bytes) or len(data) > max_pdf_bytes:
      raise ImportInputError("Размер PDF превышает установленный предел {} МБ.".format(max_pdf_bytes // (1024 * 1024)))
    digest = hashlib.sha256(data).hexdigest()
    if digest != (import_row["checkpoint"] or {}).get("sha256"):
      raise ImportInputError("Исходный PDF изменился после загрузки.")
    return _process_pdf_pages(import_row, data)
  except ImportInputError as error:
    checkpoint = import_row["checkpoint"] or {}
    checkpoint["error"] = str(error)
    import_row.update(status="pdf_failed", checkpoint=checkpoint,
                      updated_at=datetime.now(timezone.utc))
    return {"ok": False, "message": str(error)}
  except Exception:
    import_row.update(status="pdf_failed", updated_at=datetime.now(timezone.utc))
    raise


def _launch_pdf_processing(import_row):
  try:
    task = anvil.server.launch_background_task(
      "process_pdf_catalog_draft", import_row.get_id()
    )
  except Exception:
    checkpoint = import_row["checkpoint"] or {}
    checkpoint["error"] = "Anvil не смог запустить фоновую обработку PDF."
    import_row.update(status="pdf_failed", checkpoint=checkpoint,
                      updated_at=datetime.now(timezone.utc))
    raise
  checkpoint = import_row["checkpoint"] or {}
  task_id = task.get_id() if task is not None else ""
  checkpoint["task_id"] = task_id
  import_row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
  return task_id


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def start_pdf_catalog_draft(uploaded_file):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для импорта каталога.")
  if not isinstance(uploaded_file, anvil.Media):
    return {"ok": False, "message": "Выберите PDF-файл спецификации."}
  filename = (uploaded_file.name or "").replace("\\", "/").rsplit("/", 1)[-1]
  if not filename.casefold().endswith(".pdf"):
    return {"ok": False, "message": "Для черновика каталога загрузите файл PDF."}
  max_pdf_bytes = _pdf_setting_int(
    "pdf.max_file_size_mb", 50, 1, MAX_PDF_SOURCE_BYTES // (1024 * 1024)
  ) * 1024 * 1024
  if uploaded_file.length > max_pdf_bytes:
    return {"ok": False, "message": "PDF не должен превышать {} МБ.".format(max_pdf_bytes // (1024 * 1024))}
  if uploaded_file.content_type not in ("application/pdf", "application/octet-stream", ""):
    return {"ok": False, "message": "Файл должен иметь MIME-тип PDF."}
  data = uploaded_file.get_bytes()
  if not isinstance(data, bytes) or len(data) > max_pdf_bytes:
    return {"ok": False, "message": "PDF не должен превышать {} МБ.".format(max_pdf_bytes // (1024 * 1024))}
  if not data.startswith(b"%PDF-"):
    return {"ok": False, "message": "Файл не имеет корректной сигнатуры PDF."}
  if not _has_active_import_capacity():
    return {"ok": False, "message": "Достигнут лимит активных импортов. Дождитесь завершения текущих задач."}

  digest = hashlib.sha256(data).hexdigest()
  existing_rows = app_tables.imports.search(
    q.fetch_only("source_name", "checkpoint", "status", "total"), format="pdf"
  )[:MAX_PDF_DRAFTS]
  for row in existing_rows:
    checkpoint = row["checkpoint"] or {}
    if (
      checkpoint.get("sha256") == digest
    and row["status"] in ("pdf_processing", "pdf_paused", "pdf_draft", "pdf_failed", "pdf_approved")
      and not (row["status"] == "pdf_approved" and checkpoint.get("needs_retry"))
    ):
      return {
        "ok": True, "draft_id": row.get_id(), "products": row["total"] or 0,
        "status": row["status"],
        "message": "Этот PDF уже есть в импортах. Откройте его и проверьте текущий статус."
      }

  now = datetime.now(timezone.utc)
  import_row = app_tables.imports.add_row(
    source_type="upload", source_name=filename[:120], source_url="",
    format="pdf", status="pdf_processing", source_file=uploaded_file,
    checkpoint={
      "sha256": digest, "format": "pdf", "page_progress": 0,
      "page_total": 0, "warnings": [], "image_count": 0,
      "source_size": len(data), "failed_pages": [], "pause_requested": False
    },
    total=0, processed=0, imported=0, skipped=0,
    created_by=user, created_at=now, updated_at=now
  )
  _launch_pdf_processing(import_row)
  _trim_pdf_import_history()
  return {
    "ok": True, "draft_id": import_row.get_id(), "products": 0,
    "status": "pdf_processing",
    "message": "PDF принят в фоновую обработку. Товары появятся в черновике; каталог не изменится до утверждения."
  }


def _start_xlsx_catalog_draft(uploaded_file, user):
  filename = (uploaded_file.name or "").replace("\\", "/").rsplit("/", 1)[-1]
  if not filename.casefold().endswith(".xlsx"):
    return {"ok": False, "message": "Для черновика загрузите книгу XLSX."}
  if uploaded_file.content_type not in (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream", ""
  ):
    return {"ok": False, "message": "Файл должен иметь MIME-тип XLSX."}
  if uploaded_file.length > 50 * 1024 * 1024:
    return {"ok": False, "message": "Для книги больше 50 МБ используйте загрузку XLSX частями."}
  data = uploaded_file.get_bytes()
  if not isinstance(data, bytes) or len(data) > 50 * 1024 * 1024:
    return {"ok": False, "message": "Для книги больше 50 МБ используйте загрузку XLSX частями."}
  if not data.startswith(b"PK\x03\x04"):
    return {"ok": False, "message": "Файл не имеет корректной структуры XLSX."}
  if not _has_active_import_capacity():
    return {"ok": False, "message": "Достигнут лимит активных импортов. Дождитесь завершения текущих задач."}

  digest = hashlib.sha256(data).hexdigest()
  for row in app_tables.imports.search(
    q.fetch_only("checkpoint", "status", "total"), format="xlsx"
  )[:MAX_PDF_DRAFTS]:
    checkpoint = row["checkpoint"] or {}
    if checkpoint.get("sha256") == digest and row["status"] in (
      "xlsx_processing", "xlsx_paused", "xlsx_draft", "xlsx_failed",
      "xlsx_approved", "xlsx_rejected"
    ):
      return {
        "ok": True, "draft_id": row.get_id(), "products": row["total"] or 0,
        "status": row["status"],
        "message": "Эта книга уже зарегистрирована. Откройте её черновик, чтобы продолжить работу."
      }

  now = datetime.now(timezone.utc)
  import_row = app_tables.imports.add_row(
    source_type="upload", source_name=filename[:120], source_url="",
    format="xlsx", status="xlsx_processing", source_file=None,
    checkpoint={"sha256": digest, "format": "xlsx", "source_size": len(data),
                "warnings": [], "sheet_count": 0, "image_count": 0,
                "image_uploaded": 0, "image_bytes": 0, "image_hashes": [],
                "row_progress": 0, "row_count": 0,
                "pause_requested": False, "needs_cloud_retry": False},
    total=0, processed=0, imported=0, skipped=0,
    created_by=user, created_at=now, updated_at=now
  )
  for chunk_index, offset in enumerate(range(0, len(data), XLSX_UPLOAD_CHUNK_BYTES)):
    chunk_data = data[offset:offset + XLSX_UPLOAD_CHUNK_BYTES]
    cast(Any, app_tables.xlsx_upload_chunks).add_row(
      **{"import": import_row, "chunk_index": chunk_index,
         "content": anvil.BlobMedia(
           "application/octet-stream", chunk_data,
           name="xlsx-{}-{}.part".format(import_row.get_id(), chunk_index)
         ),
         "byte_count": len(chunk_data),
         "sha256": hashlib.sha256(chunk_data).hexdigest(),
         "created_at": now}
    )
  _launch_xlsx_processing(import_row)
  _trim_pdf_import_history()
  return {
    "ok": True, "draft_id": import_row.get_id(), "products": 0,
    "status": "xlsx_processing",
    "message": "XLSX принят в фоновую обработку по пакетам. Результаты сохраняются в черновик, каталог не меняется до утверждения."
  }


def _xlsx_chunk_rows(import_row):
  return app_tables.xlsx_upload_chunks.search(
    q.fetch_only("chunk_index", "content", "byte_count", "sha256"),
    order_by("chunk_index"), **{"import": import_row}
  )


def _has_xlsx_source(import_row):
  if import_row is None:
    return False
  if import_row["source_file"] is not None:
    return True
  return next(iter(_xlsx_chunk_rows(import_row)), None) is not None


def _delete_xlsx_upload_chunks(import_row):
  if import_row is None:
    return
  for chunk_row in list(_xlsx_chunk_rows(import_row)):
    chunk_row.delete()


def _materialize_xlsx_source(import_row):
  checkpoint = import_row["checkpoint"] or {}
  expected_size = int(checkpoint.get("source_size", 0) or 0)
  expected_chunks = int(checkpoint.get("expected_chunks", 0) or 0)
  output = tempfile.TemporaryFile(mode="w+b")
  digest = hashlib.sha256()
  byte_count = 0
  chunk_count = 0
  if import_row["source_file"] is not None:
    data = import_row["source_file"].get_bytes()
    output.write(data)
    digest.update(data)
    byte_count = len(data)
    chunk_count = 1
  else:
    for chunk_index, chunk_row in enumerate(_xlsx_chunk_rows(import_row)):
      if chunk_index >= expected_chunks or chunk_row["chunk_index"] != chunk_index:
        output.close()
        raise ImportInputError("В загрузке XLSX не хватает части №{}.".format(chunk_index + 1))
      chunk_data = chunk_row["content"].get_bytes()
      if (not isinstance(chunk_data, bytes)
          or len(chunk_data) != chunk_row["byte_count"]
          or hashlib.sha256(chunk_data).hexdigest() != chunk_row["sha256"]):
        output.close()
        raise ImportInputError("Часть №{} загрузки XLSX повреждена.".format(chunk_index + 1))
      output.write(chunk_data)
      digest.update(chunk_data)
      byte_count += len(chunk_data)
      chunk_count += 1
  if (byte_count != expected_size
      or (expected_chunks and chunk_count != expected_chunks)
      or byte_count > MAX_XLSX_SOURCE_BYTES):
    output.close()
    raise ImportInputError("Размер XLSX не совпадает с сохранённой контрольной точкой.")
  value = digest.hexdigest()
  expected_digest = checkpoint.get("sha256", "")
  if expected_digest and value != expected_digest:
    output.close()
    raise ImportInputError("Контрольная сумма XLSX не совпала после сборки частей.")
  output.seek(0)
  return output, value


def _new_xlsx_catalog_upload(user, filename, source_size, upload_signature):
  now = datetime.now(timezone.utc)
  expected_chunks = (source_size + XLSX_UPLOAD_CHUNK_BYTES - 1) // XLSX_UPLOAD_CHUNK_BYTES
  return app_tables.imports.add_row(
    source_type="upload", source_name=filename[:120], source_url="",
    format="xlsx", status="xlsx_uploading", source_file=None,
    checkpoint={
      "format": "xlsx", "source_size": source_size,
      "upload_signature": upload_signature, "expected_chunks": expected_chunks,
      "next_chunk": 0, "uploaded_bytes": 0, "sha256": "",
      "warnings": [], "sheet_count": 0, "image_count": 0,
      "image_uploaded": 0, "image_bytes": 0, "image_hashes": [],
      "row_progress": 0, "row_count": 0,
      "pause_requested": False, "needs_cloud_retry": False
    },
    total=0, processed=0, imported=0, skipped=0,
    created_by=user, created_at=now, updated_at=now
  )


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def begin_xlsx_catalog_upload(filename, source_size, last_modified):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для импорта каталога.")
  if not isinstance(filename, str) or not filename.strip() or len(filename) > 180:
    return {"ok": False, "message": "Проверьте имя книги XLSX."}
  filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
  if not filename.casefold().endswith(".xlsx"):
    return {"ok": False, "message": "Выберите книгу XLSX."}
  if (isinstance(source_size, bool) or not isinstance(source_size, (int, float))
      or int(source_size) < 1 or int(source_size) > MAX_XLSX_SOURCE_BYTES):
    return {"ok": False, "message": "XLSX должен занимать не более 1 ГБ."}
  if (isinstance(last_modified, bool) or not isinstance(last_modified, (int, float))
      or not 0 <= last_modified <= 4102444800000):
    return {"ok": False, "message": "Не удалось проверить выбранный файл."}
  source_size = int(source_size)
  upload_signature = hashlib.sha256("{}|{}|{}".format(
    filename.casefold(), source_size, int(last_modified)
  ).encode("utf-8")).hexdigest()
  for row in app_tables.imports.search(
    q.fetch_only("checkpoint", "status", "total", "format", "source_name"),
    order_by("created_at", ascending=False), created_by=user
  )[:MAX_PDF_DRAFTS * 2]:
    checkpoint = row["checkpoint"] or {}
    if (row["format"] == "xlsx"
        and checkpoint.get("upload_signature") == upload_signature
        and row["status"] in (
          "xlsx_uploading", "xlsx_processing", "xlsx_paused", "xlsx_failed",
          "xlsx_draft", "xlsx_images_processing", "xlsx_approved", "xlsx_rejected"
        )):
      next_chunk = max(0, int(checkpoint.get(
        "next_chunk", (checkpoint.get("uploaded_bytes", 0) or 0) // XLSX_UPLOAD_CHUNK_BYTES
      ) or 0))
      if row["status"] == "xlsx_uploading" and checkpoint.get("upload_paused"):
        checkpoint["upload_paused"] = False
        row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
      return {
        "ok": True, "upload_id": row.get_id(), "status": row["status"],
        "chunk_size": XLSX_UPLOAD_CHUNK_BYTES,
        "next_chunk": next_chunk,
        "uploaded_bytes": checkpoint.get("uploaded_bytes", 0),
        "message": "Найдена предыдущая загрузка. Продолжаем с части {} без повторной передачи сохранённых частей.".format(next_chunk + 1)
      }
  if not _has_active_import_capacity():
    return {"ok": False, "message": "Достигнут лимит активных импортов. Дождитесь завершения текущих задач."}
  import_row = _new_xlsx_catalog_upload(user, filename, source_size, upload_signature)
  _trim_pdf_import_history()
  return {
    "ok": True, "upload_id": import_row.get_id(),
    "status": "xlsx_uploading", "chunk_size": XLSX_UPLOAD_CHUNK_BYTES,
    "next_chunk": 0, "uploaded_bytes": 0,
    "message": "Загрузка началась частями по 4 МБ. Каждая часть сохраняется отдельно."
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def upload_xlsx_catalog_chunk(upload_id, chunk_index, chunk_data):
  Core.require_permission("import.manage")
  if not isinstance(upload_id, str) or not upload_id:
    return {"ok": False, "message": "Загрузка XLSX не найдена."}
  if (isinstance(chunk_index, bool) or not isinstance(chunk_index, int)
      or chunk_index < 0):
    return {"ok": False, "message": "Проверьте номер части XLSX."}
  if not isinstance(chunk_data, bytes) or not 1 <= len(chunk_data) <= XLSX_UPLOAD_CHUNK_BYTES:
    return {"ok": False, "message": "Размер части XLSX должен быть от 1 байта до 4 МБ."}
  import_row = app_tables.imports.get_by_id(upload_id)
  if import_row is None or import_row["format"] != "xlsx":
    return {"ok": False, "message": "Загрузка XLSX не найдена."}
  if import_row["status"] != "xlsx_uploading":
    checkpoint = import_row["checkpoint"] or {}
    return {
      "ok": True, "status": import_row["status"],
      "uploaded_bytes": checkpoint.get("uploaded_bytes", 0),
      "source_size": checkpoint.get("source_size", 0),
      "message": "Этот XLSX уже передан серверу."
    }
  checkpoint = import_row["checkpoint"] or {}
  expected_chunks = int(checkpoint.get("expected_chunks", 0) or 0)
  expected_size = int(checkpoint.get("source_size", 0) or 0)
  if chunk_index >= expected_chunks:
    return {"ok": False, "message": "Номер части выходит за пределы файла."}
  expected_length = min(
    XLSX_UPLOAD_CHUNK_BYTES,
    expected_size - chunk_index * XLSX_UPLOAD_CHUNK_BYTES
  )
  if len(chunk_data) != expected_length:
    return {"ok": False, "message": "Размер полученной части не совпадает с ожидаемым."}
  if chunk_index == 0 and not chunk_data.startswith(b"PK\x03\x04"):
    return {"ok": False, "message": "Файл не имеет корректной структуры XLSX."}
  chunk_digest = hashlib.sha256(chunk_data).hexdigest()
  existing = next(iter(app_tables.xlsx_upload_chunks.search(
    **{"import": import_row, "chunk_index": chunk_index}
  )), None)
  if existing is not None and existing["sha256"] == chunk_digest:
    return {
      "ok": True, "status": "xlsx_uploading",
      "uploaded_bytes": min(expected_size, (chunk_index + 1) * XLSX_UPLOAD_CHUNK_BYTES),
      "source_size": expected_size, "message": "Часть уже сохранена и проверена."
    }
  if existing is not None:
    for later in list(app_tables.xlsx_upload_chunks.search(**{"import": import_row})):
      if later["chunk_index"] >= chunk_index:
        later.delete()
    checkpoint["next_chunk"] = chunk_index
    checkpoint["uploaded_bytes"] = chunk_index * XLSX_UPLOAD_CHUNK_BYTES
  next_chunk = int(checkpoint.get("next_chunk", 0) or 0)
  if chunk_index != next_chunk:
    return {
      "ok": False,
      "message": "Ожидается часть {}. Выберите тот же файл, чтобы безопасно продолжить загрузку.".format(next_chunk + 1)
    }
  now = datetime.now(timezone.utc)
  cast(Any, app_tables.xlsx_upload_chunks).add_row(
    **{"import": import_row, "chunk_index": chunk_index,
       "content": anvil.BlobMedia(
         "application/octet-stream", chunk_data,
         name="xlsx-{}-{}.part".format(upload_id, chunk_index)
       ),
       "byte_count": len(chunk_data), "sha256": chunk_digest, "created_at": now}
  )
  next_chunk = chunk_index + 1
  uploaded_bytes = min(expected_size, next_chunk * XLSX_UPLOAD_CHUNK_BYTES)
  checkpoint.update(next_chunk=next_chunk, uploaded_bytes=uploaded_bytes)
  checkpoint["upload_paused"] = False
  complete = next_chunk >= expected_chunks and uploaded_bytes == expected_size
  import_row.update(
    checkpoint=checkpoint,
    status="xlsx_processing" if complete else "xlsx_uploading",
    updated_at=now
  )
  if complete:
    _launch_xlsx_processing(import_row)
  return {
    "ok": True, "status": import_row["status"],
    "uploaded_bytes": uploaded_bytes, "source_size": expected_size,
    "complete": complete,
    "message": "Загрузка завершена. Начат поэтапный разбор XLSX в черновик."
      if complete else "Часть {} сохранена.".format(next_chunk)
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def verify_xlsx_catalog_chunks(upload_id, chunk_hashes):
  Core.require_permission("import.manage")
  if not isinstance(upload_id, str) or not upload_id:
    return {"ok": False, "message": "Загрузка XLSX не найдена."}
  if not isinstance(chunk_hashes, list) or len(chunk_hashes) > 256:
    return {"ok": False, "message": "Не удалось проверить контрольные суммы XLSX."}
  if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
         for value in chunk_hashes):
    return {"ok": False, "message": "Контрольная сумма части XLSX имеет неверный формат."}
  import_row = app_tables.imports.get_by_id(upload_id)
  if (import_row is None or import_row["format"] != "xlsx"
      or import_row["status"] != "xlsx_uploading"):
    return {"ok": False, "message": "Продолжить можно только незавершённую загрузку XLSX."}
  checkpoint = import_row["checkpoint"] or {}
  saved_count = max(0, int(checkpoint.get("next_chunk", 0) or 0))
  if len(chunk_hashes) != saved_count:
    return {"ok": False, "message": "Контрольная точка изменилась. Обновите список черновиков и повторите загрузку."}
  saved_rows = {row["chunk_index"]: row for row in _xlsx_chunk_rows(import_row)}
  mismatch = None
  for index, expected_hash in enumerate(chunk_hashes):
    saved_row = saved_rows.get(index)
    if saved_row is None or saved_row["sha256"] != expected_hash:
      mismatch = index
      break
  if mismatch is None:
    return {"ok": True, "match": True, "next_chunk": saved_count,
            "message": "Сохранённые части сверены. Продолжаем с контрольной точки."}

  for index, saved_row in list(saved_rows.items()):
    if index >= mismatch:
      saved_row.delete()
  checkpoint.update(
    next_chunk=mismatch, uploaded_bytes=mismatch * XLSX_UPLOAD_CHUNK_BYTES,
    upload_paused=False
  )
  import_row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
  return {
    "ok": True, "match": False, "next_chunk": mismatch,
    "message": "Файл отличается от сохранённой загрузки. Повторно передадим части начиная с №{}; предыдущие подтверждённые части оставлены.".format(mismatch + 1)
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def cancel_xlsx_catalog_upload(upload_id):
  Core.require_permission("import.manage")
  if not isinstance(upload_id, str) or not upload_id:
    return {"ok": False, "message": "Загрузка XLSX не найдена."}
  import_row = app_tables.imports.get_by_id(upload_id)
  if import_row is None or import_row["format"] != "xlsx":
    return {"ok": False, "message": "Загрузка XLSX не найдена."}
  if import_row["status"] != "xlsx_uploading":
    return {"ok": False, "message": "Отменить можно только загрузку, которая ещё передаётся."}
  checkpoint = import_row["checkpoint"] or {}
  checkpoint["upload_paused"] = True
  import_row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
  return {"ok": True, "message": "Загрузка поставлена на паузу. Сохранённые части останутся для продолжения."}


def _process_xlsx_catalog_batch(import_row, records, complete=False, row_total=None):
  checkpoint = import_row["checkpoint"] or {}
  cursor = max(0, int(checkpoint.get("row_progress", 0) or 0))
  products = _pdf_draft_rows(import_row)
  if cursor > MAX_PDF_DRAFT_PRODUCTS or cursor + len(records) > MAX_PDF_DRAFT_PRODUCTS:
    raise ImportInputError(
      "В одном XLSX-черновике можно обработать не более {} товарных строк.".format(MAX_PDF_DRAFT_PRODUCTS)
    )
  if len(products) != cursor:
    raise ImportInputError("Контрольная точка XLSX не совпадает с исходной таблицей.")
  if cursor == 0:
    Catalog.ensure_catalog_categories()
  category_rows = cast(Any, Catalog)._category_options()
  warnings = list(checkpoint.get("warnings", []))
  image_hashes = list(checkpoint.get("image_hashes", []))
  image_context = {
    "import_id": import_row.get_id(), "uploaded": 0,
    "count": int(checkpoint.get("image_count", 0) or 0),
    "bytes": int(checkpoint.get("image_bytes", 0) or 0),
    "limited": False, "failed": False, "seen": set(image_hashes),
    "seen_urls": {}
  }
  for digest in image_hashes:
    media = app_tables.media_objects.get(checksum=digest)
    if media is not None and media["url"]:
      image_context["seen_urls"][digest] = media["url"]
  existing_keys = set(filter(None, (_record_key(item) for item in products)))
  duplicate_count = int(checkpoint.get("duplicate_count", 0) or 0)
  missing_category = int(checkpoint.get("missing_category", 0) or 0)
  missing_model = int(checkpoint.get("missing_model", 0) or 0)
  existing_count = int(checkpoint.get("existing_count", 0) or 0)
  end = cursor + len(records)
  for record in records:
    warnings.extend(record.get("__source_warnings", []))
    product = _xlsx_draft_product(record, category_rows, image_context, warnings)
    key = _record_key(record)
    if key is not None and key in existing_keys:
      duplicate_count += 1
      warnings.append("Возможный повтор модели/артикула: {} · {}.".format(
        product.get("brand", ""), product.get("model", "") or product.get("sku", "")
      ))
    elif key is not None:
      existing_keys.add(key)
    missing_category += not bool(product["category_code"])
    missing_model += not bool(product["model"])
    if product["model"]:
      _, existing = Catalog.find_import_product(
        product["brand"], product["model"], product["sku"]
      )
      existing_count += 1 if existing is not None else 0
    products.append(product)
  _save_pdf_draft_rows(import_row, products)
  latest_row = app_tables.imports.get_by_id(import_row.get_id())
  latest_checkpoint = latest_row["checkpoint"] or {} if latest_row is not None else {}
  checkpoint["pause_requested"] = bool(
    checkpoint.get("pause_requested") or latest_checkpoint.get("pause_requested")
  )
  image_hashes = list(image_context["seen"])
  checkpoint.update({
    "row_count": row_total if complete and row_total is not None else checkpoint.get("row_count", 0),
    "row_progress": end,
    "sheet_names": list(dict.fromkeys(
      (checkpoint.get("sheet_names", []) or [])
      + [record.get("__source_sheet", "") for record in records]
    )),
    "image_count": image_context["count"],
    "image_uploaded": int(checkpoint.get("image_uploaded", 0) or 0) + image_context["uploaded"],
    "image_bytes": image_context["bytes"],
    "image_hashes": image_hashes,
    "duplicate_count": duplicate_count,
    "missing_category": missing_category,
    "missing_model": missing_model,
    "existing_count": existing_count,
    "warnings": list(dict.fromkeys(warnings))[-500:],
    "needs_cloud_retry": bool(checkpoint.get("needs_cloud_retry") or image_context["failed"])
  })
  checkpoint["sheet_count"] = len(checkpoint["sheet_names"])
  pause_requested = bool(checkpoint.get("pause_requested"))
  if complete:
    if missing_category:
      checkpoint["warnings"] = ["Строк без сопоставленной категории: {}. Назначьте категории перед утверждением.".format(missing_category)] + checkpoint["warnings"]
    if missing_model:
      checkpoint["warnings"] = ["Строк без модели: {}. Заполните поле модели перед утверждением.".format(missing_model)] + checkpoint["warnings"]
    if existing_count:
      checkpoint["warnings"] = ["Совпадений с товарами каталога: {}. Утверждение обновит эти записи без создания повторов.".format(existing_count)] + checkpoint["warnings"]
  status = "xlsx_paused" if pause_requested and not complete else "xlsx_draft" if complete else "xlsx_processing"
  checkpoint["pause_requested"] = False
  checkpoint.pop("error", None)
  if latest_row is not None:
    import_row = latest_row
  import_row.update(
    checkpoint=checkpoint, total=len(products), processed=end, status=status,
    source_file=import_row["source_file"]
      if checkpoint["needs_cloud_retry"] or status == "xlsx_paused" else None,
    updated_at=datetime.now(timezone.utc)
  )
  if complete:
    user = import_row["created_by"]
    Core.log_audit(
      actor=user, action="catalog.xlsx_draft_created", entity_type="import",
      entity_id=import_row.get_id(), details={
        "rows": len(products), "sheets": checkpoint["sheet_count"],
        "images": image_context["count"], "image_uploaded": checkpoint["image_uploaded"],
        "duplicates": duplicate_count
      }, created_at=datetime.now(timezone.utc)
    )
    Analytics.notify_telegram_import(
      import_row["source_name"], len(products), row_total or end, 0, image_context["count"]
    )
    if not checkpoint["needs_cloud_retry"]:
      _delete_xlsx_upload_chunks(import_row)
  return {"complete": complete or pause_requested, "status": status}


@anvil.server.background_task
def process_xlsx_catalog_draft(draft_id):
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] != "xlsx" or import_row["status"] != "xlsx_processing":
    return
  source = None
  record_iterator = None
  try:
    source, digest = _materialize_xlsx_source(import_row)
    checkpoint = import_row["checkpoint"] or {}
    if not checkpoint.get("sha256"):
      checkpoint["sha256"] = digest
      import_row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
    cursor = max(0, int((import_row["checkpoint"] or {}).get("row_progress", 0) or 0))
    records_seen = 0
    batch = []
    paused = False
    record_iterator = _iter_xlsx_records(source)
    for record in record_iterator:
      records_seen += 1
      if records_seen <= cursor:
        continue
      batch.append(record)
      if len(batch) >= BATCH_SIZE:
        import_row = app_tables.imports.get_by_id(draft_id)
        if import_row is None or import_row["status"] != "xlsx_processing":
          paused = True
          break
        result = _process_xlsx_catalog_batch(import_row, batch)
        batch = []
        if result["complete"]:
          paused = result["status"] == "xlsx_paused"
          break
        time.sleep(XLSX_BATCH_PAUSE_SECONDS)
    if not paused:
      import_row = app_tables.imports.get_by_id(draft_id)
      if import_row is None or import_row["status"] != "xlsx_processing":
        paused = True
      elif records_seen < cursor:
        raise ImportInputError("Контрольная точка XLSX превышает количество строк исходного файла.")
      else:
        result = _process_xlsx_catalog_batch(
          import_row, batch, complete=True, row_total=records_seen
        )
  except ImportInputError as error:
    failed_row = app_tables.imports.get_by_id(draft_id)
    if failed_row is None:
      raise
    checkpoint = failed_row["checkpoint"] or {}
    checkpoint["error"] = str(error)
    failed_row.update(status="xlsx_failed", checkpoint=checkpoint,
                      updated_at=datetime.now(timezone.utc))
    return {"ok": False, "message": str(error)}
  except Exception:
    failed_row = app_tables.imports.get_by_id(draft_id)
    if failed_row is not None:
      failed_row.update(status="xlsx_failed", updated_at=datetime.now(timezone.utc))
    raise
  finally:
    if record_iterator is not None:
      record_iterator.close()
    if source is not None:
      source.close()
  finished_row = app_tables.imports.get_by_id(draft_id)
  return {"ok": True, "status": finished_row["status"] if finished_row is not None else "missing"}


def _launch_xlsx_processing(import_row):
  try:
    task = anvil.server.launch_background_task(
      "process_xlsx_catalog_draft", import_row.get_id()
    )
  except Exception:
    checkpoint = import_row["checkpoint"] or {}
    checkpoint["error"] = "Anvil не смог запустить фоновую обработку XLSX."
    import_row.update(status="xlsx_failed", checkpoint=checkpoint,
                      updated_at=datetime.now(timezone.utc))
    raise
  checkpoint = import_row["checkpoint"] or {}
  checkpoint["task_id"] = task.get_id() if task is not None else ""
  import_row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
  return checkpoint["task_id"]


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def start_catalog_file_draft(uploaded_file):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для импорта каталога.")
  if not isinstance(uploaded_file, anvil.Media):
    return {"ok": False, "message": "Выберите PDF или XLSX-файл."}
  filename = (uploaded_file.name or "").casefold()
  if filename.endswith(".pdf"):
    return start_pdf_catalog_draft(uploaded_file)
  if filename.endswith(".xlsx"):
    return _start_xlsx_catalog_draft(uploaded_file, user)
  return {"ok": False, "message": "Поддерживаются PDF и XLSX."}


def _resume_pdf_catalog_draft(draft_id, user):
  if not isinstance(draft_id, str) or not draft_id:
    return {"ok": False, "message": "Выберите PDF-черновик."}
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] != "pdf":
    return {"ok": False, "message": "PDF-черновик не найден."}
  if import_row["status"] not in ("pdf_failed", "pdf_draft", "pdf_paused"):
    return {"ok": False, "message": "Продолжить можно после завершения текущего этапа."}
  if import_row["source_file"] is None:
    return {"ok": False, "message": "Исходный PDF уже очищен. Загрузите его заново."}
  if not _has_active_import_capacity():
    return {"ok": False, "message": "Достигнут лимит активных импортов. Дождитесь завершения текущих задач."}
  checkpoint = import_row["checkpoint"] or {}
  failed_pages = checkpoint.get("failed_pages", [])
  if not isinstance(failed_pages, list):
    failed_pages = []
  if checkpoint.get("needs_cloud_retry"):
    total = checkpoint.get("page_total", 0) or 0
    image_failed_pages = checkpoint.get("failed_image_pages", [])
    if isinstance(image_failed_pages, list) and image_failed_pages:
      failed_pages = sorted(set(failed_pages).union(image_failed_pages))
    elif not failed_pages:
      failed_pages = list(range(1, min(total, MAX_PDF_PAGES) + 1))
  if not checkpoint.get("pending_pages"):
    checkpoint.pop("pending_pages", None)
  if not failed_pages and (checkpoint.get("page_progress", 0) or 0) >= (checkpoint.get("page_total", 0) or 0) and not checkpoint.get("needs_retry"):
    return {"ok": False, "message": "Ошибок для повтора нет. Черновик уже готов к проверке."}
  checkpoint.update({"failed_pages": failed_pages, "pause_requested": False, "error": ""})
  now = datetime.now(timezone.utc)
  import_row.update(status="pdf_processing", checkpoint=checkpoint, updated_at=now)
  _launch_pdf_processing(import_row)
  Core.log_audit(
    actor=user, action="catalog.pdf_draft_resumed", entity_type="import",
    entity_id=import_row.get_id(), details={"filename": import_row["source_name"],
                                          "failed_pages": len(failed_pages)},
    created_at=now
  )
  return {"ok": True, "message": "PDF продолжит обработку с сохранённой страницы; успешные страницы и черновые товары оставлены."}


def _retry_xlsx_draft_images(import_row):
  if import_row["status"] not in ("xlsx_draft", "xlsx_images_processing"):
    return {"ok": False, "message": "Повторить загрузку фото можно после завершения разбора XLSX."}
  if not _has_xlsx_source(import_row):
    return {"ok": False, "message": "Исходный XLSX недоступен для повтора загрузки фотографий."}
  source, _ = _materialize_xlsx_source(import_row)
  try:
    records = _records_xlsx(source)
  finally:
    source.close()
  products = _pdf_draft_rows(import_row)
  if len(records) != len(products):
    return {"ok": False, "message": "Структура исходного XLSX изменилась. Загрузите файл заново."}
  checkpoint = import_row["checkpoint"] or {}
  uploaded = 0
  failed = []
  total = 0
  bytes_seen = 0
  seen = set()
  for record, product in zip(records, products):
    urls = [product.get("image_url", "")] + [
      line.strip() for line in product.get("extra_image_urls", "").splitlines()
      if line.strip()
    ]
    for image in record.get("__embedded_images", [])[:12]:
      image_data = image.get("data") if isinstance(image, dict) else None
      mime_type = image.get("mime_type") if isinstance(image, dict) else ""
      if not isinstance(image_data, bytes) or not mime_type:
        continue
      digest = hashlib.sha256(image_data).hexdigest()
      if digest in seen:
        continue
      seen.add(digest)
      total += 1
      bytes_seen += len(image_data)
      if total > MAX_PDF_IMAGES or bytes_seen > MAX_PDF_TOTAL_IMAGE_BYTES:
        failed.append("Достигнут лимит загрузки изображений XLSX.")
        break
      existing = app_tables.media_objects.get(checksum=digest)
      if existing is not None and existing["url"]:
        url = existing["url"]
      else:
        try:
          url, provider = _upload_pdf_image(
            image_data, mime_type, import_row.get_id(), digest
          )
          _record_external_media(digest, url, provider, mime_type, len(image_data))
          uploaded += 1
        except ImportInputError as error:
          failed.append(str(error))
          continue
      if url and url not in urls:
        urls.append(url)
    if urls:
      product["image_url"] = urls[0]
      product["extra_image_urls"] = "\n".join(urls[1:12])
  _save_pdf_draft_rows(import_row, products)
  checkpoint["image_count"] = max(checkpoint.get("image_count", 0), total)
  checkpoint["image_uploaded"] = checkpoint.get("image_uploaded", 0) + uploaded
  checkpoint["needs_cloud_retry"] = bool(failed)
  if failed:
    checkpoint.setdefault("warnings", []).extend(failed[:20])
  import_row.update(
    checkpoint=checkpoint,
    source_file=None,
    updated_at=datetime.now(timezone.utc)
  )
  if not failed:
    _delete_xlsx_upload_chunks(import_row)
  return {
    "ok": not failed,
    "message": "Загружено новых фото: {}.{}".format(
      uploaded, " Осталось ошибок: {}.".format(len(failed)) if failed else ""
    ),
    "errors": failed[:20]
  }


def _resume_xlsx_catalog_draft(import_row):
  if import_row["status"] not in ("xlsx_paused", "xlsx_failed"):
    return {"ok": False, "message": "Продолжить можно только приостановленный или ошибочный XLSX-импорт."}
  if not _has_xlsx_source(import_row):
    return {"ok": False, "message": "Исходный XLSX недоступен. Загрузите файл повторно."}
  if not _has_active_import_capacity():
    return {"ok": False, "message": "Достигнут лимит активных импортов. Дождитесь завершения текущих задач."}
  checkpoint = import_row["checkpoint"] or {}
  checkpoint.pop("error", None)
  checkpoint["pause_requested"] = False
  import_row.update(status="xlsx_processing", checkpoint=checkpoint,
                    updated_at=datetime.now(timezone.utc))
  _launch_xlsx_processing(import_row)
  return {"ok": True, "message": "XLSX продолжит обработку с последней сохранённой строки."}


@anvil.server.background_task
def retry_xlsx_catalog_draft_images(draft_id):
  import_row = app_tables.imports.get_by_id(draft_id)
  if (import_row is None or import_row["format"] != "xlsx"
      or import_row["status"] != "xlsx_images_processing"):
    return
  try:
    result = _retry_xlsx_draft_images(import_row)
  except ImportInputError as error:
    current = app_tables.imports.get_by_id(draft_id)
    if current is not None:
      checkpoint = current["checkpoint"] or {}
      checkpoint["needs_cloud_retry"] = True
      checkpoint["error"] = str(error)
      current.update(status="xlsx_draft", checkpoint=checkpoint,
                     updated_at=datetime.now(timezone.utc))
    return {"ok": False, "message": str(error)}
  except Exception:
    current = app_tables.imports.get_by_id(draft_id)
    if current is not None:
      current.update(status="xlsx_draft", updated_at=datetime.now(timezone.utc))
    raise
  current = app_tables.imports.get_by_id(draft_id)
  if current is not None:
    checkpoint = current["checkpoint"] or {}
    checkpoint.pop("error", None)
    current.update(status="xlsx_draft", checkpoint=checkpoint,
                   updated_at=datetime.now(timezone.utc))
  return result


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def resume_pdf_catalog_draft(draft_id):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для продолжения импорта каталога.")
  if isinstance(draft_id, str) and draft_id:
    row = app_tables.imports.get_by_id(draft_id)
    if row is not None and row["format"] == "xlsx":
      return _resume_xlsx_catalog_draft(row)
  return _resume_pdf_catalog_draft(draft_id, user)


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def retry_pdf_catalog_draft(draft_id):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для повтора импорта каталога.")
  if isinstance(draft_id, str) and draft_id:
    row = app_tables.imports.get_by_id(draft_id)
    if row is not None and row["format"] == "xlsx":
      if row["status"] in ("xlsx_failed", "xlsx_paused"):
        return _resume_xlsx_catalog_draft(row)
      if row["status"] != "xlsx_draft":
        return {"ok": False, "message": "Подождите завершения текущей обработки XLSX."}
      checkpoint = row["checkpoint"] or {}
      if not checkpoint.get("needs_cloud_retry"):
        return {"ok": False, "message": "Повторная загрузка изображений не требуется."}
      checkpoint["error"] = ""
      row.update(status="xlsx_images_processing", checkpoint=checkpoint,
                 updated_at=datetime.now(timezone.utc))
      try:
        anvil.server.launch_background_task(
          "retry_xlsx_catalog_draft_images", row.get_id()
        )
      except Exception:
        row.update(status="xlsx_draft", updated_at=datetime.now(timezone.utc))
        raise
      return {"ok": True, "message": "Повтор загрузки XLSX-изображений запущен в фоне."}
  return _resume_pdf_catalog_draft(draft_id, user)


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def pause_pdf_catalog_draft(draft_id):
  Core.require_permission("import.manage")
  if not isinstance(draft_id, str) or not draft_id:
    return {"ok": False, "message": "Выберите PDF для остановки."}
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] not in ("pdf", "xlsx"):
    return {"ok": False, "message": "Импорт не найден."}
  processing_status = "pdf_processing" if import_row["format"] == "pdf" else "xlsx_processing"
  if import_row["status"] != processing_status:
    return {"ok": False, "message": "Сейчас нет активной обработки файла."}
  checkpoint = import_row["checkpoint"] or {}
  checkpoint["pause_requested"] = True
  import_row.update(checkpoint=checkpoint, updated_at=datetime.now(timezone.utc))
  return {"ok": True, "message": "Остановка запрошена. Текущая страница или пакет строк сохранится, затем импорт приостановится."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def get_pdf_catalog_drafts():
  Core.require_permission("import.manage")
  fields = q.fetch_only(
    "source_name", "status", "total", "processed",
    "imported", "created_at", "updated_at", "checkpoint", "source_file"
  )
  rows = list(app_tables.imports.search(
    fields, order_by("created_at", ascending=False), format="pdf"
  )[:MAX_PDF_DRAFTS]) + list(app_tables.imports.search(
    fields, order_by("created_at", ascending=False), format="xlsx"
  )[:MAX_PDF_DRAFTS])
  rows.sort(key=lambda row: row["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
  result_rows = []
  for row in rows:
    checkpoint = row["checkpoint"] or {}
    page_total = checkpoint.get("page_total", 0) or 0
    page_progress = checkpoint.get("page_progress", 0) or 0
    is_xlsx = row["format"] == "xlsx"
    if is_xlsx and row["status"] == "xlsx_uploading":
      progress_total = checkpoint.get("source_size", 0) or 0
      progress_done = checkpoint.get("uploaded_bytes", 0) or 0
    else:
      progress_total = checkpoint.get("row_count", 0) if is_xlsx else page_total
      progress_done = checkpoint.get("row_progress", 0) if is_xlsx else page_progress
    if row["status"] == "xlsx_images_processing":
      progress_total = checkpoint.get("image_count", 0) or 0
      progress_done = checkpoint.get("image_uploaded", 0) or 0
    result_rows.append({
      "id": row.get_id(), "source_name": row["source_name"],
      "format": row["format"],
      "status": row["status"], "total": row["total"] or 0,
      "processed": progress_done, "page_total": progress_total,
      "row_total": progress_total, "sheet_count": checkpoint.get("sheet_count", 0),
      "progress_percent": int(progress_done * 100 / progress_total) if progress_total else 0,
      "upload_paused": bool(checkpoint.get("upload_paused")),
      "failed_pages": len(checkpoint.get("failed_pages", [])),
      "file_size": checkpoint.get("source_size", row["source_file"].length if row["source_file"] else 0),
      "imported": row["imported"] or 0,
      "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M UTC")
      if row["created_at"] else ""
    })
  return {"ok": True, "rows": result_rows}


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def get_pdf_catalog_draft(draft_id):
  Core.require_permission("import.manage")
  if not isinstance(draft_id, str) or not draft_id:
    return {"ok": False, "message": "Выберите черновик импорта."}
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] not in ("pdf", "xlsx"):
    return {"ok": False, "message": "Черновик импорта не найден."}
  is_xlsx = import_row["format"] == "xlsx"
  checkpoint = import_row["checkpoint"] or {}
  category_rows = cast(Any, Catalog)._category_options()
  by_code = {row["code"]: row for row in category_rows}
  categories = [{
    "code": row["code"], "title": _pdf_category_path(row, by_code),
    "parent_code": row.get("parent_code")
  } for row in category_rows]
  products = _pdf_draft_rows(import_row)
  if not products:
    products = checkpoint.get("products", [])
  image_options = []
  seen_image_urls = set()
  for page_row in app_tables.pdf_draft_pages.search(
    q.fetch_only("page_number", "image_assets"), **{"import": import_row}
  ):
    for asset in page_row["image_assets"] or []:
      url = asset.get("url")
      if not isinstance(url, str) or not url.startswith("https://") or url in seen_image_urls:
        continue
      seen_image_urls.add(url)
      image_options.append({
        "url": url, "page": page_row["page_number"],
        "name": asset.get("name") or "Фото страницы {}".format(page_row["page_number"]),
        "size": asset.get("size", 0) or 0
      })
  if is_xlsx:
    for product in products:
      for index, url in enumerate([product.get("image_url", "")] +
                                  (product.get("extra_image_urls", "").splitlines()
                                   if isinstance(product.get("extra_image_urls"), str) else [])):
        url = url.strip() if isinstance(url, str) else ""
        if url.startswith("https://") and url not in seen_image_urls:
          seen_image_urls.add(url)
          image_options.append({
            "url": url, "page": None,
            "name": "Изображение {}".format(len(image_options) + 1),
            "size": 0
          })
  if is_xlsx and import_row["status"] == "xlsx_uploading":
    progress_total = checkpoint.get("source_size", 0) or 0
    progress_done = checkpoint.get("uploaded_bytes", 0) or 0
  else:
    progress_total = checkpoint.get("row_count", 0) if is_xlsx else checkpoint.get("page_total", 0)
    progress_done = checkpoint.get("row_progress", 0) if is_xlsx else checkpoint.get("page_progress", 0)
  if import_row["status"] == "xlsx_images_processing":
    progress_total = checkpoint.get("image_count", 0) or 0
    progress_done = checkpoint.get("image_uploaded", 0) or 0
  draft_status = "xlsx_draft" if is_xlsx else "pdf_draft"
  failed_status = "xlsx_failed" if is_xlsx else "pdf_failed"
  paused_status = "xlsx_paused" if is_xlsx else "pdf_paused"
  return {
    "ok": True, "id": import_row.get_id(), "source_name": import_row["source_name"],
    "format": import_row["format"], "status": import_row["status"], "products": products,
    "warnings": checkpoint.get("warnings", []),
    "extracted_text": checkpoint.get("pdf_text", ""),
    "page_count": checkpoint.get("page_total", 0),
    "page_progress": checkpoint.get("page_progress", 0),
    "row_count": checkpoint.get("row_count", 0),
    "row_progress": checkpoint.get("row_progress", 0),
    "uploaded_bytes": checkpoint.get("uploaded_bytes", 0),
    "upload_paused": bool(checkpoint.get("upload_paused")),
    "sheet_count": checkpoint.get("sheet_count", 0),
    "image_count": checkpoint.get("image_count", 0),
    "image_uploaded": checkpoint.get("image_uploaded", 0),
    "unassigned_images": checkpoint.get("unassigned_images", []),
    "image_options": image_options,
    "failed_pages": checkpoint.get("failed_pages", []),
    "progress_percent": int(
      progress_done * 100 / progress_total
    ) if progress_total else 0,
    "error": checkpoint.get("error", ""),
    "retry_available": (_has_xlsx_source(import_row) if is_xlsx else bool(import_row["source_file"]))
      and (import_row["status"] in (failed_status, paused_status)
           or (is_xlsx and import_row["status"] == draft_status
               and checkpoint.get("needs_cloud_retry"))
           or (not is_xlsx and import_row["status"] == draft_status
               and checkpoint.get("needs_retry"))),
    "pause_available": import_row["status"] == "xlsx_processing" if is_xlsx else import_row["status"] == "pdf_processing",
    "resume_available": (_has_xlsx_source(import_row) if is_xlsx else bool(import_row["source_file"]))
      and import_row["status"] == paused_status,
    "file_size": checkpoint.get("source_size", import_row["source_file"].length if import_row["source_file"] else 0),
    "category_options": categories
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def get_pdf_catalog_draft_page(draft_id, page_number):
  Core.require_permission("import.manage")
  if not isinstance(draft_id, str) or not draft_id:
    return {"ok": False, "message": "Выберите PDF-черновик."}
  if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
    return {"ok": False, "message": "Укажите страницу PDF."}
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] != "pdf":
    return {"ok": False, "message": "PDF-черновик не найден."}
  page_filter = {"import": import_row, "page_number": page_number}
  row = next(iter(app_tables.pdf_draft_pages.search(**page_filter)), None)
  if row is None:
    return {"ok": False, "message": "Страница ещё не обработана."}
  return {
    "ok": True, "page": page_number, "text": row["text"] or "",
    "images": row["image_assets"] or []
  }


def _clean_pdf_product(product):
  if not isinstance(product, dict):
    return None, "Строка товара должна быть объектом."
  text_fields = {
    "brand": 80, "model": 120, "sku": 80, "type": 80,
    "series": 100, "description": 2000, "category_code": 100, "subcategory_code": 100,
    "evidence": 400, "sale_price": 40, "currency": 3,
    "purchase_price": 40, "special_price": 40, "discount": 40,
    "markup": 40, "installation_price": 40, "minimum_stock": 40,
    "quantity": 40, "image_url": 1000, "extra_image_urls": 12000,
    "documents_json": 10000
  }
  cleaned = {}
  for field, limit in text_fields.items():
    value = product.get(field, "")
    if value is None:
      value = ""
    if not isinstance(value, str) or len(value) > limit:
      return None, "Поле «{}» имеет неверный формат или слишком длинное значение.".format(field)
    cleaned[field] = value.strip()
  specs_json = product.get("specs_json", "{}")
  if not isinstance(specs_json, str) or len(specs_json) > 65000:
    return None, "JSON характеристик слишком велик (максимум 65 КБ)."
  try:
    specs = json.loads(specs_json or "{}")
  except json.JSONDecodeError:
    return None, "Проверьте JSON в поле характеристик."
  if not isinstance(specs, dict) or len(specs) > 100:
    return None, "Характеристики должны быть JSON-объектом не более чем из 100 строк."
  for key, value in specs.items():
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
      return None, "В характеристиках есть неподдерживаемое поле «{}».".format(key)
    if isinstance(value, dict):
      if set(value) - {"value", "unit"}:
        return None, "Проверьте значение или единицу характеристики «{}».".format(key)
      raw_value, raw_unit = value.get("value"), value.get("unit", "")
      if (isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float))
          or len(str(raw_value)) > 1000 or not isinstance(raw_unit, str) or len(raw_unit) > 32):
        return None, "Проверьте значение или единицу характеристики «{}».".format(key)
      value = {"value": str(raw_value), "unit": raw_unit}
    elif isinstance(value, bool) or not isinstance(value, (str, int, float)):
      return None, "В характеристиках есть неподдерживаемое поле «{}».".format(key)
    elif len(str(value)) > 1000:
      return None, "Значение характеристики слишком длинное."
  cleaned["specs_json"] = json.dumps(specs, ensure_ascii=False, indent=2)
  for field in (
    "sale_price", "purchase_price", "special_price", "discount",
    "markup", "installation_price", "quantity", "minimum_stock"
  ):
    if cleaned[field]:
      amount, error = _number(
        cleaned[field], field, 100 if field == "discount" else None
      )
      if error:
        return None, error
      cleaned[field] = str(amount)
  if cleaned["currency"] and (
    len(cleaned["currency"]) != 3 or not cleaned["currency"].isascii()
    or not cleaned["currency"].isalpha()
  ):
    return None, "Код валюты должен содержать три латинские буквы."
  image_urls = []
  if cleaned["image_url"]:
    image_urls.append(cleaned["image_url"])
  if cleaned["extra_image_urls"]:
    image_urls.extend(
      line.strip() for line in cleaned["extra_image_urls"].splitlines()
      if line.strip()
    )
  if len(image_urls) > 12:
    return None, "К товару можно привязать не более 12 фотографий из PDF."
  safe_image_urls = []
  for image_url in image_urls:
    if len(image_url) > 1000 or _remote_url_error(image_url):
      return None, "Фотографии должны быть публичными HTTPS-ссылками."
    if image_url not in safe_image_urls:
      safe_image_urls.append(image_url)
  cleaned["image_urls"] = safe_image_urls
  try:
    documents = json.loads(cleaned["documents_json"] or "[]")
  except json.JSONDecodeError:
    return None, "Проверьте JSON документов."
  if not isinstance(documents, list) or len(documents) > 20:
    return None, "Документы должны быть списком не более чем из 20 записей."
  safe_documents = []
  for document in documents:
    if not isinstance(document, dict):
      return None, "Каждый документ должен содержать название и ссылку."
    title, url = document.get("title", ""), document.get("url", "")
    if not isinstance(title, str) or len(title) > 120 or not isinstance(url, str) or len(url) > 1000:
      return None, "Проверьте название или ссылку документа."
    if url and _remote_url_error(url):
      return None, "Документы должны быть публичными HTTPS-ссылками."
    if title.strip() and url.strip():
      safe_documents.append({"title": title.strip(), "url": url.strip()})
  cleaned["documents_json"] = json.dumps(safe_documents, ensure_ascii=False, indent=2)
  source_page = product.get("source_page")
  if source_page is not None and (
    isinstance(source_page, bool) or not isinstance(source_page, int)
    or source_page < 1 or source_page > MAX_PDF_PAGES
  ):
    return None, "Номер страницы источника имеет неверный формат."
  cleaned["source_page"] = source_page
  confidence = product.get("confidence")
  if confidence is not None and (
    isinstance(confidence, bool) or not isinstance(confidence, (int, float))
    or not math.isfinite(confidence) or confidence < 0 or confidence > 1
  ):
    return None, "Оценка уверенности должна быть от 0 до 1."
  cleaned["confidence"] = confidence
  return cleaned, None


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def save_pdf_catalog_draft(draft_id, products=None, action="save"):
  user = Core.require_permission("import.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для изменения импорта.")
  if action not in ("save", "approve", "reject"):
    return {"ok": False, "message": "Выберите сохранение, утверждение или отклонение черновика."}
  if not isinstance(draft_id, str) or not draft_id:
    return {"ok": False, "message": "Выберите черновик импорта."}
  import_row = app_tables.imports.get_by_id(draft_id)
  if import_row is None or import_row["format"] not in ("pdf", "xlsx"):
    return {"ok": False, "message": "Черновик импорта не найден."}
  is_xlsx = import_row["format"] == "xlsx"
  expected_draft_status = "xlsx_draft" if is_xlsx else "pdf_draft"
  if import_row["status"] != expected_draft_status:
    return {"ok": False, "message": "Этот черновик уже закрыт или ещё обрабатывается."}
  checkpoint = import_row["checkpoint"] or {}
  if action == "reject":
    now = datetime.now(timezone.utc)
    products_count = len(_pdf_draft_rows(import_row)) or len(checkpoint.get("products", []))
    import_row.update(
      status="xlsx_rejected" if is_xlsx else "pdf_rejected",
      source_file=None, processed=products_count,
      updated_at=now
    )
    if is_xlsx:
      _delete_xlsx_upload_chunks(import_row)
    Core.log_audit(
      actor=user, action="catalog.{}_draft_rejected".format(import_row["format"]), entity_type="import",
      entity_id=import_row.get_id(), details={"products": products_count},
      created_at=now
    )
    return {"ok": True, "message": "Черновик {} отклонён; товары не добавлены в каталог.".format(import_row["format"].upper())}

  if not isinstance(products, list) or len(products) > MAX_PDF_DRAFT_PRODUCTS:
    return {"ok": False, "message": "В черновике может быть не более {} товарных строк.".format(MAX_PDF_DRAFT_PRODUCTS)}
  cleaned_products = []
  for index, product in enumerate(products, start=1):
    cleaned, error = _clean_pdf_product(product)
    if error:
      return {"ok": False, "message": "Товар {}: {}".format(index, error)}
    cleaned_products.append(cleaned)

  if action == "save":
    now = datetime.now(timezone.utc)
    checkpoint.pop("products", None)
    _save_pdf_draft_rows(import_row, cleaned_products)
    import_row.update(
      checkpoint=checkpoint, total=len(cleaned_products), updated_at=now
    )
    Core.log_audit(
      actor=user, action="catalog.{}_draft_saved".format(import_row["format"]), entity_type="import",
      entity_id=import_row.get_id(), details={"products": len(cleaned_products)},
      created_at=now
    )
    return {"ok": True, "message": "Изменения черновика {} сохранены.".format(import_row["format"].upper())}

  if not Core.has_permission(user, "catalog.manage"):
    return {"ok": False, "message": "Для утверждения требуется право управления каталогом."}
  if not cleaned_products:
    return {"ok": False, "message": "Добавьте хотя бы один товар перед утверждением."}

  Catalog.ensure_catalog_categories()
  category_rows = list(app_tables.catalog_categories.search(active=True))
  import_records = []
  validation_errors = []
  for index, product in enumerate(cleaned_products, start=1):
    record = {
      "brand": product["brand"], "model": product["model"],
      "sku": product["sku"], "type": product["type"],
      "series": product["series"],
      "description": product["description"],
      "category_code": product["category_code"],
      "subcategory_code": product["subcategory_code"],
      "sale_price": product["sale_price"],
      "purchase_price": product["purchase_price"],
      "special_price": product["special_price"],
      "discount": product["discount"], "markup": product["markup"],
      "installation_price": product["installation_price"],
      "currency": product["currency"], "quantity": product["quantity"],
      "minimum_stock": product["minimum_stock"],
      "image_url": product["image_urls"][0] if product["image_urls"] else ""
    }
    specs = json.loads(product["specs_json"] or "{}")
    record["specifications"] = specs
    _, error = _prepare_record(record, category_rows, import_row["source_name"], "")
    if error:
      validation_errors.append("Товар {}: {}".format(index, error))
    import_records.append(record)
  duplicates = _duplicate_indexes(import_records)
  if duplicates:
    first_seen = {}
    for index, record in enumerate(import_records):
      key = _record_key(record)
      if key is None:
        continue
      if index in duplicates:
        validation_errors.append(
          "Товары {} и {} дублируют друг друга.".format(
            first_seen[key] + 1, index + 1
          )
        )
      else:
        first_seen[key] = index
  if validation_errors:
    return {"ok": False, "message": "Исправьте ошибки перед утверждением.", "errors": validation_errors}

  now = datetime.now(timezone.utc)
  _save_pdf_draft_rows(import_row, cleaned_products)
  imported = 0
  skipped = 0
  for index, record in enumerate(import_records):
    state, message = _apply_record(record, category_rows, import_row, "", now)
    prepared = cleaned_products[index]
    _, product_row = Catalog.find_import_product(
      prepared["brand"], prepared["model"], prepared["sku"]
    )
    if product_row is not None:
      media_rows = list(app_tables.product_media.search(
        q.fetch_only("url", "type", "is_primary"), product=product_row
      ))
      existing_urls = {row["url"] for row in media_rows if row["url"]}
      for image_index, image_url in enumerate(prepared["image_urls"]):
        if image_url in existing_urls:
          continue
        app_tables.product_media.add_row(
          product=product_row, url=image_url,
          type="primary" if image_index == 0 and not existing_urls else "gallery",
          is_primary=(image_index == 0 and not existing_urls), sort_order=image_index,
          alt_text="{} {}".format(prepared["brand"], prepared["model"]).strip(),
          source="{}: {}".format(import_row["format"].upper(), import_row["source_name"]),
          checksum="", created_at=now
        )
        existing_urls.add(image_url)
      for document in json.loads(prepared["documents_json"] or "[]"):
        if next(iter(app_tables.catalog_documents.search(
          q.fetch_only("url"), product=product_row, url=document["url"]
        )), None) is None:
          app_tables.catalog_documents.add_row(
            title=document["title"], kind="technical", product=product_row,
            url=document["url"], sort_order=0,
            created_at=now
          )
    if state == "imported":
      imported += 1
    else:
      skipped += 1
      _log(import_row, "warning", message or "Запись не изменила существующий товар.", index + 1)
  checkpoint.pop("products", None)
  import_row.update(
    checkpoint=checkpoint, status="xlsx_approved" if is_xlsx else "pdf_approved", total=len(import_records),
    processed=len(import_records), imported=imported, skipped=skipped,
    source_file=import_row["source_file"] if checkpoint.get("needs_retry") else None,
    updated_at=now
  )
  if is_xlsx:
    _delete_xlsx_upload_chunks(import_row)
  _log(import_row, "info", "Утверждено товаров: {}; без изменений: {}.".format(imported, skipped))
  Core.log_audit(
    actor=user, action="catalog.{}_draft_approved".format(import_row["format"]), entity_type="import",
    entity_id=import_row.get_id(),
    details={"products": len(import_records), "imported": imported, "skipped": skipped},
    created_at=now
  )
  return {
    "ok": True,
    "message": "Черновик утверждён. Добавлено/обновлено: {}; без изменений: {}.".format(imported, skipped)
  }
