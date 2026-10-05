"""Managed two-level site links stored in the existing system settings table."""

from datetime import datetime, timezone
import re
from typing import Any, cast
from urllib.parse import urlsplit
import uuid

import anvil.server
from anvil.tables import app_tables
import Core


MENU_SETTING_KEY = "site.navigation_menu"
_SAFE_ID = re.compile(r"^[a-f0-9]{16,32}$")


def _stored_items():
  row = app_tables.system_settings.get(key=MENU_SETTING_KEY)
  value = row["value"] if row is not None else []
  if not isinstance(value, list):
    return []
  return [dict(item) for item in value if isinstance(item, dict)]


def _safe_url(value, image=False):
  if not isinstance(value, str) or len(value) > 1000:
    return False
  value = value.strip()
  if "\\" in value or any(ord(char) < 32 for char in value):
    return False
  if not value:
    return image
  if value.startswith("/") and not value.startswith("//"):
    return True
  if value.startswith("_/theme/"):
    return image
  try:
    parts = urlsplit(value)
  except ValueError:
    return False
  return bool(
    parts.scheme == "https" and parts.netloc
    and not parts.username and not parts.password and not parts.fragment
  )


def _normalized_items(raw_items):
  if not isinstance(raw_items, list) or len(raw_items) > 40:
    return None, "В меню может быть не более 40 пунктов."
  cleaned = []
  used_ids = set()
  for index, raw in enumerate(raw_items):
    if not isinstance(raw, dict):
      return None, "Пункт меню {} имеет неверный формат.".format(index + 1)
    item_id = raw.get("id")
    if item_id in (None, ""):
      item_id = uuid.uuid4().hex
    if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id) or item_id in used_ids:
      return None, "Проверьте уникальные идентификаторы пунктов меню."
    used_ids.add(item_id)
    title = raw.get("title", "")
    url = raw.get("url", "")
    image_url = raw.get("image_url", "")
    parent_id = raw.get("parent_id") or None
    enabled = raw.get("enabled", True)
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
      return None, "Название пункта меню должно содержать от 1 до 80 символов."
    if not isinstance(url, str) or not _safe_url(url):
      return None, "Для пункта «{}» укажите HTTPS-ссылку или путь сайта.".format(title.strip())
    if not isinstance(image_url, str) or not _safe_url(image_url, image=True):
      return None, "Для пункта «{}» укажите HTTPS-ссылку или путь к изображению темы.".format(title.strip())
    if not isinstance(enabled, bool):
      return None, "Проверьте состояние пункта «{}».".format(title.strip())
    if parent_id is not None and not isinstance(parent_id, str):
      return None, "Родительский пункт «{}» отсутствует в меню.".format(title.strip())
    try:
      sort_order = int(raw.get("sort_order", 0))
    except (TypeError, ValueError, OverflowError):
      return None, "Порядок пункта «{}» должен быть целым числом.".format(title.strip())
    if isinstance(raw.get("sort_order", 0), bool) or not 0 <= sort_order <= 100000:
      return None, "Порядок пункта «{}» должен быть от 0 до 100000.".format(title.strip())
    cleaned.append({
      "id": item_id, "title": title.strip(), "url": url.strip(),
      "image_url": image_url.strip(), "parent_id": parent_id,
      "sort_order": sort_order, "enabled": enabled
    })

  items_by_id = {item["id"]: item for item in cleaned}
  child_ids = {item["parent_id"] for item in cleaned if item["parent_id"]}
  for item in cleaned:
    parent_id = item["parent_id"]
    if parent_id and parent_id not in items_by_id:
      return None, "Родительский пункт «{}» отсутствует в меню.".format(item["title"])
    if parent_id and (parent_id == item["id"] or parent_id in child_ids):
      return None, "В меню разрешено только два уровня вложенности."
    visited = {item["id"]}
    current = item
    while current["parent_id"]:
      parent_id = current["parent_id"]
      if parent_id in visited:
        return None, "В меню обнаружена циклическая вложенность."
      visited.add(parent_id)
      current = items_by_id[parent_id]
  return cleaned, None


def _menu_tree(items, enabled_only=True):
  by_id = {item["id"]: dict(item, children=[]) for item in items}
  roots = []
  for item in items:
    node = by_id[item["id"]]
    if enabled_only and not item["enabled"]:
      continue
    parent = by_id.get(item["parent_id"])
    if parent is None:
      roots.append(node)
    elif not enabled_only or parent["enabled"]:
      parent["children"].append(node)

  def ordered(nodes):
    result = []
    for node in sorted(nodes, key=lambda row: (row["sort_order"], row["title"].casefold())):
      node["children"] = ordered(node["children"])
      result.append(node)
    return result

  return ordered(roots)


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def get_managed_site_menu():
  Core.require_permission("cms.manage")
  items = _stored_items()
  title_by_id = {item.get("id"): item.get("title", "") for item in items}
  items.sort(key=lambda item: (
    str(item.get("parent_id") or ""), item.get("sort_order", 0),
    item.get("title", "").casefold()
  ))
  return {
    "ok": True,
    "items": [
      dict(item, parent_title=title_by_id.get(item.get("parent_id"), ""))
      for item in items
    ]
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def save_managed_site_menu(raw_items):
  actor = Core.require_permission("cms.manage")
  if actor is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для изменения меню сайта.")
  items, error = _normalized_items(raw_items)
  if error or items is None:
    return {"ok": False, "message": error}
  now = datetime.now(timezone.utc)
  row = app_tables.system_settings.get(key=MENU_SETTING_KEY)
  values: dict[str, Any] = {
    "key": MENU_SETTING_KEY, "value": items,
    "updated_at": now, "updated_by": actor
  }
  if row is None:
    cast(Any, app_tables.system_settings).add_row(**values)
  else:
    row.update(value=items, updated_at=now, updated_by=actor)
  Core.log_audit(
    actor=actor, action="site.navigation_menu_saved",
    entity_type="site_menu", entity_id=MENU_SETTING_KEY,
    details={"items": len(items), "enabled": sum(1 for item in items if item["enabled"])},
    created_at=now
  )
  return {"ok": True, "message": "Меню сайта сохранено.", "items": items}


@anvil.server.callable
def get_public_site_menu():
  return {"ok": True, "items": _menu_tree(_stored_items())}


def get_public_site_menu_data():
  """Internal payload helper for the site header's existing menu request."""
  return _menu_tree(_stored_items())
