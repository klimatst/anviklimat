"""Read-only checks for catalogue records, media, documents and imports."""

from urllib.parse import urlsplit

import anvil.server
from anvil.tables import app_tables, query as q
import Core
import EngineeringCore


_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def _safe_link(value):
  if not isinstance(value, str) or not value.strip():
    return False
  value = value.strip()
  if value.startswith(("/_/", "_/theme/")):
    return True
  try:
    parts = urlsplit(value)
  except ValueError:
    return False
  return bool(
    parts.scheme == "https" and parts.netloc
    and not parts.username and not parts.password and not parts.fragment
  )


def _issue(code, severity, title, detail, target="", target_id=None,
           category_code="", action_label=""):
  return {
    "code": code, "severity": severity, "title": title,
    "detail": detail, "target": target, "target_id": target_id,
    "category_code": category_code, "action_label": action_label
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_system_diagnostics(search_text="", severity="all", limit=300):
  Core.require_admin_user()
  if not isinstance(search_text, str) or len(search_text) > 120:
    return {"ok": False, "message": "Поиск должен содержать не более 120 символов.", "issues": [], "summary": []}
  if severity not in ("all", "error", "warning", "info"):
    return {"ok": False, "message": "Выберите допустимый уровень проблемы.", "issues": [], "summary": []}
  if isinstance(limit, bool):
    return {"ok": False, "message": "Лимит записей должен быть числом.", "issues": [], "summary": []}
  try:
    limit = int(limit)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Лимит записей должен быть числом.", "issues": [], "summary": []}
  if isinstance(limit, bool) or not 1 <= limit <= 1000:
    return {"ok": False, "message": "Лимит записей должен быть от 1 до 1000.", "issues": [], "summary": []}

  category_rows = list(app_tables.catalog_categories.search(
    q.fetch_only("code", "title", "parent", "active")
  ))
  categories_by_id = {row.get_id(): row for row in category_rows}
  child_ids = set()
  for row in category_rows:
    parent = row["parent"]
    if parent is not None:
      child_ids.add(parent.get_id())

  products = list(app_tables.products.search(
    q.fetch_only(
      "identity_key", "brand", "model", "sku", "sku_key", "category",
      "subcategory", "series", "description", "active"
    ),
    identity_key=q.not_(q.ilike("demo|%"))
  ))
  image_product_ids = {
    row["product"].get_id()
    for row in app_tables.product_media.search(
      q.fetch_only("product", "file_id", "url")
    )
    if row["product"] is not None and (row["file_id"] or row["url"])
  }

  issues = []
  category_product_ids = {}
  products_by_sku = {}
  products_by_identity = {}
  for product in products:
    product_id = str(product.get_id())
    model = (product["model"] or "").strip()
    sku = (product["sku"] or "").strip()
    brand = product["brand"]
    brand_title = brand["name"] if brand is not None else ""
    category = product["category"]
    subcategory = product["subcategory"]
    category_title = category["title"] if category is not None else ""
    if category is not None:
      category_product_ids.setdefault(category.get_id(), set()).add(product_id)
    if subcategory is not None:
      category_product_ids.setdefault(subcategory.get_id(), set()).add(product_id)

    missing = []
    if not model:
      missing.append("модель")
    if not brand_title:
      missing.append("бренд")
    if category is None:
      missing.append("категория")
    if not (product["description"] or "").strip():
      missing.append("описание")
    label = "{} {}".format(brand_title, model).strip() or "Товар без названия"
    if product_id not in image_product_ids:
      issues.append(_issue(
        "product_missing_image", "warning", "Товар без изображения", label,
        "product", product_id, action_label="Открыть товар"
      ))
    if missing:
      issues.append(_issue(
        "product_incomplete", "warning", "Карточка заполнена не полностью",
        "{} · не заполнено: {}".format(label, ", ".join(missing)),
        "product", product_id, action_label="Открыть товар"
      ))

    if subcategory is not None:
      parent = subcategory["parent"]
      if category is None or parent is None or parent.get_id() != category.get_id():
        issues.append(_issue(
          "product_category_link", "error", "Проверьте связь категории",
          "{} · подкатегория «{}» не относится к выбранной категории.".format(
            label, subcategory["title"]
          ), "product", product_id, action_label="Открыть товар"
        ))

    identity = (product["identity_key"] or "").strip().casefold()
    sku_key = (product["sku_key"] or sku).strip().casefold()
    if sku_key:
      products_by_sku.setdefault(sku_key, []).append((product_id, label, sku))
    if identity:
      products_by_identity.setdefault(identity, []).append((product_id, label, sku))

  duplicate_groups = {}
  duplicate_product_ids = set()
  for sku_key, rows in products_by_sku.items():
    if len(rows) > 1:
      duplicate_groups["sku:" + sku_key] = ("артикулу " + rows[0][2], rows)
      duplicate_product_ids.update(row[0] for row in rows)
  for identity, rows in products_by_identity.items():
    row_ids = {row[0] for row in rows}
    if len(rows) > 1 and not row_ids.issubset(duplicate_product_ids):
      duplicate_groups["identity:" + identity] = ("идентичности модели", rows)
      duplicate_product_ids.update(row_ids)
  for _, (match_label, rows) in duplicate_groups.items():
    first_id, first_label, _ = rows[0]
    names = ", ".join(row[1] for row in rows[:4])
    if len(rows) > 4:
      names += " и ещё {}".format(len(rows) - 4)
    issues.append(_issue(
      "duplicate_products", "warning", "Возможный дубль товара",
      "Совпадает {} · записей: {} · {}".format(match_label, len(rows), names),
      "product", first_id, action_label="Проверить товары"
    ))

  for category in category_rows:
    if (
      category["active"] and category.get_id() not in child_ids
      and not category_product_ids.get(category.get_id())
    ):
      issues.append(_issue(
        "empty_category", "info", "Пустая категория",
        category["title"] or "Категория без названия",
        "category", str(category.get_id()), category["code"] or "",
        "Открыть категорию"
      ))

  for document in app_tables.catalog_documents.search(
    q.fetch_only("title", "product", "series", "file", "url")
  ):
    if document["file"] is None and not (document["url"] or "").strip():
      product = document["product"]
      issues.append(_issue(
        "document_missing_file", "warning", "Документ без файла",
        document["title"] or "Документ не привязан к файлу",
        "product" if product is not None else "",
        str(product.get_id()) if product is not None else None,
        action_label="Открыть товар" if product is not None else ""
      ))
    elif document["url"] and not _safe_link(document["url"]):
      product = document["product"]
      issues.append(_issue(
        "document_invalid_link", "error", "Некорректная ссылка документа",
        document["title"] or "Проверьте HTTPS-ссылку документа",
        "product" if product is not None else "",
        str(product.get_id()) if product is not None else None,
        action_label="Открыть товар" if product is not None else ""
      ))

  for media in app_tables.product_media.search(
    q.fetch_only("product", "url", "source", "file_id")
  ):
    if media["url"] and not _safe_link(media["url"]):
      product = media["product"]
      issues.append(_issue(
        "media_invalid_link", "error", "Некорректная ссылка изображения",
        "Проверьте публичный HTTPS URL изображения.",
        "product" if product is not None else "",
        str(product.get_id()) if product is not None else None,
        action_label="Открыть товар" if product is not None else ""
      ))

  for import_row in app_tables.imports.search(
    q.fetch_only("source_name", "format", "status", "checkpoint", "processed", "total", "updated_at")
  ):
    checkpoint = import_row["checkpoint"] or {}
    if not isinstance(checkpoint, dict):
      checkpoint = {}
    failed_pages = checkpoint.get("failed_pages", [])
    if not isinstance(failed_pages, list):
      failed_pages = []
    has_errors = import_row["status"] in ("failed", "error", "pdf_failed")
    needs_retry = bool(checkpoint.get("needs_retry") or checkpoint.get("needs_cloud_retry"))
    if has_errors or needs_retry or failed_pages:
      source_name = import_row["source_name"] or "Импорт без имени"
      detail = "Статус: {}".format(import_row["status"] or "не указан")
      if failed_pages:
        detail += " · страниц с ошибкой: {}".format(len(failed_pages))
      elif needs_retry:
        detail += " · требуется повторная обработка"
      issues.append(_issue(
        "import_errors", "error" if has_errors else "warning",
        "Импорт требует внимания", "{} · {}".format(source_name, detail),
        "pdf_import" if import_row["format"] == "pdf" else "import",
        str(import_row.get_id()), action_label="Открыть импорт"
      ))

  try:
    engineering_gate = EngineeringCore.get_engineering_quality_gate()
  except Exception as exc:
    engineering_gate = {"ok": False, "message": "Engineering Quality Gate недоступен: {}".format(exc)}
  if engineering_gate.get("ok"):
    for item in engineering_gate.get("issues", [])[:60]:
      severity = "error" if item.get("severity") == "high" else "warning"
      issues.append(_issue(
        "engineering_lifecycle_gap", severity, "Инженерный lifecycle требует внимания",
        "{} · {}".format(item.get("project", "Проект"), item.get("message", "")),
        "project", item.get("project"), action_label="Открыть проекты"
      ))
  else:
    issues.append(_issue(
      "engineering_quality_gate_unavailable", "warning",
      "Engineering Quality Gate недоступен", engineering_gate.get("message", "Проверьте инженерное ядро.")
    ))

  for issue in issues:
    issue["search_key"] = " ".join((
      issue["code"], issue["title"], issue["detail"], issue["category_code"]
    )).casefold()
  search_key = search_text.strip().casefold()
  filtered = [
    item for item in issues
    if (severity == "all" or item["severity"] == severity)
    and (not search_key or search_key in item["search_key"])
  ]
  filtered.sort(key=lambda item: (
    _SEVERITY_RANK[item["severity"]], item["code"], item["title"].casefold()
  ))
  visible_issues = filtered[:limit]
  for issue in visible_issues:
    issue.pop("search_key", None)
  summary = {}
  for issue in issues:
    entry = summary.setdefault(issue["code"], {
      "code": issue["code"], "title": issue["title"],
      "severity": issue["severity"], "count": 0
    })
    entry["count"] += 1
  return {
    "ok": True, "summary": sorted(
      summary.values(), key=lambda item: (
        _SEVERITY_RANK[item["severity"]], item["title"].casefold()
      )
    ),
    "total": len(filtered), "available_total": len(issues),
    "has_more": len(filtered) > limit, "issues": visible_issues,
    "message": "Проверено товаров: {} · категорий: {} · документов и импортов.".format(
      len(products), len(category_rows)
    )
  }
