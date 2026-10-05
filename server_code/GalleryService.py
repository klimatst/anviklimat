from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import anvil.server
import Core
from anvil.tables import app_tables, order_by


DEFAULT_SETTINGS = {
  "gallery_title": "Наши работы",
  "gallery_intro": "Проекты по кондиционированию, вентиляции и инженерным системам.",
  "storage_provider": "Внешний медиасервер",
  "storage_base_url": "",
  "items_per_page": 60,
  "columns": 3,
  "image_ratio": "landscape",
  "show_locations": True,
  "show_dates": True,
  "featured_first": True
}


def _text(value, label, maximum, required=False):
  if value is None:
    value = ""
  if not isinstance(value, str):
    return None, "Проверьте поле «{}».".format(label)
  value = value.strip()
  if required and not value:
    return None, "Заполните поле «{}».".format(label)
  if len(value) > maximum:
    return None, "Сократите поле «{}» до {} символов.".format(label, maximum)
  return value, None


def _gallery_settings():
  settings = dict(DEFAULT_SETTINGS)
  row = app_tables.system_settings.get(key="gallery_settings")
  if row is not None and isinstance(row["value"], dict):
    for key in DEFAULT_SETTINGS:
      if key in row["value"]:
        settings[key] = row["value"][key]
  return settings


def _valid_https_url(value, label):
  clean, error = _text(value, label, 1000)
  if error or not clean:
    return clean, error
  parsed = urlparse(clean)
  if parsed.scheme.casefold() != "https" or not parsed.netloc or parsed.username or parsed.password:
    return None, "Укажите полный HTTPS-адрес для поля «{}».".format(label)
  return clean, None


def _resolve_image_url(value, base_url, label, required=True):
  candidate, error = _text(value, label, 1000, required=required)
  if error:
    return None, error
  if not candidate:
    return "", None
  parsed = urlparse(candidate)
  if parsed.scheme or parsed.netloc:
    return _valid_https_url(candidate, label)
  if not base_url:
    return None, "Укажите HTTPS-ссылку на фотографию или настройте базовый URL медиасервера."
  if candidate.startswith("//") or ".." in candidate.split("/"):
    return None, "Укажите безопасный относительный путь к фотографии."
  resolved = urljoin(base_url.rstrip("/") + "/", candidate.lstrip("/"))
  return _valid_https_url(resolved, label)


def _serialize_item(row, can_edit=False):
  image_url = row["image_url"] or ""
  return {
    "id": str(row.get_id()),
    "title": row["title"] or "",
    "description": row["description"] or "",
    "image_url": row["thumbnail_url"] or image_url,
    "full_image_url": image_url,
    "alt_text": row["alt_text"] or row["title"] or "",
    "category": row["category"] or "",
    "location": row["location"] or "",
    "completed_at": row["completed_at"] or "",
    "sort_order": row["sort_order"] or 0,
    "featured": bool(row["featured"]),
    "published": bool(row["published"]),
    "can_edit": can_edit
  }


def _items(include_drafts=False, limit=60):
  rows = list(app_tables.gallery_items.search(order_by("sort_order"))[:500])
  if not include_drafts:
    rows = [row for row in rows if row["published"]]
  settings = _gallery_settings()
  if settings["featured_first"]:
    rows.sort(key=lambda row: (not bool(row["featured"]), row["sort_order"] or 0))
  return [_serialize_item(row, can_edit=include_drafts) for row in rows[:limit]]


@anvil.server.callable
def get_public_gallery_page():
  settings = _gallery_settings()
  limit = settings["items_per_page"]
  if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 200:
    limit = DEFAULT_SETTINGS["items_per_page"]
  return {"settings": settings, "items": _items(limit=limit)}


@anvil.server.callable
def get_gallery_admin_state():
  if Core.get_admin_user() is None:
    return {"can_edit": False, "settings": dict(DEFAULT_SETTINGS), "items": []}
  return {
    "can_edit": True,
    "settings": _gallery_settings(),
    "items": _items(include_drafts=True, limit=500)
  }


@anvil.server.callable
def save_gallery_settings(values):
  user = Core.require_admin_user()
  if user is None:
    raise anvil.server.PermissionDenied("Доступ разрешён только администратору.")
  if not isinstance(values, dict):
    return {"ok": False, "message": "Настройки галереи имеют неверный формат."}

  result = dict(DEFAULT_SETTINGS)
  for key, label, maximum in (
    ("gallery_title", "Заголовок галереи", 100),
    ("gallery_intro", "Описание галереи", 500),
    ("storage_provider", "Название медиасервера", 80)
  ):
    value, error = _text(values.get(key), label, maximum, required=key != "gallery_intro")
    if error:
      return {"ok": False, "message": error}
    result[key] = value

  base_url, error = _valid_https_url(values.get("storage_base_url", ""), "Базовый URL медиасервера")
  if error:
    return {"ok": False, "message": error}
  result["storage_base_url"] = base_url
  try:
    result["items_per_page"] = int(values.get("items_per_page", 60))
    result["columns"] = int(values.get("columns", 3))
  except (TypeError, ValueError):
    return {"ok": False, "message": "Количество фотографий и столбцов должно быть целым числом."}
  if not 1 <= result["items_per_page"] <= 200:
    return {"ok": False, "message": "На странице можно показывать от 1 до 200 фотографий."}
  if result["columns"] not in (2, 3, 4):
    return {"ok": False, "message": "Выберите 2, 3 или 4 столбца галереи."}
  if values.get("image_ratio") not in ("landscape", "cinematic", "square"):
    return {"ok": False, "message": "Выберите доступный формат карточек."}
  result["image_ratio"] = values["image_ratio"]
  for key in ("show_locations", "show_dates", "featured_first"):
    if not isinstance(values.get(key), bool):
      return {"ok": False, "message": "Проверьте переключатели отображения галереи."}
    result[key] = values[key]

  now = datetime.now(timezone.utc)
  row = app_tables.system_settings.get(key="gallery_settings")
  if row is None:
    app_tables.system_settings.add_row(
      key="gallery_settings", value=result, updated_at=now, updated_by=user
    )
  else:
    row.update(value=result, updated_at=now, updated_by=user)
  Core.log_audit(
    actor=user, action="gallery.settings.updated", entity_type="gallery",
    entity_id="settings", details={"items_per_page": result["items_per_page"]},
    created_at=now
  )
  return {"ok": True, "message": "Настройки галереи сохранены.", "settings": result}


@anvil.server.callable
def save_gallery_item(values, item_id=None):
  user = Core.require_admin_user()
  if user is None:
    raise anvil.server.PermissionDenied("Доступ разрешён только администратору.")
  if not isinstance(values, dict):
    return {"ok": False, "message": "Карточка проекта имеет неверный формат."}
  settings = _gallery_settings()
  clean = {}
  for key, label, maximum, required in (
    ("title", "Название проекта", 120, True),
    ("description", "Описание проекта", 1200, False),
    ("alt_text", "Описание фотографии", 240, True),
    ("category", "Направление", 80, False),
    ("location", "Город или объект", 120, False),
    ("completed_at", "Дата завершения", 40, False)
  ):
    value, error = _text(values.get(key), label, maximum, required=required)
    if error:
      return {"ok": False, "message": error}
    clean[key] = value

  image_url, error = _resolve_image_url(
    values.get("image_url"), settings["storage_base_url"], "Основная фотография"
  )
  if error:
    return {"ok": False, "message": error}
  thumbnail_url = image_url
  if values.get("thumbnail_url"):
    thumbnail_url, error = _resolve_image_url(
      values["thumbnail_url"], settings["storage_base_url"], "Миниатюра"
    )
    if error:
      return {"ok": False, "message": error}

  try:
    sort_order = int(values.get("sort_order", 100))
  except (TypeError, ValueError):
    return {"ok": False, "message": "Порядок отображения должен быть целым числом."}
  if sort_order < 0 or sort_order > 100000:
    return {"ok": False, "message": "Порядок отображения должен быть от 0 до 100000."}
  for key in ("featured", "published"):
    if not isinstance(values.get(key), bool):
      return {"ok": False, "message": "Проверьте отметки «Избранное» и «Опубликовано»."}
    clean[key] = values[key]

  now = datetime.now(timezone.utc)
  clean.update(
    image_url=image_url, thumbnail_url=thumbnail_url,
    sort_order=sort_order, updated_at=now, updated_by=user
  )
  if item_id:
    if not isinstance(item_id, str):
      return {"ok": False, "message": "Некорректный номер карточки."}
    row = app_tables.gallery_items.get_by_id(item_id)
    if row is None:
      return {"ok": False, "message": "Карточка проекта больше не существует."}
    row.update(**clean)
    action = "gallery.item.updated"
  else:
    clean["created_at"] = now
    row = app_tables.gallery_items.add_row(**clean)
    action = "gallery.item.created"
  Core.log_audit(
    actor=user, action=action, entity_type="gallery_item",
    entity_id=str(row.get_id()), details={"title": clean["title"]}, created_at=now
  )
  return {"ok": True, "message": "Карточка проекта сохранена.", "item": _serialize_item(row, True)}


@anvil.server.callable
def delete_gallery_item(item_id):
  user = Core.require_admin_user()
  if user is None:
    raise anvil.server.PermissionDenied("Доступ разрешён только администратору.")
  if not isinstance(item_id, str) or not item_id:
    return {"ok": False, "message": "Некорректный номер карточки."}
  row = app_tables.gallery_items.get_by_id(item_id)
  if row is None:
    return {"ok": False, "message": "Карточка проекта не найдена."}
  title = row["title"] or ""
  row.delete()
  Core.log_audit(
    actor=user, action="gallery.item.deleted", entity_type="gallery_item",
    entity_id=item_id, details={"title": title}, created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Карточка проекта удалена."}
