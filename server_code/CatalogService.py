import anvil
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
import base64
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast
from urllib.parse import urlsplit

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import AdminStudio
import SiteMenuService


PAGE_SIZE = 24
CUSTOM_FIELDS_SETTING_KEY = "catalog.product_custom_fields"
CUSTOM_FIELD_TYPES = {
  "text", "number", "price", "date", "select", "multiselect",
  "toggle", "image", "file", "url", "rich_text"
}
ROOT_CATEGORIES = [
  ("vrf-vrv", "VRV / VRF-системы"),
  ("ventilation", "Вентиляция"),
  ("air-conditioning", "Кондиционирование"),
  ("humidification", "Системы увлажнения"),
  ("dehumidification", "Осушение"),
  ("air-quality", "Качество воздуха"),
  ("refrigeration", "Холодильное оборудование"),
  ("heating", "Отопление"),
  ("heat-pumps", "Тепловые насосы"),
  ("hydronics", "Гидравлика"),
  ("electrical", "Электрика"),
  ("automation-bms", "Автоматика и BMS"),
  ("installation", "Монтаж"),
  ("tools", "Инструменты"),
  ("materials", "Материалы"),
  ("spare-parts", "Запасные части"),
  ("humidifiers-purifiers", "Увлажнители и очистители"),
  ("heat-equipment", "Тепловое оборудование"),
  ("multi-split-systems", "Мульти сплит системы"),
  ("semi-industrial", "Полупромышленные системы"),
  ("hydromodules", "Гидромодули"),
  ("compressor-condensing-blocks", "Компрессорно-конденсаторные блоки"),
  ("large-capacity-split-systems", "Сплит-системы большой производительности"),
  ("precision-systems", "Прецизионные кондиционеры"),
  ("rooftop-systems", "Крышные кондиционеры"),
  ("drycoolers-condensers", "Драйкулеры и выносные конденсаторы"),
  ("industrial-heating", "Промышленное тепловое оборудование"),
  ("industrial-humidification", "Промышленные увлажнители воздуха"),
  ("control-units", "Узлы регулирования"),
  ("accessories-options", "Аксессуары и опции"),
  ("ahu-automation", "Автоматика для ПУ и ПВУ")
]
HUMIDIFICATION_CATEGORIES = [
  ("steam", "Паровые"),
  ("electrode", "Электродные"),
  ("ten", "ТЭН"),
  ("gas", "Газовые"),
  ("ultrasonic", "Ультразвуковые"),
  ("adiabatic", "Адиабатические"),
  ("high-pressure", "Высокого давления"),
  ("evaporative", "Испарительные"),
  ("duct", "Канальные"),
  ("room", "Комнатные"),
  ("industrial", "Промышленные"),
  ("ahu", "Для AHU"),
  ("water-treatment", "Водоподготовка"),
  ("reverse-osmosis", "Обратный осмос"),
  ("filters", "Фильтры"),
  ("pumps", "Насосы"),
  ("valves", "Клапаны"),
  ("sensors", "Датчики"),
  ("controllers", "Контроллеры"),
  ("bms", "BMS"),
  ("distributors", "Распределители"),
  ("nozzles", "Форсунки"),
  ("piping", "Трубопроводы"),
  ("drainage", "Дренаж"),
  ("installation", "Монтаж"),
  ("service", "Сервис")
]
CATALOG_CATEGORY_PHOTOS = {
  "air-conditioning": "conditioners.jpg",
  "vrf-vrv": "vrv-vrf.jpg",
  "ventilation": "ventilation.jpg",
  "refrigeration": "refrigeration.jpg",
  "materials": "materials.jpg",
  # Related equipment families share a real HVAC photograph until their own
  # product image has been attached in the catalog.
  "humidification": "ventilation.jpg",
  "dehumidification": "ventilation.jpg",
  "air-quality": "ventilation.jpg",
  "heating": "vrv-vrf.jpg",
  "heat-pumps": "vrv-vrf.jpg",
  "hydronics": "materials.jpg",
  "electrical": "materials.jpg",
  "automation-bms": "ventilation.jpg",
  "installation": "materials.jpg",
  "tools": "refrigeration.jpg",
  "spare-parts": "refrigeration.jpg"
}
HVAC_CATEGORY_GROUPS = {
  "air-conditioning": [
    ("split-systems", "Сплит-системы"),
    ("multi-split", "Мульти-сплит"),
    ("wall", "Настенные кондиционеры"),
    ("cassette", "Кассетные кондиционеры"),
    ("duct", "Канальные кондиционеры"),
    ("floor-ceiling", "Напольно-потолочные кондиционеры"),
    ("column", "Колонные кондиционеры"),
    ("portable", "Мобильные кондиционеры"),
    ("precision", "Прецизионные кондиционеры")
  ],
  "air-conditioning-split-systems": [
    ("inverter", "Инверторные сплит-системы"),
    ("on-off", "On/Off сплит-системы")
  ],
  "vrf-vrv": [
    ("outdoor-units", "Наружные блоки"),
    ("indoor-units", "Внутренние блоки"),
    ("wall-units", "Настенные внутренние блоки"),
    ("cassette-units", "Кассетные внутренние блоки"),
    ("duct-units", "Канальные внутренние блоки"),
    ("floor-ceiling-units", "Напольно-потолочные блоки"),
    ("branch-selectors", "Селекторные блоки"),
    ("controllers", "Пульты и системы управления")
  ],
  "ventilation": [
    ("ahu", "Приточно-вытяжные установки"),
    ("supply-units", "Приточные установки"),
    ("exhaust-units", "Вытяжные установки"),
    ("fans", "Вентиляторы"),
    ("heat-recovery", "Рекуператоры"),
    ("air-ducts", "Воздуховоды"),
    ("fittings", "Фасонные элементы"),
    ("grilles-diffusers", "Решётки и диффузоры"),
    ("dampers", "Воздушные клапаны")
  ],
  "refrigeration": [
    ("chillers", "Чиллеры"),
    ("fan-coils", "Фанкойлы")
  ],
  "heat-pumps": [
    ("air-air", "Тепловые насосы воздух — воздух"),
    ("air-water", "Тепловые насосы воздух — вода"),
    ("ground-water", "Геотермальные тепловые насосы"),
    ("monoblock", "Тепловые насосы моноблок"),
    ("split", "Тепловые насосы сплит-системы")
  ],
  "air-conditioning-split-systems": [
    ("inverter", "Инверторные сплит-системы"),
    ("on-off", "On/Off сплит-системы")
  ],
  "humidifiers-purifiers": [
    ("air-purifiers", "Очистители воздуха")
  ],
  "heat-equipment": [
    ("air-curtains", "Воздушно-тепловые завесы"),
    ("heat-guns", "Тепловые пушки"),
    ("electric-convectors", "Электрические конвекторы")
  ],
  "multi-split-systems": [
    ("indoor-blocks", "Внутренние блоки мульти сплит системы"),
    ("outdoor-blocks", "Внешние блоки мульти сплит системы")
  ],
  "semi-industrial": [
    ("cassette-type", "Кассетный тип"),
    ("console-type", "Консольный тип"),
    ("column-type", "Колонный тип"),
    ("duct-type", "Канальный тип"),
    ("external-blocks", "Внешние блоки")
  ],
  "hydromodules": [
    ("hydromodule-units", "Гидромодули для систем охлаждения и отопления")
  ],
  "compressor-condensing-blocks": [
    ("air-cooled", "С воздушным охлаждением"),
    ("water-cooled", "С водяным охлаждением")
  ],
  "large-capacity-split-systems": [
    ("outdoor-units", "Внешние блоки"),
    ("indoor-units", "Внутренние блоки")
  ],
  "precision-systems": [
    ("precision-room", "Системы для серверных и технологических помещений")
  ],
  "rooftop-systems": [
    ("rooftop-units", "Руфтопы для коммерческих объектов")
  ],
  "drycoolers-condensers": [
    ("drycoolers", "Драйкулеры"),
    ("remote-condensers", "Выносные конденсаторы")
  ],
  "industrial-heating": [
    ("water-air-heaters", "Водяные тепловентиляторы"),
    ("industrial-curtains", "Промышленные воздушно-тепловые завесы")
  ],
  "industrial-humidification": [
    ("industrial-steam", "Паровые увлажнители"),
    ("industrial-adiabatic", "Адиабатические увлажнители")
  ],
  "control-units": [
    ("fan-coil-valves", "Узлы обвязки фанкойлов"),
    ("hydraulic-control", "Гидравлические узлы регулирования")
  ],
  "accessories-options": [
    ("controls-accessories", "Пульты и системы управления"),
    ("installation-accessories", "Монтажные принадлежности")
  ],
  "ahu-automation": [
    ("supply-automation", "Автоматика приточных установок"),
    ("supply-exhaust-automation", "Автоматика приточно-вытяжных установок")
  ]
}

HOME_ROOT_CODES = {
  "air-conditioning", "humidifiers-purifiers", "heat-equipment",
  "multi-split-systems", "semi-industrial", "heat-pumps"
}

def _current_user():
  user = anvil.users.get_user()
  if user is not None:
    Core._ensure_core_data(user)
  return user


def _admin_user():
  return Core.get_admin_user()


def product_identity_key(brand_name, model, sku):
  brand_key = (brand_name or "").casefold()
  if brand_key:
    return "brand|{}|{}".format(brand_key, model.casefold())
  sku_key = (sku or "").casefold()
  if sku_key:
    return "sku|" + sku_key
  return "model|" + model.casefold()


def find_import_product(brand_name, model, sku):
  identity_key = product_identity_key(brand_name, model, sku)
  product = app_tables.products.get(identity_key=identity_key)
  brand_key = (brand_name or "").casefold()
  sku_key = (sku or "").casefold()
  if product is None and brand_key:
    product = app_tables.products.get(
      identity_key=brand_key + "|" + model.casefold()
    )
  if product is None and sku_key:
    product = app_tables.products.get(sku_key=sku_key)
  if product is None and not brand_key and not sku_key:
    product = app_tables.products.get(identity_key="|" + model.casefold())
  return identity_key, product


def _ensure_categories():
  category_table = cast(Any, app_tables.catalog_categories)
  existing = {
    row["code"]: row
    for row in app_tables.catalog_categories.search()
  }
  missing_roots = [
    {"code": code, "title": title, "parent": None, "active": True, "sort_order": order * 100}
    for order, (code, title) in enumerate(ROOT_CATEGORIES)
    if code not in existing
  ]
  if missing_roots:
    added_roots = category_table.add_rows(missing_roots)
    for values, row in zip(missing_roots, added_roots):
      existing[values["code"]] = row

  legacy_titles = {
    "vrf-vrv": ("VRF/VRV", "VRV / VRF-системы"),
    "air-conditioning": ("Кондиционирование", "Кондиционеры")
  }
  for code, (old_title, new_title) in legacy_titles.items():
    row = existing.get(code)
    if row is not None and row["title"] == old_title:
      row["title"] = new_title

  category_groups = dict(HVAC_CATEGORY_GROUPS)
  category_groups["humidification"] = HUMIDIFICATION_CATEGORIES
  # Some of the reference categories are nested several levels deep. Create
  # each level only after its parent row is available, retaining every legacy
  # row already stored in the table.
  pending_groups = dict(category_groups)
  while pending_groups:
    progressed = False
    for parent_code, children in list(pending_groups.items()):
      parent = existing.get(parent_code)
      if parent is None:
        continue
      missing_children = []
      for order, (code, title) in enumerate(children):
        child_code = parent_code + "-" + code
        if child_code not in existing:
          missing_children.append({
            "code": child_code,
            "title": title,
            "parent": parent,
            "active": True,
            "sort_order": (parent["sort_order"] or 0) + order + 1
          })
      if missing_children:
        added_children = category_table.add_rows(missing_children)
        for values, row in zip(missing_children, added_children):
          existing[values["code"]] = row
      del pending_groups[parent_code]
      progressed = True
    if not progressed:
      break

  # Reuse the established category records while placing their existing
  # equipment families under the new home/business navigation groups.
  parent_moves = {
    "humidification": "humidifiers-purifiers",
    "heating": "heat-equipment",
    "air-conditioning-multi-split": "multi-split-systems",
    "air-conditioning-cassette": "semi-industrial",
    "air-conditioning-duct": "semi-industrial",
    "air-conditioning-floor-ceiling": "semi-industrial",
    "air-conditioning-column": "semi-industrial",
    "air-conditioning-precision": "precision-systems",
    "air-conditioning-wall": "air-conditioning-split-systems",
    "vrf-vrv-wall-units": "vrf-vrv-indoor-units",
    "vrf-vrv-cassette-units": "vrf-vrv-indoor-units",
    "vrf-vrv-duct-units": "vrf-vrv-indoor-units",
    "vrf-vrv-floor-ceiling-units": "vrf-vrv-indoor-units"
  }
  for code, parent_code in parent_moves.items():
    row = existing.get(code)
    parent = existing.get(parent_code)
    if row is not None and parent is not None and row.get_id() != parent.get_id():
      current_parent = row["parent"]
      if current_parent is None or current_parent.get_id() != parent.get_id():
        row.update(parent=parent)

  # Keep the legacy name recognizable while matching the home catalogue label.
  humidification = existing.get("humidification")
  if humidification is not None and humidification["title"] == "Системы увлажнения":
    humidification["title"] = "Увлажнители воздуха"


def ensure_catalog_categories():
  _ensure_categories()


def _category_options(include_inactive=False):
  # ``parent`` points back to this table. Fetch category rows once, then resolve
  # parent codes from the same result set instead of issuing a nested linked-row
  # fetch for every category.
  rows = list(app_tables.catalog_categories.search(
    q.fetch_only(
      "code", "title", "parent", "active", "sort_order", "description",
      "image", "meta_title", "meta_description"
    ),
    order_by("sort_order")
  ))
  rows_by_id = {row.get_id(): row for row in rows}
  result = []
  for row in rows:
    if not include_inactive and not row["active"]:
      continue
    parent = row["parent"]
    parent_id = parent.get_id() if parent is not None else None
    parent_row = rows_by_id.get(parent_id) if parent_id is not None else None
    result.append({
      "id": row.get_id(),
      "code": row["code"],
      "title": row["title"],
      "sort_order": row["sort_order"] or 0,
      "parent_id": parent_id,
      "parent_code": parent_row["code"] if parent_row is not None else None,
      "description": row["description"] or "",
      "meta_title": row["meta_title"] or "",
      "meta_description": row["meta_description"] or "",
      "image_url": _category_image_url(row["code"], row["image"])
    })
  by_code = {row["code"]: row for row in result}
  for row in result:
    parts = [row["title"]]
    parent_code = row["parent_code"]
    visited = {row["code"]}
    while parent_code in by_code and parent_code not in visited:
      visited.add(parent_code)
      parent_row = by_code[parent_code]
      parts.insert(0, parent_row["title"])
      parent_code = parent_row["parent_code"]
    row["path"] = " / ".join(parts)
    row["depth"] = len(parts) - 1
    row["child_count"] = sum(
      1 for candidate in result if candidate["parent_id"] == row["id"]
    )
  return result


def _category_image_url(category_code, media=None):
  if isinstance(media, anvil.Media):
    return media.get_url()
  filename = CATALOG_CATEGORY_PHOTOS.get(category_code)
  if not filename and isinstance(category_code, str):
    # Subcategories inherit the image of their nearest known catalog family,
    # so category cards never become visually empty just because a child
    # category has no dedicated artwork yet.
    matches = [
      (root, image) for root, image in CATALOG_CATEGORY_PHOTOS.items()
      if category_code.startswith(root + "-")
    ]
    if matches:
      filename = max(matches, key=lambda pair: len(pair[0]))[1]
  return "_/theme/catalog/" + filename if filename else ""


def _safe_product_image_url(value):
  if not isinstance(value, str) or not value:
    return ""
  if value.startswith(("_/theme/", "_/media/")):
    return value
  try:
    parsed = urlsplit(value)
  except ValueError:
    return ""
  if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
    return ""
  return value


def _display_currency(value):
  currency = str(value or "").strip()
  if currency.upper() in ("RUB", "RUR"):
    return "₽"
  return currency


def _product_image_url(product):
  media_rows = app_tables.product_media.search(
    q.fetch_only("file", "url", "type", "sort_order", "is_primary"),
    order_by("sort_order"), product=product
  )[:30]
  candidates = []
  for row in media_rows:
    media_file = row["file"]
    image_url = media_file.get_url() if isinstance(media_file, anvil.Media) else ""
    image_url = image_url or _safe_product_image_url(row["url"] or "")
    if not image_url:
      continue
    media_type = (row["type"] or "").strip().casefold()
    priority = 0 if row["is_primary"] or media_type in ("primary", "main", "cover", "hero") else 1
    candidates.append((priority, row["sort_order"] or 0, image_url))
  return min(candidates)[2] if candidates else ""


def _product_gallery(product, limit=12):
  rows = list(app_tables.product_media.search(
    q.fetch_only("file", "url", "type", "alt_text", "is_primary", "sort_order"),
    order_by("sort_order"), product=product
  )[:limit])
  gallery = []
  for row in rows:
    media_file = row["file"]
    image_url = media_file.get_url() if isinstance(media_file, anvil.Media) else ""
    image_url = image_url or _safe_product_image_url(row["url"] or "")
    if not image_url:
      continue
    gallery.append({
      "url": image_url,
      "alt_text": row["alt_text"] or "Фото модели",
      "is_primary": bool(row["is_primary"])
        or (row["type"] or "").strip().casefold() in ("primary", "main", "cover", "hero"),
      "sort_order": row["sort_order"] or 0
    })
  gallery.sort(key=lambda row: (not row["is_primary"], row["sort_order"]))
  return gallery


def _text_value(data, key, label, maximum, required=False):
  value = data.get(key, "")
  if value is None:
    value = ""
  if not isinstance(value, str):
    return None, "Поле «{}» заполнено неверно.".format(label)
  value = value.strip()
  if required and not value:
    return None, "Заполните поле «{}».".format(label)
  if len(value) > maximum:
    return None, "Поле «{}» слишком длинное.".format(label)
  return value, None


def _number_value(data, key, label, maximum=None):
  raw = data.get(key)
  if raw is None or (isinstance(raw, str) and not raw.strip()):
    return None, None
  if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
    return None, "Проверьте числовое поле «{}».".format(label)
  try:
    value = float(str(raw).replace(" ", "").replace(",", "."))
  except ValueError:
    return None, "Проверьте числовое поле «{}».".format(label)
  if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
    return None, "Значение поля «{}» вне допустимого диапазона.".format(label)
  return value, None


def _public_source_url(value):
  if not isinstance(value, str) or not value:
    return ""
  try:
    parsed = urlsplit(value)
  except ValueError:
    return ""
  if (
    parsed.scheme not in ("http", "https") or not parsed.netloc
    or parsed.username or parsed.password or parsed.query or parsed.fragment
  ):
    return ""
  return value


def _parse_offer_data(prices, stock):
  price_fields = {
    "purchase_price": "Закупочная цена",
    "sale_price": "Цена продажи",
    "special_price": "Специальная цена",
    "discount": "Скидка",
    "markup": "Наценка",
    "installation_price": "Цена монтажа"
  }
  result_prices = {}
  for key, label in price_fields.items():
    value, error = _number_value(prices, key, label, 100 if key == "discount" else None)
    if error:
      return None, None, error
    result_prices[key] = value

  result_stock = {}
  for key, label in (("quantity", "Остаток"), ("minimum_stock", "Минимальный остаток")):
    value, error = _number_value(stock, key, label)
    if error:
      return None, None, error
    result_stock[key] = value
  return result_prices, result_stock, None


def _upsert_offer(table, product, values):
  row = table.get(product=product)
  data_values = [
    value for key, value in values.items()
    if key not in ("currency", "updated_at")
  ]
  if not any(value is not None for value in data_values):
    if row is not None:
      row.delete()
    return
  if row is None:
    table.add_row(product=product, **values)
  else:
    row.update(**values)


@anvil.server.callable
def get_catalog_categories():
  _ensure_categories()
  return {"ok": True, "categories": _category_options()}


@anvil.server.callable
def get_catalog_menu_tree(include_counts=True, include_series=True):
  """Return live category rows grouped into the two catalogue directions."""
  # Public navigation is read-mostly. Do not rewrite/migrate the category
  # tree on every page load; initialize it only when the table is empty.
  if next(iter(app_tables.catalog_categories.search(
    q.fetch_only("code"), q.page_size(1)
  )), None) is None:
    _ensure_categories()
  categories = _category_options()
  by_id: dict[str, dict[str, Any]] = {
    row["id"]: dict(row, children=[]) for row in categories
  }
  roots = []
  direct_product_counts = {}

  # Count each product once at its most specific linked category. Parent
  # totals are then derived from children, avoiding large in-memory ID sets.
  if include_counts:
    for product in app_tables.products.search(
      q.fetch_only("category", "subcategory"), active=True
    ):
      category = product["subcategory"] or product["category"]
      if category is not None:
        category_id = category.get_id()
        direct_product_counts[category_id] = direct_product_counts.get(category_id, 0) + 1

  for row in categories:
    node = by_id[row["id"]]
    node["product_count"] = direct_product_counts.get(row["id"], 0)
    node["menu_label"] = row["title"]
    node["menu_mode"] = True
    node["has_children"] = False
    node["expand_icon"] = ""
    parent = by_id.get(row["parent_id"])
    if parent is None:
      roots.append(node)
    else:
      parent["children"].append(node)

  def order_tree(nodes, visited=None):
    visited = visited or set()
    safe_nodes = []
    for node in sorted(nodes, key=lambda item: (item["sort_order"] or 0, item["title"].casefold())):
      if node["id"] in visited:
        continue
      path = set(visited)
      path.add(node["id"])
      children = order_tree(node["children"], path)
      node["children"] = children
      if include_counts:
        node["product_count"] += sum(child["product_count"] for child in children)
      node["has_children"] = bool(children)
      node["child_count"] = len(children)
      node["expand_icon"] = "›" if children else ""
      safe_nodes.append(node)
    return safe_nodes

  roots = order_tree(roots)


  for category in categories:
    node = by_id[category["id"]]
    category["product_count"] = node["product_count"] if include_counts else 0
    category["child_count"] = node["child_count"]

  home = []
  business = []
  for root in roots:
    (home if root["code"] in HOME_ROOT_CODES else business).append(root)

  navigation_settings = AdminStudio.get_public_navigation_settings()
  return {
    "ok": True,
    "categories": categories,
    "series": (
      [_series_payload(row) for row in _series_rows_for_category(active_only=True)]
      if include_series else []
    ),
    "navigation_settings": navigation_settings,
    "site_menu": SiteMenuService.get_public_site_menu_data(),
    "tree": [
      {
        "id": "direction-home", "code": "direction-home", "title": "Для дома",
        "menu_label": "Для дома", "children": home, "has_children": True,
        "expand_icon": "›", "menu_mode": True, "product_count": sum(
          row["product_count"] for row in home
        )
      },
      {
        "id": "direction-business", "code": "direction-business", "title": "Для бизнеса",
        "menu_label": "Для бизнеса", "children": business, "has_children": True,
        "expand_icon": "›", "menu_mode": True, "product_count": sum(
          row["product_count"] for row in business
        )
      }
    ]
  }


def _series_image_url(series):
  image = series["image"]
  return image.get_url() if isinstance(image, anvil.Media) else ""


def _series_rows_for_category(category=None, active_only=True):
  rows = list(app_tables.catalog_series.search(
    q.fetch_only(
      "code", "title", "category", "description", "status", "is_new",
      "power_range", "image", "sort_order", "active"
    ),
    order_by("sort_order")
  ))
  allowed_category_ids = None
  if category is not None:
    all_categories = list(app_tables.catalog_categories.search(
      q.fetch_only("parent"), active=True
    ))
    descendants = {category.get_id()}
    changed = True
    while changed:
      changed = False
      for item in all_categories:
        parent = item["parent"]
        if parent is not None and parent.get_id() in descendants:
          item_id = item.get_id()
          if item_id not in descendants:
            descendants.add(item_id)
            changed = True
    allowed_category_ids = descendants
  result = []
  for row in rows:
    if active_only and not row["active"]:
      continue
    linked_category = row["category"]
    if allowed_category_ids is not None and (
      linked_category is None or linked_category.get_id() not in allowed_category_ids
    ):
      continue
    result.append(row)
  return result


def _series_payload(row):
  category = row["category"]
  return {
    "id": row.get_id(), "code": row["code"], "title": row["title"],
    "category_id": category.get_id() if category is not None else None,
    "category_code": category["code"] if category is not None else "",
    "category_title": category["title"] if category is not None else "",
    "description": row["description"] or "", "status": row["status"] or "active",
    "is_new": bool(row["is_new"]), "power_range": row["power_range"] or "",
    "image_url": _series_image_url(row),
    "sort_order": row["sort_order"] or 0, "active": bool(row["active"])
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def sync_catalog_series_from_specs():
  """Link existing model rows to series named in their saved specifications."""
  user = Core.require_permission("catalog.manage")
  products = list(app_tables.products.search(
    q.fetch_only("series", "category", "subcategory", "active", "model")
  ))
  product_by_id = {row.get_id(): row for row in products}
  series_specs = list(app_tables.product_specs.search(
    q.fetch_only("product", "key", "value", "unit", "visible"),
    q.any_of(
      q.all_of(key_key="серия"),
      q.all_of(key_key="серия оборудования"),
      q.all_of(key_key="series")
    )
  ))
  metadata_specs = list(app_tables.product_specs.search(
    q.fetch_only("product", "key", "value", "unit"),
    q.any_of(
      q.all_of(key_key="описание серии"),
      q.all_of(key_key="диапазон мощности"),
      q.all_of(key_key="новинка")
    )
  ))
  metadata_by_product = {}
  for row in metadata_specs:
    product = row["product"]
    if product is not None:
      metadata_by_product.setdefault(product.get_id(), {})[
        (row["key"] or "").casefold()
      ] = row

  existing_series = list(app_tables.catalog_series.search(
    q.fetch_only("title", "category", "description", "power_range", "is_new", "active", "status")
  ))
  series_by_key = {
    (row["category"].get_id() if row["category"] is not None else None,
     (row["title"] or "").casefold()): row
    for row in existing_series
  }
  created = linked = 0
  now = datetime.now(timezone.utc)
  for spec in series_specs:
    product = spec["product"]
    if product is None or product.get_id() not in product_by_id or product["series"] is not None:
      continue
    title = (spec["value"] or "").strip()
    if not title or len(title) > 120:
      continue
    category = product["subcategory"] or product["category"]
    if category is None:
      continue
    category_id = category.get_id()
    key = (category_id, title.casefold())
    series = series_by_key.get(key)
    metadata = metadata_by_product.get(product.get_id(), {})
    description_spec = metadata.get("описание серии")
    power_spec = metadata.get("диапазон мощности")
    new_spec = metadata.get("новинка")
    is_new = bool(new_spec and (new_spec["value"] or "").strip().casefold() in {
      "да", "yes", "true", "1", "новинка"
    })
    if series is None:
      series = app_tables.catalog_series.add_row(
        code="series-" + uuid.uuid4().hex,
        title=title,
        category=category,
        description=(description_spec["value"] or "")[:3000] if description_spec else "",
        status="active",
        is_new=is_new,
        power_range=(power_spec["value"] or "")[:120] if power_spec else "",
        image=None,
        sort_order=created * 10,
        active=True,
        created_at=now,
        updated_at=now
      )
      series_by_key[key] = series
      created += 1
    product["series"] = series
    linked += 1

  if linked:
    Core.log_audit(
      actor=user, action="catalog.series_linked_from_specs",
      entity_type="catalog", entity_id="",
      details={"series_created": created, "products_linked": linked},
      created_at=now
    )
  return {
    "ok": True, "series_created": created, "products_linked": linked,
    "message": "Создано серий: {} · связано моделей: {}.".format(created, linked)
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_catalog_series_admin():
  Core.require_permission("catalog.manage")
  _ensure_categories()
  series = []
  for row in _series_rows_for_category(active_only=False):
    item = _series_payload(row)
    item["product_count"] = len(app_tables.products.search(series=row))
    item["document_count"] = len(app_tables.catalog_documents.search(series=row))
    item["status_label"] = "Активна" if row["active"] else "Скрыта"
    series.append(item)
  return {"ok": True, "series": series, "categories": _category_options(include_inactive=True)}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_catalog_series(series_id, payload, image=None):
  user = Core.require_permission("catalog.manage")
  if not isinstance(payload, dict):
    return {"ok": False, "message": "Проверьте данные серии."}
  title, error = _text_value(payload, "title", "Название серии", 120, required=True)
  if error:
    return {"ok": False, "message": error}
  description, error = _text_value(payload, "description", "Описание серии", 3000)
  if error:
    return {"ok": False, "message": error}
  power_range, error = _text_value(payload, "power_range", "Диапазон мощности", 120)
  if error:
    return {"ok": False, "message": error}
  status, error = _text_value(payload, "status", "Статус серии", 24, required=True)
  if error:
    return {"ok": False, "message": error}
  if status not in {"active", "draft", "archived"}:
    return {"ok": False, "message": "Выберите статус серии из списка."}
  category_id = payload.get("category_id")
  if not isinstance(category_id, str) or not category_id:
    return {"ok": False, "message": "Выберите категорию серии."}
  category = app_tables.catalog_categories.get_by_id(category_id)
  if category is None:
    return {"ok": False, "message": "Категория серии не найдена."}
  is_new = payload.get("is_new", False)
  active = payload.get("active", True)
  if not isinstance(is_new, bool) or not isinstance(active, bool):
    return {"ok": False, "message": "Проверьте состояние серии."}
  try:
    sort_order = int(payload.get("sort_order", 0))
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Порядок серии должен быть целым числом."}
  if isinstance(payload.get("sort_order"), bool) or sort_order < 0 or sort_order > 100000:
    return {"ok": False, "message": "Порядок серии должен быть от 0 до 100000."}
  if image is not None and not isinstance(image, anvil.Media):
    return {"ok": False, "message": "Файл изображения серии некорректен."}
  if image is not None and (
    image.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}
    or image.length <= 0 or image.length > 8 * 1024 * 1024
  ):
    return {"ok": False, "message": "Изображение серии должно быть JPEG, PNG, WebP или GIF до 8 МБ."}
  row = app_tables.catalog_series.get_by_id(series_id) if series_id else None
  if series_id and row is None:
    return {"ok": False, "message": "Серия не найдена."}
  duplicate = next((
    candidate for candidate in app_tables.catalog_series.search(category=category)
    if (candidate["title"] or "").casefold() == (title or "").casefold()
    and (row is None or candidate.get_id() != row.get_id())
  ), None)
  if duplicate is not None:
    return {"ok": False, "message": "В этой категории серия с таким названием уже существует."}
  values = {
    "title": title, "category": category, "description": description or "",
    "status": status, "is_new": is_new, "power_range": power_range or "",
    "sort_order": sort_order, "active": active,
    "updated_at": datetime.now(timezone.utc)
  }
  if image is not None:
    values["image"] = image
  if row is None:
    code = "series-" + uuid.uuid4().hex
    row = app_tables.catalog_series.add_row(
      code=code, created_at=datetime.now(timezone.utc), **values
    )
    action = "catalog.series_created"
  else:
    row.update(**values)
    action = "catalog.series_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="catalog_series", entity_id=row.get_id(),
    details={"code": row["code"], "category": category["code"], "active": active},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "series_id": row.get_id(), "message": "Серия сохранена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_catalog_series(series_id):
  user = Core.require_permission("catalog.manage")
  if not isinstance(series_id, str) or not series_id:
    return {"ok": False, "message": "Выберите серию."}
  row = app_tables.catalog_series.get_by_id(series_id)
  if row is None:
    return {"ok": False, "message": "Серия не найдена."}
  if next(iter(app_tables.products.search(series=row)), None) is not None:
    return {"ok": False, "message": "Сначала перенесите товары из этой серии."}
  if next(iter(app_tables.catalog_documents.search(series=row)), None) is not None:
    return {"ok": False, "message": "Сначала удалите или перенесите документы серии."}
  code = row["code"]
  row.delete()
  Core.log_audit(
    actor=user, action="catalog.series_deleted", entity_type="catalog_series",
    entity_id=series_id, details={"code": code},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Серия удалена."}


def _catalog_document_payload(row):
  media = row["file"]
  url = media.get_url() if isinstance(media, anvil.Media) else _public_source_url(row["url"] or "")
  return {
    "id": row.get_id(), "title": row["title"] or "Документ",
    "kind": row["kind"] or "other", "url": url,
    "file_name": media.name if isinstance(media, anvil.Media) else "",
    "content_type": media.content_type if isinstance(media, anvil.Media) else ""
  }


def _catalog_document_rows(product=None, series=None):
  filters = {"product": product} if product is not None else {"series": series}
  return [
    _catalog_document_payload(row)
    for row in app_tables.catalog_documents.search(
      q.fetch_only("title", "kind", "file", "url", "sort_order"),
      order_by("sort_order"), **filters
    )[:50]
  ]


@anvil.server.callable
def get_catalog_documents(owner_type, owner_id):
  if owner_type == "product":
    owner = app_tables.products.get_by_id(owner_id) if isinstance(owner_id, str) else None
    if owner is None or (not owner["active"] and not Core.has_permission(_current_user(), "catalog.manage")):
      return {"ok": False, "message": "Товар не найден."}
    return {"ok": True, "documents": _catalog_document_rows(product=owner)}
  if owner_type == "series":
    owner = app_tables.catalog_series.get_by_id(owner_id) if isinstance(owner_id, str) else None
    if owner is None or (not owner["active"] and not Core.has_permission(_current_user(), "catalog.manage")):
      return {"ok": False, "message": "Серия не найдена."}
    return {"ok": True, "documents": _catalog_document_rows(series=owner)}
  return {"ok": False, "message": "Неизвестный тип объекта."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_catalog_document(owner_type, owner_id, title, kind, file_media=None,
                          url="", sort_order=0):
  user = Core.require_permission("catalog.manage")
  title, error = _text_value({"value": title}, "value", "Название документа", 160, required=True)
  if error:
    return {"ok": False, "message": error}
  kind, error = _text_value({"value": kind}, "value", "Тип документа", 32, required=True)
  if error:
    return {"ok": False, "message": error}
  if kind not in {"instruction", "datasheet", "certificate", "other"}:
    return {"ok": False, "message": "Выберите доступный тип документа."}
  url, error = _text_value({"value": url}, "value", "Ссылка на документ", 1000)
  if error:
    return {"ok": False, "message": error}
  if file_media is not None and not isinstance(file_media, anvil.Media):
    return {"ok": False, "message": "Выбранный файл документа некорректен."}
  if file_media is not None and (
    file_media.length <= 0 or file_media.length > 25 * 1024 * 1024
    or file_media.content_type not in {
      "application/pdf", "application/octet-stream", "application/zip",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
  ):
    return {"ok": False, "message": "Поддерживаются документы до 25 МБ в PDF, DOC/DOCX или ZIP."}
  if file_media is None and not _public_source_url(url or ""):
    return {"ok": False, "message": "Добавьте файл или безопасную HTTP/HTTPS-ссылку на документ."}
  try:
    sort_order = int(sort_order)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Порядок документа должен быть целым числом."}
  if sort_order < 0 or sort_order > 100000:
    return {"ok": False, "message": "Порядок документа должен быть от 0 до 100000."}
  product = series = None
  if owner_type == "product" and isinstance(owner_id, str):
    product = app_tables.products.get_by_id(owner_id)
  elif owner_type == "series" and isinstance(owner_id, str):
    series = app_tables.catalog_series.get_by_id(owner_id)
  if product is None and series is None:
    return {"ok": False, "message": "Объект каталога не найден."}
  row = cast(Any, app_tables.catalog_documents).add_row(
    title=title, kind=kind, product=product, series=series,
    file=file_media, url=url or "", sort_order=sort_order,
    created_at=datetime.now(timezone.utc)
  )
  Core.log_audit(
    actor=user, action="catalog.document_added", entity_type=owner_type,
    entity_id=owner_id, details={"document": row.get_id(), "title": title},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "document": _catalog_document_payload(row), "message": "Документ добавлен."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_catalog_document(document_id):
  user = Core.require_permission("catalog.manage")
  if not isinstance(document_id, str) or not document_id:
    return {"ok": False, "message": "Выберите документ."}
  row = app_tables.catalog_documents.get_by_id(document_id)
  if row is None:
    return {"ok": False, "message": "Документ уже удалён."}
  entity_type = "product" if row["product"] is not None else "series"
  owner = row["product"] or row["series"]
  owner_id = owner.get_id() if owner is not None else ""
  title = row["title"] or ""
  row.delete()
  Core.log_audit(
    actor=user, action="catalog.document_deleted", entity_type=entity_type,
    entity_id=owner_id, details={"title": title},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "owner_type": entity_type, "owner_id": owner_id, "message": "Документ удалён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def add_catalog_category(title, parent_id=None):
  user = Core.require_permission("catalog.manage")
  if not isinstance(title, str):
    return {"ok": False, "message": "Введите название категории."}
  title = title.strip()
  if not title or len(title) > 80:
    return {"ok": False, "message": "Название категории должно содержать от 1 до 80 символов."}

  parent = None
  if parent_id:
    if not isinstance(parent_id, str):
      return {"ok": False, "message": "Некорректная родительская категория."}
    parent = app_tables.catalog_categories.get_by_id(parent_id)
    if parent is None:
      return {"ok": False, "message": "Родительская категория не найдена."}

  existing = next((
    row for row in app_tables.catalog_categories.search()
    if row["parent"] == parent and row["title"].casefold() == title.casefold()
  ), None)
  if existing is not None:
    return {"ok": False, "message": "Такая категория уже существует."}
  category_table = cast(Any, app_tables.catalog_categories)
  category_table.add_row(
    code="custom-" + uuid.uuid4().hex,
    title=title,
    parent=parent,
    active=True,
    sort_order=1000
  )
  return {"ok": True, "message": "Категория добавлена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_catalog_admin_data():
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  _ensure_categories()
  category_rows = list(app_tables.catalog_categories.search(
    q.fetch_only(
      "code", "title", "parent", "active", "sort_order", "description",
      "image", "meta_title", "meta_description"
    ),
    order_by("sort_order")
  ))
  rows_by_id = {row.get_id(): row for row in category_rows}
  product_ids_by_category = {}
  for product in app_tables.products.search(q.fetch_only("category", "subcategory")):
    for field in ("category", "subcategory"):
      linked = product[field]
      if linked is not None:
        product_ids_by_category.setdefault(linked.get_id(), set()).add(product.get_id())
  categories = []
  for row in category_rows:
    parent = row["parent"]
    parent_id = parent.get_id() if parent is not None else None
    parent_row = rows_by_id.get(parent_id) if parent_id else None
    category = {
      "id": row.get_id(), "code": row["code"], "title": row["title"],
      "parent_id": parent_id,
      "parent_code": parent_row["code"] if parent_row is not None else None,
      "active": bool(row["active"]), "sort_order": row["sort_order"] or 0,
      "description": row["description"] or "",
      "meta_title": row["meta_title"] or "",
      "meta_description": row["meta_description"] or "",
      "image_url": _category_image_url(row["code"], row["image"]),
      "product_count": len(product_ids_by_category.get(row.get_id(), set())),
      "child_count": 0,
      "depth": 0,
      "status_title": "Активна" if row["active"] else "Скрыта"
    }
    categories.append(category)
  child_counts = {}
  for category in categories:
    if category["parent_id"]:
      child_counts[category["parent_id"]] = child_counts.get(category["parent_id"], 0) + 1
  for category in categories:
    category["child_count"] = child_counts.get(category["id"], 0)
    parent_row = rows_by_id.get(category["parent_id"]) if category["parent_id"] else None
    path_parts = [category["title"]]
    visited = {category["id"]}
    parent_id = category["parent_id"]
    while parent_id in rows_by_id and parent_id not in visited:
      visited.add(parent_id)
      parent_row = rows_by_id[parent_id]
      path_parts.insert(0, parent_row["title"])
      parent = parent_row["parent"]
      parent_id = parent.get_id() if parent is not None else None
      category["depth"] += 1
    parent_title = " / ".join(path_parts[:-1]) if len(path_parts) > 1 else "Основной раздел"
    category["status_title"] = "{} · {} товаров · {} подкатегорий".format(
      category["status_title"], category["product_count"], category["child_count"]
    )
    category["path"] = "{} / {}".format(parent_title, category["title"])

  brands = []
  for brand in app_tables.brands.search(
    q.fetch_only("name", "name_key"), order_by("name")
  ):
    brands.append({
      "id": brand.get_id(), "name": brand["name"],
      "product_count": len(app_tables.products.search(brand=brand)),
      "product_label": "Товаров: {}".format(len(app_tables.products.search(brand=brand)))
    })
  return {"ok": True, "categories": categories, "brands": brands}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_catalog_category(category_id, title, parent_id, active, sort_order,
                          description="", meta_title="", meta_description="",
                          image=None, remove_image=False):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(title, str):
    return {"ok": False, "message": "Введите название категории."}
  title = title.strip()
  if not title or len(title) > 80:
    return {"ok": False, "message": "Название категории должно содержать от 1 до 80 символов."}
  if not isinstance(active, bool):
    return {"ok": False, "message": "Проверьте состояние категории."}
  description, error = _text_value(
    {"value": description}, "value", "Описание категории", 2000
  )
  if error:
    return {"ok": False, "message": error}
  meta_title, error = _text_value(
    {"value": meta_title}, "value", "SEO-заголовок", 160
  )
  if error:
    return {"ok": False, "message": error}
  meta_description, error = _text_value(
    {"value": meta_description}, "value", "SEO-описание", 320
  )
  if error:
    return {"ok": False, "message": error}
  if image is not None and not isinstance(image, anvil.Media):
    return {"ok": False, "message": "Выбранный файл изображения некорректен."}
  if not isinstance(remove_image, bool):
    return {"ok": False, "message": "Проверьте настройку изображения категории."}
  if image is not None and (
    image.content_type not in {"image/jpeg", "image/png", "image/webp"}
    or image.length <= 0 or image.length > 5 * 1024 * 1024
  ):
    return {"ok": False, "message": "Для категории используйте JPEG, PNG или WebP до 5 МБ."}
  try:
    order = int(sort_order)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Порядок должен быть целым числом."}
  if isinstance(sort_order, bool) or order < 0 or order > 100000:
    return {"ok": False, "message": "Порядок должен быть от 0 до 100000."}

  if category_id is not None and not isinstance(category_id, str):
    return {"ok": False, "message": "Некорректная категория."}
  row = app_tables.catalog_categories.get_by_id(category_id) if category_id else None
  if category_id and row is None:
    return {"ok": False, "message": "Категория не найдена."}
  parent = None
  if parent_id:
    if not isinstance(parent_id, str):
      return {"ok": False, "message": "Проверьте родительскую категорию."}
    parent = app_tables.catalog_categories.get_by_id(parent_id)
    if parent is None:
      return {"ok": False, "message": "Родительская категория не найдена."}
    if row is not None and parent.get_id() == row.get_id():
      return {"ok": False, "message": "Категория не может быть родителем самой себе."}
    ancestor = parent
    visited = set()
    while ancestor is not None:
      ancestor_id = ancestor.get_id()
      if row is not None and ancestor_id == row.get_id():
        return {"ok": False, "message": "Нельзя переместить категорию внутрь её собственной ветки."}
      if ancestor_id in visited:
        return {"ok": False, "message": "В дереве категорий обнаружен цикл."}
      visited.add(ancestor_id)
      ancestor = ancestor["parent"]
  duplicate = next((
    item for item in app_tables.catalog_categories.search()
    if item["parent"] == parent
    and item["title"].casefold() == title.casefold()
    and (row is None or item.get_id() != row.get_id())
  ), None)
  if duplicate is not None:
    return {"ok": False, "message": "В этом разделе уже есть категория с таким названием."}

  now = datetime.now(timezone.utc)
  category_values = {
    "title": title, "parent": parent, "active": active,
    "sort_order": order, "description": description or "",
    "meta_title": meta_title or "", "meta_description": meta_description or ""
  }
  if image is not None:
    category_values["image"] = image
  elif remove_image:
    category_values["image"] = None
  if row is None:
    row = cast(Any, app_tables.catalog_categories).add_row(
      code="custom-" + uuid.uuid4().hex, **category_values
    )
    action = "catalog.category_created"
  else:
    cast(Any, row).update(**category_values)
    action = "catalog.category_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="catalog_category",
    entity_id=row.get_id(),
    details={"code": row["code"], "active": active,
             "parent": parent["code"] if parent else None}, created_at=now
  )
  return {"ok": True, "category_id": row.get_id(), "message": "Категория сохранена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_catalog_category(category_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(category_id, str) or not category_id:
    return {"ok": False, "message": "Выберите категорию."}
  row = app_tables.catalog_categories.get_by_id(category_id)
  if row is None:
    return {"ok": False, "message": "Категория не найдена."}
  if row["code"] in {code for code, _ in ROOT_CATEGORIES}:
    return {"ok": False, "message": "Основной раздел нельзя удалить. Скрывайте его переключателем в редакторе."}
  category_fields = [
    field for field in _custom_field_definitions()
    if field.get("category_id") == category_id
  ]
  if any(field.get("enabled", True) for field in category_fields):
    return {"ok": False, "message": "Сначала отключите дополнительные поля категории."}
  field_markers = tuple(
    "custom-field|{}|".format(field["id"])
    for field in category_fields if field.get("id")
  )
  if field_markers and any(
    (spec["source"] or "").startswith(field_markers)
    for spec in app_tables.product_specs.search()
  ):
    return {"ok": False, "message": "В товарах сохранены значения дополнительных полей. Переместите товары и проверьте их значения перед удалением."}
  if next(iter(app_tables.catalog_categories.search(parent=row)), None) is not None:
    return {"ok": False, "message": "Сначала удалите или переместите подкатегории."}
  if (
    next(iter(app_tables.products.search(category=row)), None) is not None
    or next(iter(app_tables.products.search(subcategory=row)), None) is not None
    or next(iter(app_tables.catalog_series.search(category=row)), None) is not None
  ):
    return {"ok": False, "message": "Категория используется товарами или сериями. Отключите её вместо удаления."}
  code = row["code"]
  if category_fields:
    all_fields = _custom_field_definitions()
    remaining_fields = [
      field for field in all_fields if field.get("category_id") != category_id
    ]
    settings = app_tables.system_settings.get(key=CUSTOM_FIELDS_SETTING_KEY)
    if settings is not None:
      settings.update(
        value=remaining_fields, updated_at=datetime.now(timezone.utc),
        updated_by=user
      )
  row.delete()
  Core.log_audit(
    actor=user, action="catalog.category_deleted", entity_type="catalog_category",
    entity_id=category_id, details={"code": code},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Категория удалена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_catalog_brand(brand_id, name):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(name, str):
    return {"ok": False, "message": "Введите название бренда."}
  name = name.strip()
  if not name or len(name) > 80:
    return {"ok": False, "message": "Название бренда должно содержать от 1 до 80 символов."}
  if brand_id is not None and not isinstance(brand_id, str):
    return {"ok": False, "message": "Некорректный бренд."}
  brand = app_tables.brands.get_by_id(brand_id) if brand_id else None
  if brand_id and brand is None:
    return {"ok": False, "message": "Бренд не найден."}
  name_key = name.casefold()
  duplicate = app_tables.brands.get(name_key=name_key)
  if duplicate is not None and (brand is None or duplicate.get_id() != brand.get_id()):
    return {"ok": False, "message": "Такой бренд уже есть."}

  products = list(app_tables.products.search(brand=brand)) if brand is not None else []
  identity_keys = {}
  for product in products:
    key = product_identity_key(name, product["model"] or "", product["sku"] or "")
    if key in identity_keys:
      return {"ok": False, "message": "Переименование создаст повторяющиеся товары. Исправьте их модели или артикулы."}
    identity_keys[key] = product.get_id()
    existing = app_tables.products.get(identity_key=key)
    if existing is not None and existing.get_id() not in {item.get_id() for item in products}:
      return {"ok": False, "message": "Переименование создаст товар с уже используемой моделью."}

  now = datetime.now(timezone.utc)
  if brand is None:
    brand = app_tables.brands.add_row(name=name, name_key=name_key)
    action = "catalog.brand_created"
  else:
    brand.update(name=name, name_key=name_key)
    for product in products:
      product["identity_key"] = product_identity_key(
        name, product["model"] or "", product["sku"] or ""
      )
    action = "catalog.brand_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="catalog_brand",
    entity_id=brand.get_id(), details={"name": name}, created_at=now
  )
  return {"ok": True, "brand_id": brand.get_id(), "message": "Бренд сохранён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_catalog_brand(brand_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(brand_id, str) or not brand_id:
    return {"ok": False, "message": "Выберите бренд."}
  brand = app_tables.brands.get_by_id(brand_id)
  if brand is None:
    return {"ok": False, "message": "Бренд не найден."}
  if next(iter(app_tables.products.search(brand=brand)), None) is not None:
    return {"ok": False, "message": "Бренд связан с товарами. Сначала измените карточки товаров."}
  name = brand["name"]
  brand.delete()
  Core.log_audit(
    actor=user, action="catalog.brand_deleted", entity_type="catalog_brand",
    entity_id=brand_id, details={"name": name},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Бренд удалён."}


def _catalog_category_scope(category_id):
  rows = list(app_tables.catalog_categories.search(
    q.fetch_only("code", "parent", "active"), active=True
  ))
  rows_by_id = {row.get_id(): row for row in rows}
  rows_by_code = {row["code"]: row for row in rows}
  if category_id in ("direction-home", "direction-business"):
    home = category_id == "direction-home"
    selected = [row for row in rows if row["parent"] is None and
                ((row["code"] in HOME_ROOT_CODES) == home)]
  else:
    category = rows_by_id.get(category_id) or rows_by_code.get(category_id)
    if category is None:
      return None
    selected = [category]
  selected_ids = {row.get_id() for row in selected}
  changed = True
  while changed:
    changed = False
    for row in rows:
      parent = row["parent"]
      if parent is not None and parent.get_id() in selected_ids:
        row_id = row.get_id()
        if row_id not in selected_ids:
          selected_ids.add(row_id)
          selected.append(row)
          changed = True
  return selected


def _category_scope_expression(rows):
  clauses = []
  for category in rows:
    clauses.append(q.all_of(category=category))
    clauses.append(q.all_of(subcategory=category))
  return q.any_of(*clauses) if clauses else None


def _category_is_within(category, ancestor):
  current = category
  visited = set()
  while current is not None:
    current_id = current.get_id()
    if current_id == ancestor.get_id():
      return True
    if current_id in visited:
      return False
    visited.add(current_id)
    current = current["parent"]
  return False


def _custom_field_definitions():
  row = app_tables.system_settings.get(key=CUSTOM_FIELDS_SETTING_KEY)
  value = row["value"] if row is not None else []
  return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _custom_field_scope_ids(category, subcategory=None):
  selected = []
  for target in (category, subcategory):
    if target is None:
      continue
    current = target
    visited = set()
    while current is not None and current.get_id() not in visited:
      current_id = current.get_id()
      visited.add(current_id)
      selected.append(str(current_id))
      current = current["parent"]
  return selected


def _custom_fields_for_category_ids(category_ids, include_disabled=False):
  category_set = set(str(item) for item in category_ids if item)
  fields = [
    dict(item) for item in _custom_field_definitions()
    if item.get("category_id") in category_set
    and (include_disabled or item.get("enabled", True))
  ]
  fields.sort(key=lambda item: (
    item.get("sort_order", 0), item.get("title", "").casefold()
  ))
  return fields


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_catalog_custom_field_definitions(category_id):
  Core.require_permission("catalog.manage")
  if not isinstance(category_id, str) or not category_id:
    return {"ok": False, "message": "Выберите категорию.", "fields": []}
  category = app_tables.catalog_categories.get_by_id(category_id)
  if category is None:
    return {"ok": False, "message": "Категория не найдена.", "fields": []}
  fields = _custom_fields_for_category_ids([category_id], include_disabled=True)
  return {
    "ok": True,
    "types": [
      ("Короткий текст", "text"), ("Число", "number"),
      ("Цена", "price"), ("Дата", "date"),
      ("Список", "select"), ("Несколько значений", "multiselect"),
      ("Переключатель", "toggle"), ("Изображение", "image"),
      ("Файл или ссылка на документ", "file"),
      ("Ссылка", "url"), ("Длинный текст", "rich_text")
    ],
    "fields": fields
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_catalog_custom_field(category_id, field_id, code, title, kind,
                              choices, unit, required, show_public,
                              enabled, sort_order):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для настройки полей каталога.")
  if not isinstance(category_id, str) or not category_id:
    return {"ok": False, "message": "Выберите категорию."}
  category = app_tables.catalog_categories.get_by_id(category_id)
  if category is None:
    return {"ok": False, "message": "Категория не найдена."}
  if field_id is not None and (not isinstance(field_id, str) or not field_id):
    return {"ok": False, "message": "Некорректное поле каталога."}
  if not isinstance(code, str):
    return {"ok": False, "message": "Введите код поля."}
  code = code.strip().casefold()
  if (
    not 2 <= len(code) <= 36 or not code.isascii() or not code[0].isalpha()
    or any(not (character.isalnum() or character == "_") for character in code)
  ):
    return {"ok": False, "message": "Код поля: латинская буква, затем латинские буквы, цифры или _."}
  title, error = _text_value({"value": title}, "value", "Название поля", 80, required=True)
  if error:
    return {"ok": False, "message": error}
  if kind not in CUSTOM_FIELD_TYPES:
    return {"ok": False, "message": "Выберите доступный тип поля."}
  unit, error = _text_value({"value": unit}, "value", "Единица измерения", 24)
  if error:
    return {"ok": False, "message": error}
  if not isinstance(choices, list) or len(choices) > 30 or any(
    not isinstance(item, str) or not item.strip() or len(item.strip()) > 80
    for item in choices
  ):
    return {"ok": False, "message": "Проверьте варианты списка: до 30 значений по 80 символов."}
  choices = list(dict.fromkeys(item.strip() for item in choices))
  if kind in ("select", "multiselect") and not choices:
    return {"ok": False, "message": "Для списка добавьте хотя бы один вариант."}
  if any(not isinstance(flag, bool) for flag in (required, show_public, enabled)):
    return {"ok": False, "message": "Проверьте обязательность, публикацию и состояние поля."}
  try:
    sort_order = int(sort_order)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Порядок поля должен быть целым числом."}
  if sort_order < 0 or sort_order > 100000:
    return {"ok": False, "message": "Порядок поля должен быть от 0 до 100000."}

  definitions = _custom_field_definitions()
  field = next((item for item in definitions if item.get("id") == field_id), None)
  if field_id and field is None:
    return {"ok": False, "message": "Поле больше не существует."}
  if field is not None and field.get("category_id") != category_id:
    return {"ok": False, "message": "Поле относится к другой категории."}
  if field is not None and field.get("kind") != kind:
    marker = "custom-field|{}|".format(field_id)
    has_saved_values = any(
      (row["source"] or "").startswith(marker)
      for row in app_tables.product_specs.search()
    )
    if has_saved_values:
      return {
        "ok": False,
        "message": "Нельзя менять тип поля после ввода значений. Создайте новое поле с нужным типом."
      }
  related_scope_ids = {
    str(candidate.get_id())
    for candidate in app_tables.catalog_categories.search()
    if _category_is_within(candidate, category)
    or _category_is_within(category, candidate)
  }
  duplicate = next((
    item for item in definitions
    if item.get("category_id") in related_scope_ids
    and item.get("code", "").casefold() == code
    and item.get("id") != field_id
  ), None)
  if duplicate is not None:
    return {"ok": False, "message": "Такой код уже задан в этой категории или в её родительском разделе."}
  now = datetime.now(timezone.utc)
  if field is None:
    field = cast(dict[str, Any], {
      "id": uuid.uuid4().hex, "category_id": category_id, "code": code
    })
    definitions.append(field)
    action = "catalog.custom_field_created"
  else:
    field = cast(dict[str, Any], field)
    action = "catalog.custom_field_updated"
  field["code"] = code
  field["title"] = title or ""
  field["kind"] = kind
  field["choices"] = choices
  field["unit"] = unit or ""
  field["required"] = required
  field["show_public"] = show_public
  field["enabled"] = enabled
  field["sort_order"] = sort_order
  settings = app_tables.system_settings.get(key=CUSTOM_FIELDS_SETTING_KEY)
  if settings is None:
    app_tables.system_settings.add_row(
      key=CUSTOM_FIELDS_SETTING_KEY, value=definitions,
      updated_at=now, updated_by=user
    )
  else:
    settings.update(value=definitions, updated_at=now, updated_by=user)
  value_marker = "custom-field|{}|".format(field["id"])
  for product_spec in app_tables.product_specs.search():
    if (product_spec["source"] or "").startswith(value_marker):
      product_spec.update(
        key=field["title"], key_key="__custom_field__:" + field["id"],
        unit=field.get("unit", ""),
        visible=bool(field.get("enabled") and field.get("show_public")),
        sort_order=sort_order, updated_at=now
      )
  Core.log_audit(
    actor=user, action=action, entity_type="catalog_custom_field",
    entity_id=field["id"], details={"category": category["code"], "code": code},
    created_at=now
  )
  return {"ok": True, "field_id": field["id"], "message": "Поле каталога сохранено."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def disable_catalog_custom_field(category_id, field_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для настройки полей каталога.")
  if not isinstance(category_id, str) or not isinstance(field_id, str):
    return {"ok": False, "message": "Выберите поле каталога."}
  definitions = _custom_field_definitions()
  field = next((item for item in definitions if item.get("id") == field_id), None)
  if field is None or field.get("category_id") != category_id:
    return {"ok": False, "message": "Поле не найдено в этой категории."}
  field["enabled"] = False
  now = datetime.now(timezone.utc)
  settings = app_tables.system_settings.get(key=CUSTOM_FIELDS_SETTING_KEY)
  if settings is None:
    raise RuntimeError("Catalog custom field settings disappeared during the update.")
  settings.update(value=definitions, updated_at=now, updated_by=user)
  value_marker = "custom-field|{}|".format(field_id)
  for product_spec in app_tables.product_specs.search():
    if (product_spec["source"] or "").startswith(value_marker):
      product_spec.update(visible=False, updated_at=now)
  Core.log_audit(
    actor=user, action="catalog.custom_field_disabled",
    entity_type="catalog_custom_field", entity_id=field_id,
    details={"code": field.get("code", "")}, created_at=now
  )
  return {"ok": True, "message": "Поле отключено. Сохранённые значения остаются в товарах."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_product_custom_fields(product_id=None, category_id=None, subcategory_id=None):
  Core.require_permission("catalog.manage")
  product = None
  if product_id is not None:
    if not isinstance(product_id, str) or not product_id:
      return {"ok": False, "message": "Некорректный товар.", "fields": []}
    product = app_tables.products.get_by_id(product_id)
    if product is None:
      return {"ok": False, "message": "Товар не найден.", "fields": []}
    category = (
      None if category_id == "" else
      app_tables.catalog_categories.get_by_id(category_id)
      if isinstance(category_id, str) and category_id else product["category"]
    )
    subcategory = (
      None if subcategory_id == "" else
      app_tables.catalog_categories.get_by_id(subcategory_id)
      if isinstance(subcategory_id, str) and subcategory_id else product["subcategory"]
    )
  else:
    category = app_tables.catalog_categories.get_by_id(category_id) if category_id else None
    subcategory = app_tables.catalog_categories.get_by_id(subcategory_id) if subcategory_id else None
  if subcategory is not None and (
    category is None or not _category_is_within(subcategory, category)
  ):
    return {"ok": False, "message": "Подкатегория не относится к выбранной категории.", "fields": []}
  category_ids = _custom_field_scope_ids(category, subcategory)
  definitions = _custom_fields_for_category_ids(category_ids)
  values_by_id = {}
  if product is not None:
    for row in app_tables.product_specs.search(product=product):
      source = row["source"] or ""
      if source.startswith("custom-field|"):
        parts = source.split("|", 2)
        if len(parts) == 3:
          values_by_id[parts[1]] = (row, parts[2])
  fields = []
  for definition in definitions:
    row, reference = values_by_id.get(definition["id"], (None, ""))
    value = row["value"] if row is not None else ""
    if definition["kind"] == "multiselect" and value:
      try:
        value = json.loads(value)
      except (TypeError, ValueError):
        value = []
    elif definition["kind"] == "toggle":
      value = value == "true"
    elif definition["kind"] in ("image", "file") and reference.startswith("media:"):
      media_id = reference.split(":", 1)[1]
      media_row = app_tables.product_media.get_by_id(media_id)
      media_file = media_row["file"] if media_row is not None else None
      value = (
        media_file.get_url()
        if media_row is not None and media_row["product"] is not None
        and product is not None and media_row["product"].get_id() == product.get_id()
        and isinstance(media_file, anvil.Media) else ""
      )
    elif definition["kind"] == "file" and reference.startswith("document:"):
      document_id = reference.split(":", 1)[1]
      document = app_tables.catalog_documents.get_by_id(document_id)
      value = (
        _catalog_document_payload(document)["url"]
        if document is not None and document["product"] is not None and product is not None
        and document["product"].get_id() == product.get_id()
        else ""
      )
    fields.append({
      **definition, "value": value,
      "stored_reference": reference,
      "product_id": product.get_id() if product is not None else None,
      "value_row_id": row.get_id() if row is not None else None
    })
  return {"ok": True, "fields": fields}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_product_custom_field_value(product_id, field_id, value, uploaded_file=None):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для редактирования товара.")
  if not isinstance(product_id, str) or not isinstance(field_id, str):
    return {"ok": False, "message": "Выберите товар и дополнительное поле."}
  product = app_tables.products.get_by_id(product_id)
  if product is None:
    return {"ok": False, "message": "Товар не найден."}
  definition = next((
    item for item in _custom_field_definitions()
    if item.get("id") == field_id and item.get("enabled", True)
  ), None)
  if definition is None:
    return {"ok": False, "message": "Поле больше не активно."}
  category = product["category"]
  subcategory = product["subcategory"]
  if definition.get("category_id") not in _custom_field_scope_ids(category, subcategory):
    return {"ok": False, "message": "Это поле не относится к категории товара."}

  kind = definition["kind"]
  display_value = ""
  reference = "empty"
  if kind == "toggle":
    if not isinstance(value, bool):
      return {"ok": False, "message": "Проверьте значение переключателя."}
    display_value = "Да" if value else "Нет"
    reference = "value"
    encoded_value = "true" if value else "false"
  elif kind == "multiselect":
    if not isinstance(value, list) or len(value) > 30 or any(
      not isinstance(item, str) or item not in definition.get("choices", [])
      for item in value
    ):
      return {"ok": False, "message": "Выберите доступные значения поля."}
    normalized_values = list(dict.fromkeys(value))
    if definition.get("required") and not normalized_values:
      return {"ok": False, "message": "Выберите хотя бы одно значение."}
    encoded_value = json.dumps(normalized_values, ensure_ascii=False)
    display_value = ", ".join(normalized_values)
    reference = "value"
  else:
    if value is None:
      value = ""
    if not isinstance(value, str):
      return {"ok": False, "message": "Проверьте значение дополнительного поля."}
    clean = value.strip()
    if len(clean) > (12000 if kind == "rich_text" else 1000):
      return {"ok": False, "message": "Значение поля слишком длинное."}
    if definition.get("required") and not clean and uploaded_file is None:
      return {"ok": False, "message": "Заполните обязательное поле «{}».".format(definition["title"])}
    if kind in ("number", "price") and clean:
      try:
        numeric = float(clean.replace(",", "."))
      except (TypeError, ValueError, OverflowError):
        return {"ok": False, "message": "Введите число для поля «{}».".format(definition["title"])}
      if not math.isfinite(numeric) or (kind == "price" and numeric < 0):
        return {"ok": False, "message": "Проверьте числовое значение поля «{}».".format(definition["title"])}
      clean = str(numeric)
    if kind == "date" and clean:
      try:
        datetime.strptime(clean, "%Y-%m-%d")
      except ValueError:
        return {"ok": False, "message": "Введите дату в формате ГГГГ-ММ-ДД."}
    if kind == "select" and clean and clean not in definition.get("choices", []):
      return {"ok": False, "message": "Выберите значение из списка поля «{}».".format(definition["title"])}
    if kind in ("url", "image", "file") and clean:
      safe_url = _public_source_url(clean)
      if not safe_url:
        return {"ok": False, "message": "Добавьте безопасную HTTP или HTTPS ссылку."}
      clean = safe_url
      reference = "url"
    encoded_value = clean
    display_value = clean

  if uploaded_file is not None:
    if not isinstance(uploaded_file, anvil.Media):
      return {"ok": False, "message": "Выбранный файл некорректен."}
    if kind == "image":
      if uploaded_file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        return {"ok": False, "message": "Для поля изображения выберите JPEG, PNG, WebP или GIF."}
      if uploaded_file.length <= 0 or uploaded_file.length > 8 * 1024 * 1024:
        return {"ok": False, "message": "Размер изображения должен быть не более 8 МБ."}
      checksum = hashlib.sha256(uploaded_file.get_bytes()).hexdigest()
      media_row = app_tables.product_media.get(product=product, checksum=checksum)
      if media_row is None:
        existing = list(app_tables.product_media.search(product=product)[:20])
        if len(existing) >= 20:
          return {"ok": False, "message": "Для товара уже достигнут лимит в 20 изображений."}
        media_row = app_tables.product_media.add_row(
          product=product, file_id=uuid.uuid4().hex, file=uploaded_file, url="",
          source="custom-field", type="gallery",
          alt_text=(definition["title"] or product["model"] or "Фото товара")[:160],
          is_primary=False,
          sort_order=max([row["sort_order"] or 0 for row in existing] or [0]) + 1,
          size=uploaded_file.length, created_at=datetime.now(timezone.utc),
          checksum=checksum
        )
      reference = "media:" + str(media_row.get_id())
      display_value = media_row["file"].get_url() if isinstance(media_row["file"], anvil.Media) else ""
      encoded_value = display_value
    elif kind == "file":
      allowed_document_types = {
        "application/pdf", "application/octet-stream", "application/zip",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      }
      if uploaded_file.content_type not in allowed_document_types or not (
        0 < uploaded_file.length <= 25 * 1024 * 1024
      ):
        return {"ok": False, "message": "Выберите PDF, DOC, DOCX или ZIP размером до 25 МБ."}
      document = cast(Any, app_tables.catalog_documents).add_row(
        title="{} · {}".format(product["model"], definition["title"])[:160],
        kind="other", product=product, file=uploaded_file,
        url="", sort_order=100000, created_at=datetime.now(timezone.utc)
      )
      reference = "document:" + str(document.get_id())
      display_value = _catalog_document_payload(document)["url"]
      encoded_value = display_value
    else:
      return {"ok": False, "message": "Загрузка файла доступна для полей типа «Изображение» или «Файл»."}

  if kind in ("image", "file") and uploaded_file is None and display_value:
    reference = "url"
  if definition.get("required") and not display_value and reference == "empty":
    return {"ok": False, "message": "Заполните обязательное поле «{}».".format(definition["title"])}
  marker = "custom-field|{}|{}".format(field_id, reference)
  existing_rows = list(app_tables.product_specs.search(product=product))
  row = next((item for item in existing_rows if (
    item["source"] or ""
  ).startswith("custom-field|{}|".format(field_id))), None)
  if row is None and len(existing_rows) >= 100:
    return {"ok": False, "message": "У товара достигнут предел в 100 характеристик и дополнительных полей."}
  values = {
    "key": definition["title"], "key_key": "__custom_field__:" + field_id,
    "value": encoded_value, "unit": definition.get("unit", ""),
    "source": marker, "visible": bool(definition.get("show_public")),
    "sort_order": int(definition.get("sort_order", 0)),
    "updated_at": datetime.now(timezone.utc)
  }
  if row is None:
    row = app_tables.product_specs.add_row(product=product, **values)
  else:
    row.update(**values)
  Core.log_audit(
    actor=user, action="catalog.custom_field_value_saved",
    entity_type="product", entity_id=product_id,
    details={"field": definition["code"]}, created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Поле сохранено.", "value": display_value}


@anvil.server.callable
def get_catalog_filter_options(category_id=None):
  _ensure_categories()
  allowed_ids = None
  if category_id:
    if not isinstance(category_id, str):
      return {"ok": False, "message": "Некорректная категория."}
    scope = _catalog_category_scope(category_id)
    if scope is None:
      return {"ok": False, "message": "Категория больше недоступна."}
    allowed_ids = {row.get_id() for row in scope}

  products = list(app_tables.products.search(q.fetch_only("brand", "category", "subcategory"), active=True))
  if allowed_ids is not None:
    products = [
      row for row in products if (
        row["category"] is not None and row["category"].get_id() in allowed_ids
      ) or (
        row["subcategory"] is not None and row["subcategory"].get_id() in allowed_ids
      )
    ]

  brand_counts = {}
  product_ids = set()
  for product in products:
    product_ids.add(product.get_id())
    brand = product["brand"]
    if brand is not None:
      brand_counts[brand.get_id()] = brand_counts.get(brand.get_id(), 0) + 1

  relevant_keys = ("Компрессор", "Страна", "Режим работы", "Класс энергоэффективности")
  values = {key: set() for key in relevant_keys}
  if product_ids:
    for row in app_tables.product_specs.search(
      q.fetch_only("product", "key", "value"),
      q.any_of(*[q.all_of(key=key) for key in relevant_keys]),
      visible=True
    ):
      product = row["product"]
      value = str(row["value"] or "").strip()
      if product is not None and product.get_id() in product_ids and value:
        values[row["key"]].add(value)

  brands = []
  for brand in app_tables.brands.search(q.fetch_only("name"), order_by("name")):
    count = brand_counts.get(brand.get_id(), 0)
    if count:
      brands.append({"id": brand.get_id(), "title": brand["name"], "count": count})

  return {
    "ok": True,
    "brands": brands,
    "compressors": sorted(values["Компрессор"], key=str.casefold),
    "countries": sorted(values["Страна"], key=str.casefold),
    "operation_modes": sorted(values["Режим работы"], key=str.casefold),
    "energy_classes": sorted(values["Класс энергоэффективности"], key=str.casefold)
  }


@anvil.server.callable
def search_catalog(search_text="", category_id=None, cursor=None, active_filter="active",
                   series_id=None, available_only=False, minimum_price=None,
                   maximum_price=None, sort_by="model_asc", brand_id=None,
                   compressor="", country="", operation_mode="", energy_class="",
                   minimum_area=None, maximum_area=None):
  user = _current_user()
  _ensure_categories()
  can_edit = Core.has_permission(user, "catalog.manage")
  if not isinstance(search_text, str) or len(search_text) > 100:
    return {"ok": False, "message": "Поисковый запрос слишком длинный.", "rows": [], "has_more": False}
  if active_filter not in ("active", "inactive", "all"):
    return {"ok": False, "message": "Выбран неизвестный статус каталога.", "rows": [], "has_more": False}
  if not isinstance(available_only, bool):
    return {"ok": False, "message": "Некорректный фильтр наличия.", "rows": [], "has_more": False}
  if sort_by not in ("model_asc", "model_desc", "popular", "price_asc", "price_desc"):
    return {"ok": False, "message": "Выбрана неизвестная сортировка.", "rows": [], "has_more": False}
  for field_value, label in (
    (brand_id, "Производитель"), (compressor, "Компрессор"),
    (country, "Страна"), (operation_mode, "Режим работы"),
    (energy_class, "Класс энергоэффективности")
  ):
    if field_value is not None and not isinstance(field_value, str):
      return {"ok": False, "message": "Некорректный фильтр «{}».".format(label), "rows": [], "has_more": False}
    if isinstance(field_value, str) and len(field_value) > 100:
      return {"ok": False, "message": "Фильтр «{}» слишком длинный.".format(label), "rows": [], "has_more": False}
  minimum_area, error = _number_value({"value": minimum_area}, "value", "Минимальная площадь")
  if error:
    return {"ok": False, "message": error, "rows": [], "has_more": False}
  maximum_area, error = _number_value({"value": maximum_area}, "value", "Максимальная площадь")
  if error:
    return {"ok": False, "message": error, "rows": [], "has_more": False}
  if minimum_area is not None and maximum_area is not None and minimum_area > maximum_area:
    return {"ok": False, "message": "Минимальная площадь не может быть выше максимальной.", "rows": [], "has_more": False}
  minimum_price, error = _number_value(
    {"value": minimum_price}, "value", "Минимальная цена"
  )
  if error:
    return {"ok": False, "message": error, "rows": [], "has_more": False}
  maximum_price, error = _number_value(
    {"value": maximum_price}, "value", "Максимальная цена"
  )
  if error:
    return {"ok": False, "message": error, "rows": [], "has_more": False}
  if minimum_price is not None and maximum_price is not None and minimum_price > maximum_price:
    return {"ok": False, "message": "Минимальная цена не может быть выше максимальной.", "rows": [], "has_more": False}
  if not can_edit:
    active_filter = "active"
  filters = {}
  if active_filter != "all":
    filters["active"] = active_filter == "active"
  ascending = sort_by in ("model_asc", "popular", "price_asc")
  expressions = [
    q.fetch_only(
      "identity_key", "model", "sku", "type", "description", "active", "brand",
      "category", "subcategory", "series",
      brand=q.fetch_only("name"),
      category=q.fetch_only("title", "code"),
      subcategory=q.fetch_only("title", "code"),
      series=q.fetch_only(
        "title", "description", "is_new", "power_range", "status", "active", "image"
      )
    ),
    order_by("model", ascending=ascending),
    order_by("identity_key", ascending=ascending),
    q.page_size(PAGE_SIZE + 1),
    q.all_of(identity_key=q.not_(q.ilike("demo|%")))
  ]
  price_sort = sort_by in ("price_asc", "price_desc")
  offset = 0
  if cursor:
    if not isinstance(cursor, str) or len(cursor) > 600:
      return {"ok": False, "message": "Некорректный курсор каталога.", "rows": [], "has_more": False}
    if price_sort:
      try:
        offset = int(cursor)
      except (TypeError, ValueError):
        return {"ok": False, "message": "Некорректный курсор каталога.", "rows": [], "has_more": False}
      if offset < 0 or offset > 10000:
        return {"ok": False, "message": "Некорректный курсор каталога.", "rows": [], "has_more": False}
    else:
      try:
        cursor_model, cursor_identity = json.loads(cursor)
      except (TypeError, ValueError):
        return {"ok": False, "message": "Некорректный курсор каталога.", "rows": [], "has_more": False}
      if not isinstance(cursor_model, str) or not isinstance(cursor_identity, str):
        return {"ok": False, "message": "Некорректный курсор каталога.", "rows": [], "has_more": False}
      comparison = q.less_than if not ascending else q.greater_than
      expressions.append(q.any_of(
        q.all_of(model=comparison(cursor_model)),
        q.all_of(model=cursor_model, identity_key=comparison(cursor_identity))
      ))
  if category_id:
    if not isinstance(category_id, str):
      return {"ok": False, "message": "Некорректная категория.", "rows": [], "has_more": False}
    scope = _catalog_category_scope(category_id)
    if scope is None:
      return {"ok": False, "message": "Категория больше недоступна.", "rows": [], "has_more": False}
    scope_expression = _category_scope_expression(scope)
    if scope_expression is None:
      return {"ok": True, "rows": [], "has_more": False, "next_cursor": None}
    expressions.append(scope_expression)
  if series_id:
    if not isinstance(series_id, str):
      return {"ok": False, "message": "Некорректная серия.", "rows": [], "has_more": False}
    series = app_tables.catalog_series.get_by_id(series_id)
    if series is None or (not series["active"] and not can_edit):
      return {"ok": False, "message": "Серия больше недоступна.", "rows": [], "has_more": False}
    expressions.append(q.all_of(series=series))
  if available_only:
    available_rows = list(app_tables.product_stock.search(
      q.fetch_only("product"), quantity=q.greater_than(0)
    ))
    available_products = [row["product"] for row in available_rows if row["product"] is not None]
    if not available_products:
      return {"ok": True, "rows": [], "has_more": False, "next_cursor": None}
    expressions.append(q.any_of(*[
      q.all_of(identity_key=product["identity_key"])
      for product in available_products
    ]))
  if brand_id:
    brand = app_tables.brands.get_by_id(brand_id)
    if brand is None:
      return {"ok": False, "message": "Производитель не найден.", "rows": [], "has_more": False}
    expressions.append(q.all_of(brand=brand))

  spec_filter_values = {
    "Компрессор": compressor.strip(),
    "Страна": country.strip(),
    "Режим работы": operation_mode.strip(),
    "Класс энергоэффективности": energy_class.strip()
  }
  for spec_key, wanted in spec_filter_values.items():
    if not wanted:
      continue
    matching_rows = list(app_tables.product_specs.search(
      q.fetch_only("product"), key=spec_key, value=q.ilike(wanted)
    )[:5001])
    matching_products = [row["product"] for row in matching_rows if row["product"] is not None]
    if not matching_products:
      return {"ok": True, "rows": [], "has_more": False, "next_cursor": None}
    expressions.append(q.any_of(*[
      q.all_of(identity_key=product["identity_key"])
      for product in matching_products
    ]))

  if minimum_area is not None or maximum_area is not None:
    area_rows = list(app_tables.product_specs.search(
      q.fetch_only("product", "value"), key=q.ilike("Площадь помещения%")
    )[:10001])
    area_products = []
    for area_row in area_rows:
      product = area_row["product"]
      if product is None:
        continue
      try:
        area_value = float(str(area_row["value"] or "").replace(",", ".").split()[0])
      except (TypeError, ValueError, IndexError):
        continue
      if minimum_area is not None and area_value < minimum_area:
        continue
      if maximum_area is not None and area_value > maximum_area:
        continue
      area_products.append(product)
    if not area_products:
      return {"ok": True, "rows": [], "has_more": False, "next_cursor": None}
    expressions.append(q.any_of(*[
      q.all_of(identity_key=product["identity_key"])
      for product in area_products
    ]))

  if minimum_price is not None or maximum_price is not None:
    price_filter = {}
    if minimum_price is not None and maximum_price is not None:
      price_filter["sale_price"] = q.between(
        minimum_price, maximum_price,
        min_inclusive=True, max_inclusive=True
      )
    elif minimum_price is not None:
      price_filter["sale_price"] = q.greater_than_or_equal_to(minimum_price)
    else:
      price_filter["sale_price"] = q.less_than_or_equal_to(maximum_price)
    matching_price_rows = list(app_tables.product_prices.search(
      q.fetch_only("product", "sale_price"), q.page_size(5001), **price_filter
    )[:5001])
    if len(matching_price_rows) > 5000:
      return {"ok": False, "message": "Для такого диапазона цены слишком много записей. Уточните минимум или максимум.", "rows": [], "has_more": False}
    priced_products = []
    for price_row in matching_price_rows:
      value = price_row["sale_price"]
      if value is None:
        continue
      if minimum_price is not None and value < minimum_price:
        continue
      if maximum_price is not None and value > maximum_price:
        continue
      product_ref = price_row["product"]
      if product_ref is not None:
        priced_products.append(product_ref)
    if not priced_products:
      return {"ok": True, "rows": [], "has_more": False, "next_cursor": None}
    expressions.append(q.any_of(*[
      q.all_of(identity_key=product["identity_key"])
      for product in priced_products
    ]))

  term = search_text.strip()
  if term:
    pattern = "%" + term + "%"
    text_filters = [
      q.all_of(model=q.ilike(pattern)),
      q.all_of(sku=q.ilike(pattern)),
      q.all_of(type=q.ilike(pattern)),
      q.all_of(description=q.ilike(pattern))
    ]
    matching_brands = list(app_tables.brands.search(
      q.fetch_only("name"), name=q.ilike(pattern)
    )[:50])
    text_filters.extend(q.all_of(brand=brand) for brand in matching_brands)
    matching_series = list(app_tables.catalog_series.search(
      q.fetch_only("title"), title=q.ilike(pattern), active=True
    )[:50])
    text_filters.extend(q.all_of(series=series) for series in matching_series)
    matching_categories = list(app_tables.catalog_categories.search(
      q.fetch_only("title"), title=q.ilike(pattern), active=True
    )[:100])
    for category in matching_categories:
      text_filters.append(q.all_of(category=category))
      text_filters.append(q.all_of(subcategory=category))
    matching_specs = list(app_tables.product_specs.search(
      q.fetch_only("product", product=q.fetch_only("identity_key")),
      q.any_of(
        key=q.ilike(pattern), value=q.ilike(pattern), unit=q.ilike(pattern)
      ),
      q.page_size(1001), visible=True
    )[:1001])
    if len(matching_specs) > 1000:
      return {
        "ok": False,
        "message": "Слишком много совпадений в характеристиках. Уточните запрос.",
        "rows": [], "has_more": False
      }
    spec_products = {}
    for spec in matching_specs:
      product = spec["product"]
      if product is not None:
        spec_products[product.get_id()] = product
    if len(spec_products) > 500:
      return {
        "ok": False,
        "message": "Слишком много совпадений в характеристиках. Уточните запрос.",
        "rows": [], "has_more": False
      }
    text_filters.extend(
      q.all_of(identity_key=product["identity_key"])
      for product in spec_products.values()
    )
    expressions.append(q.any_of(*text_filters))

  query_limit = 10001 if price_sort else PAGE_SIZE + 1
  products = list(app_tables.products.search(*expressions, **filters)[:query_limit])
  if price_sort and len(products) > 10000:
    return {"ok": False, "message": "Слишком много товаров для сортировки по цене. Уточните фильтры.", "rows": [], "has_more": False}
  if price_sort:
    # Prices are loaded before ordering, but the query itself may not have a
    # price index. Keep a deterministic fallback: products without a price
    # are always after products with a price.
    price_rows = {
      row["product"].get_id(): row
      for row in app_tables.product_prices.search(
        q.fetch_only("product", "sale_price", "currency"),
        q.any_of(*[q.all_of(product=product) for product in products])
      )
      if row["product"] is not None
    }
    products.sort(
      key=lambda product: (
        price_rows.get(product.get_id()) is None
        or price_rows[product.get_id()]["sale_price"] is None,
        price_rows.get(product.get_id())["sale_price"]
        if price_rows.get(product.get_id()) is not None
        and price_rows[product.get_id()]["sale_price"] is not None else 0,
        (product["model"] or "").casefold(),
        product["identity_key"] or ""
      ),
      reverse=sort_by == "price_desc"
    )
    has_more = len(products) > offset + PAGE_SIZE
    products = products[offset:offset + PAGE_SIZE]
  else:
    has_more = len(products) > PAGE_SIZE
    products = products[:PAGE_SIZE]
  price_by_product = {}
  stock_by_product = {}
  image_by_product = {}
  specs_by_product = {}
  product_documents = {}
  series_documents = {}
  if products:
    product_match = q.any_of(*[q.all_of(product=product) for product in products])
    for row in app_tables.product_prices.search(
      q.fetch_only("product", "sale_price", "currency"), product_match
    ):
      price_by_product[row["product"].get_id()] = row
    for row in app_tables.product_stock.search(
      q.fetch_only("product", "quantity"), product_match
    ):
      stock_by_product[row["product"].get_id()] = row
    for row in app_tables.product_specs.search(
      q.fetch_only("product", "key", "value", "unit", "visible", "sort_order"),
      order_by("sort_order"), product_match
    ):
      specs_by_product.setdefault(row["product"].get_id(), []).append({
        "key": row["key"] or "", "value": row["value"] or "",
        "unit": row["unit"] or "", "visible": row["visible"] is not False,
        "sort_order": row["sort_order"] or 0
      })
    image_candidates = {}
    for row in app_tables.product_media.search(
      q.fetch_only("product", "file", "url", "type", "sort_order", "is_primary"),
      order_by("sort_order"), product_match
    )[:PAGE_SIZE * 8]:
      media_file = row["file"]
      image_url = media_file.get_url() if isinstance(media_file, anvil.Media) else ""
      image_url = image_url or _safe_product_image_url(row["url"] or "")
      if not image_url:
        continue
      product_id = row["product"].get_id()
      media_type = (row["type"] or "").strip().casefold()
      priority = 0 if row["is_primary"] or media_type in ("primary", "main", "cover", "hero") else 1
      current = image_candidates.get(product_id)
      candidate = (priority, row["sort_order"] or 0, image_url)
      if current is None or candidate[:2] < current[:2]:
        image_candidates[product_id] = candidate
    image_by_product = {
      product_id: candidate[2]
      for product_id, candidate in image_candidates.items()
    }
    document_filters = [q.all_of(product=product) for product in products]
    unique_series = {}
    for product in products:
      series = product["series"]
      if series is not None:
        unique_series[series.get_id()] = series
    document_filters.extend(q.all_of(series=series) for series in unique_series.values())
    if document_filters:
      for row in app_tables.catalog_documents.search(
        q.fetch_only("title", "kind", "product", "series", "file", "url", "sort_order"),
        order_by("sort_order"), q.any_of(*document_filters)
      ):
        document = _catalog_document_payload(row)
        if row["product"] is not None:
          product_documents.setdefault(row["product"].get_id(), []).append(document)
        if row["series"] is not None:
          series_documents.setdefault(row["series"].get_id(), []).append(document)

  result = []
  for product in products:
    product_id = product.get_id()
    price = price_by_product.get(product_id)
    stock = stock_by_product.get(product_id)
    brand = product["brand"]
    category = product["category"]
    subcategory = product["subcategory"]
    series = product["series"]
    if series is not None and not series["active"] and not can_edit:
      series = None
    product_image = image_by_product.get(product_id, "")
    is_demo = (product["sku"] or "").startswith("DEMO-")
    image_url = product_image if not is_demo else ""
    sale_price = price["sale_price"] if price is not None else None
    currency = _display_currency(price["currency"]) if price is not None else ""
    quantity = stock["quantity"] if stock is not None else None
    specs = specs_by_product.get(product_id, [])
    spec_map = {item["key"].casefold(): item for item in specs}
    def spec_value(*keys):
      for key in keys:
        item = spec_map.get(key.casefold())
        if item and item["visible"]:
          return "{}{}".format(
            item["value"], " " + item["unit"] if item["unit"] else ""
          ).strip()
      return ""
    category_id_value = category.get_id() if category is not None else None
    subcategory_id_value = subcategory.get_id() if subcategory is not None else None
    result.append({
      "id": product_id,
      "identity_key": product["identity_key"],
      "active": bool(product["active"]),
      "model": product["model"] or "",
      "sku": product["sku"] or "",
      "type": product["type"] or "",
      "description": product["description"] or "",
      "brand": brand["name"] if brand is not None else "Бренд не указан",
      "category": category["title"] if category is not None else "Категория не указана",
      "category_id": category_id_value,
      "subcategory": subcategory["title"] if subcategory is not None else "",
      "subcategory_id": subcategory_id_value,
      "edit_category_id": subcategory_id_value or category_id_value,
      "category_path": " / ".join(
        value for value in (
          category["title"] if category is not None else "",
          subcategory["title"] if subcategory is not None else ""
        ) if value
      ),
      "series_id": series.get_id() if series is not None else None,
      "series_title": series["title"] if series is not None else "",
      "series_description": series["description"] or "" if series is not None else "",
      "series_power_range": series["power_range"] or "" if series is not None else "",
      "series_is_new": bool(series["is_new"]) if series is not None else False,
      "series_image_url": _series_image_url(series) if series is not None else "",
      "series_documents": series_documents.get(series.get_id(), []) if series is not None else [],
      "documents": product_documents.get(product_id, []),
      "image_url": image_url,
      "image_alt": "{} {}".format(brand["name"] if brand is not None else "", product["model"] or "").strip(),
      "image_is_product": bool(product_image) and not is_demo,
      "image_missing": not bool(product_image) or is_demo,
      "image_caption": "Фото модели" if product_image and not is_demo else "Фото модели отсутствует",
      "price_value": sale_price,
      "price_label": "Цена не указана" if sale_price is None else "{} {}".format(
        "{:.2f}".format(sale_price).replace(".", ","), currency
      ).strip(),
      "stock_quantity": quantity,
      "stock_label": "Остаток не указан" if quantity is None else ("В наличии: {}".format(quantity) if quantity > 0 else "Нет в наличии"),
      "specs": [row for row in specs if row["visible"]],
      "cooling_capacity": spec_value("Мощность охлаждения", "Холодопроизводительность", "Номинальная мощность охлаждения"),
      "heating_capacity": spec_value("Мощность обогрева", "Теплопроизводительность", "Номинальная мощность обогрева"),
      "indoor_dimensions": spec_value("Габариты внутреннего блока", "Размеры внутреннего блока", "Габариты внутреннего блока (Ш×В×Г)"),
      "compressor": spec_value("Компрессор"),
      "operation_mode": spec_value("Режим работы"),
      "country": spec_value("Страна"),
      "energy_class": spec_value("Класс энергоэффективности"),
      "area": spec_value("Площадь помещения, м²", "Площадь помещения"),
      "noise_level": spec_value("Уровень шума, Дб", "Уровень шума", "Шум"),
      "can_edit": can_edit
    })

  next_cursor = None
  if has_more:
    if price_sort:
      next_cursor = str(offset + len(products))
    else:
      next_cursor = json.dumps([
        products[-1]["model"] or "", products[-1]["identity_key"]
      ])
  return {
    "ok": True, "rows": result, "has_more": has_more,
    "shown_count": len(result), "next_cursor": next_cursor
  }


@anvil.server.callable
def get_product_card(product_id):
  user = _current_user()
  if not isinstance(product_id, str) or not product_id or len(product_id) > 100:
    return {"ok": False, "message": "Некорректный идентификатор товара."}

  product = app_tables.products.get_by_id(product_id)
  is_admin = Core.has_permission(user, "catalog.manage")
  if product is None or (not product["active"] and not is_admin):
    return {"ok": False, "message": "Товар не найден или больше недоступен."}

  brand = product["brand"]
  category = product["category"]
  subcategory = product["subcategory"]
  series = product["series"]
  if series is not None and not series["active"] and not is_admin:
    series = None
  gallery = _product_gallery(product)
  product_image = gallery[0]["url"] if gallery else ""
  price = app_tables.product_prices.get(product=product)
  stock = app_tables.product_stock.get(product=product)
  is_demo = (product["sku"] or "").startswith("DEMO-")
  data: dict[str, Any] = {
    "id": product.get_id(),
    "brand": brand["name"] if brand is not None else "Бренд не указан",
    "model": product["model"] or "",
    "sku": product["sku"] or "",
    "category": category["title"] if category is not None else "Категория не указана",
    "subcategory": subcategory["title"] if subcategory is not None else "",
    "series": series["title"] if series is not None else "",
    "series_description": series["description"] or "" if series is not None else "",
    "series_power_range": series["power_range"] or "" if series is not None else "",
    "series_is_new": bool(series["is_new"]) if series is not None else False,
    "image_url": product_image if not is_demo else "",
    "image_alt": (
      "Демо-фото направления «{}»".format(
        category["title"] if category is not None else "HVAC"
      ) if is_demo else
      "{} {}".format(
        brand["name"] if brand is not None else "", product["model"] or ""
      ).strip() if product_image else
      "Фото товара отсутствует"
    ),
    "image_is_product": bool(product_image) and not is_demo,
    "type": product["type"] or "",
    "description": product["description"] or "",
    "updated_at": product["updated_at"].isoformat(timespec="minutes") if product["updated_at"] else ""
  }
  if price is not None:
    data["sale_price"] = price["sale_price"]
    data["currency"] = _display_currency(price["currency"])
    if is_admin:
      data.update({
        key: price[key] for key in (
          "purchase_price", "special_price", "discount", "markup", "installation_price"
        )
      })
  if stock is not None:
    data["quantity"] = stock["quantity"]
    if is_admin:
      data["minimum_stock"] = stock["minimum_stock"]

  spec_rows = list(app_tables.product_specs.search(
    q.fetch_only("key", "value", "unit", "source", "visible", "sort_order"),
    order_by("sort_order"),
    q.page_size(101),
    product=product
  )[:101])
  specs = [{
    "key": row["key"],
    "value": row["value"],
    "unit": row["unit"] or "",
    "source": row["source"] or ""
  } for row in spec_rows[:100] if row["visible"] is not False]

  source_rows = list(app_tables.product_sources.search(
    q.fetch_only("url", "publisher", "version", "checked_at"),
    order_by("checked_at"),
    product=product
  )[:5])
  sources = [{
    "url": _public_source_url(row["url"] or ""),
    "publisher": row["publisher"] or "",
    "version": row["version"] or "",
    "checked_at": row["checked_at"].isoformat(timespec="minutes") if row["checked_at"] else ""
  } for row in source_rows]
  return {
    "ok": True,
    "data": data,
    "specs": specs,
    "gallery": gallery,
    "has_more_specs": len(spec_rows) > 100,
    "sources": sources,
    "documents": _catalog_document_rows(product=product),
    "series_documents": _catalog_document_rows(series=series) if series is not None else [],
    "is_admin": is_admin
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_product_editor_data(product_id=None):
  user = Core.require_permission("catalog.manage")
  _ensure_categories()
  if product_id is not None and (not isinstance(product_id, str) or not product_id):
    return {"ok": False, "message": "Некорректный идентификатор товара."}
  product = app_tables.products.get_by_id(product_id) if product_id else None
  if product_id and product is None:
    return {"ok": False, "message": "Товар не найден."}

  empty = {
    "brand_name": "", "model": "", "sku": "", "category_id": None,
    "subcategory_id": None, "series_id": None, "type": "", "description": "",
    "active": True,
    "purchase_price": None, "sale_price": None, "special_price": None,
    "discount": None, "markup": None, "installation_price": None,
    "quantity": None, "minimum_stock": None,
    "source_url": "", "source_publisher": "", "source_version": "",
    "image_url": "", "media": []
  }
  categories = _category_options(include_inactive=True)
  series_options = [_series_payload(row) for row in _series_rows_for_category(active_only=False)]
  if product is None:
    return {
      "ok": True, "product_id": None, "data": empty,
      "categories": categories, "series": series_options,
      "specs": [], "media": [], "documents": [], "custom_fields": []
    }

  data = dict(empty)
  brand = product["brand"]
  category = product["category"]
  subcategory = product["subcategory"]
  series = product["series"]
  data.update({
    "brand_name": brand["name"] if brand is not None else "",
    "model": product["model"],
    "sku": product["sku"] or "",
    "category_id": category.get_id() if category is not None else None,
    "subcategory_id": subcategory.get_id() if subcategory is not None else None,
    "series_id": series.get_id() if series is not None else None,
    "type": product["type"] or "",
    "description": product["description"] or "",
    "active": bool(product["active"]),
    "image_url": _product_image_url(product)
  })
  price = app_tables.product_prices.get(product=product)
  if price is not None:
    for key in ("purchase_price", "sale_price", "special_price", "discount", "markup", "installation_price"):
      data[key] = price[key]
  stock = app_tables.product_stock.get(product=product)
  if stock is not None:
    data["quantity"] = stock["quantity"]
    data["minimum_stock"] = stock["minimum_stock"]
  source = next(iter(app_tables.product_sources.search(product=product)), None)
  if source is not None:
    data["source_url"] = source["url"] or ""
    data["source_publisher"] = source["publisher"] or ""
    data["source_version"] = source["version"] or ""
  specs = [
    {"id": row.get_id(), "product_id": product.get_id(),
     "key": row["key"], "value": row["value"],
     "unit": row["unit"] or "", "source": row["source"] or "",
     "sort_order": row["sort_order"] or 0,
     "visible": row["visible"] is not False}
    for row in app_tables.product_specs.search(
      q.fetch_only("key", "value", "unit", "source", "sort_order", "visible"),
      order_by("sort_order"),
      product=product
    ) if not (row["source"] or "").startswith("custom-field|")
  ]
  custom_field_result = get_product_custom_fields(product.get_id())
  return {
    "ok": True, "product_id": product.get_id(), "data": data,
    "categories": categories, "series": series_options, "specs": specs,
    "custom_fields": custom_field_result["fields"],
    "media": _product_media_admin_rows(product),
    "documents": _catalog_document_rows(product=product)
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_product(product_data, prices, stock, source_data, product_id=None,
                 image_url=""):
  user = Core.require_permission("catalog.manage")
  if not all(isinstance(value, dict) for value in (product_data, prices, stock, source_data)):
    return {"ok": False, "message": "Проверьте заполненные данные."}

  model, error = _text_value(product_data, "model", "Модель", 120, required=True)
  if error:
    return {"ok": False, "message": error}
  model = model or ""
  brand_name, error = _text_value(product_data, "brand_name", "Бренд", 80)
  if error:
    return {"ok": False, "message": error}
  brand_name = brand_name or ""
  sku, error = _text_value(product_data, "sku", "Артикул", 80)
  if error:
    return {"ok": False, "message": error}
  sku = sku or ""
  product_type, error = _text_value(product_data, "type", "Тип", 80)
  if error:
    return {"ok": False, "message": error}
  product_type = product_type or ""
  description, error = _text_value(product_data, "description", "Описание", 2000)
  if error:
    return {"ok": False, "message": error}
  description = description or ""
  active = product_data.get("active", True)
  if not isinstance(active, bool):
    return {"ok": False, "message": "Проверьте состояние товара."}

  category_id = product_data.get("category_id")
  if not isinstance(category_id, str):
    return {"ok": False, "message": "Выберите доступную основную категорию."}
  category = app_tables.catalog_categories.get_by_id(category_id) if category_id else None
  if category is None or category["parent"] is not None or not category["active"]:
    return {"ok": False, "message": "Выберите доступную основную категорию."}
  subcategory_id = product_data.get("subcategory_id")
  if subcategory_id is not None and not isinstance(subcategory_id, str):
    return {"ok": False, "message": "Выберите подкатегорию внутри основной категории."}
  subcategory = app_tables.catalog_categories.get_by_id(subcategory_id) if subcategory_id else None
  parent = subcategory
  belongs_to_category = False
  while parent is not None:
    if parent.get_id() == category.get_id():
      belongs_to_category = True
      break
    parent = parent["parent"]
  if subcategory_id and (
    subcategory is None or not belongs_to_category or not subcategory["active"]
  ):
    return {"ok": False, "message": "Выберите подкатегорию внутри основной категории."}
  series_id = product_data.get("series_id")
  if series_id is not None and not isinstance(series_id, str):
    return {"ok": False, "message": "Проверьте серию товара."}
  series = app_tables.catalog_series.get_by_id(series_id) if series_id else None
  if series_id and (series is None or not _category_is_within(series["category"], category)):
    return {"ok": False, "message": "Серия не относится к выбранной категории."}
  if series is not None and subcategory is not None and not _category_is_within(
    series["category"], subcategory
  ):
    return {"ok": False, "message": "Серия находится вне выбранной подкатегории."}

  price_values, stock_values, error = _parse_offer_data(prices, stock)
  if error:
    return {"ok": False, "message": error}
  price_values = price_values or {}
  stock_values = stock_values or {}
  source_url, error = _text_value(source_data, "url", "Источник", 500)
  if error:
    return {"ok": False, "message": error}
  source_url = source_url or ""
  publisher, error = _text_value(source_data, "publisher", "Поставщик данных", 120)
  if error:
    return {"ok": False, "message": error}
  publisher = publisher or ""
  source_version, error = _text_value(source_data, "version", "Версия источника", 80)
  if error:
    return {"ok": False, "message": error}
  source_version = source_version or ""
  if not isinstance(image_url, str) or len(image_url) > 1000:
    return {"ok": False, "message": "Проверьте ссылку на фотографию товара."}
  image_url = image_url.strip()
  if image_url and not _safe_product_image_url(image_url):
    return {"ok": False, "message": "Укажите публичную HTTPS-ссылку на фотографию товара."}
  if source_url:
    if not _public_source_url(source_url):
      return {"ok": False, "message": "Укажите публичный HTTP/HTTPS-адрес источника без учётных данных и параметров."}

  if product_id is not None and (not isinstance(product_id, str) or not product_id):
    return {"ok": False, "message": "Некорректный идентификатор товара."}
  product = app_tables.products.get_by_id(product_id) if product_id else None
  if product_id and product is None:
    return {"ok": False, "message": "Товар не найден."}
  brand_key = brand_name.casefold()
  sku_key = sku.casefold()
  identity_key = product_identity_key(brand_name, model, sku)
  duplicate = app_tables.products.get(identity_key=identity_key)
  legacy_identity_key = brand_key + "|" + model.casefold()
  if duplicate is None and (brand_key or not sku_key):
    duplicate = app_tables.products.get(identity_key=legacy_identity_key)
  if duplicate is not None and (product is None or duplicate.get_id() != product.get_id()):
    return {"ok": False, "message": "Товар с таким брендом и моделью уже есть в каталоге."}
  if sku_key:
    duplicate_sku = app_tables.products.get(sku_key=sku_key)
    if duplicate_sku is not None and (product is None or duplicate_sku.get_id() != product.get_id()):
      return {"ok": False, "message": "Этот артикул уже используется."}

  brand = None
  if brand_name:
    brand = app_tables.brands.get(name_key=brand_key)
    if brand is None:
      brand = app_tables.brands.add_row(name=brand_name, name_key=brand_key)

  now = datetime.now(timezone.utc)
  is_new = product is None
  product_values = {
    "identity_key": identity_key,
    "brand": brand,
    "model": model,
    "sku": sku,
    "sku_key": sku_key,
    "category": category,
    "subcategory": subcategory,
    "series": series,
    "type": product_type,
    "description": description,
    "active": active,
    "updated_at": now
  }
  if product is None:
    product = app_tables.products.add_row(**product_values)
  else:
    product.update(**product_values)

  currency = Core._setting_value("currency")
  price_values["currency"] = currency
  price_values["updated_at"] = now
  _upsert_offer(app_tables.product_prices, product, price_values)
  stock_values["updated_at"] = now
  _upsert_offer(app_tables.product_stock, product, stock_values)

  if source_url:
    source = next(iter(app_tables.product_sources.search(product=product)), None)
    source_values = {
      "url": source_url,
      "publisher": publisher,
      "version": source_version,
      "checked_at": now
    }
    if source is None:
      app_tables.product_sources.add_row(product=product, **source_values)
    else:
      source.update(**source_values)
  else:
    source = next(iter(app_tables.product_sources.search(product=product)), None)
    if source is not None:
      source.delete()

  primary_image = next((
    row for row in app_tables.product_media.search(
      q.fetch_only("file", "url", "type", "is_primary"), product=product
    )[:30]
    if row["is_primary"] or (row["type"] or "").strip().casefold() == "primary"
  ), None)
  if image_url:
    if (
      primary_image is not None
      and isinstance(primary_image["file"], anvil.Media)
      and image_url == primary_image["file"].get_url()
    ):
      primary_image.update(source=source_url or "", type="primary", is_primary=True)
    else:
      media_values = {
        "file_id": "", "file": None, "url": image_url,
        "source": source_url or "", "type": "primary",
        "alt_text": "{} {}".format(brand_name, model).strip(),
        "is_primary": True, "sort_order": 0, "created_at": now,
        "checksum": ""
      }
      if primary_image is None:
        app_tables.product_media.add_row(product=product, **media_values)
      else:
        primary_image.update(**media_values)
  elif primary_image is not None and primary_image["file"] is None:
    primary_image.delete()

  Core.log_audit(
    actor=user,
    action="catalog.product_created" if is_new else "catalog.product_updated",
    entity_type="product",
    entity_id=product.get_id(),
    details={
      "price_fields": [
        key for key, value in price_values.items()
        if key not in ("currency", "updated_at") and value is not None
      ],
      "stock_fields": [key for key, value in stock_values.items() if key != "updated_at" and value is not None],
      "photo_attached": bool(image_url)
    },
    created_at=now
  )

  return {"ok": True, "product_id": product.get_id(), "message": "Товар сохранён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def update_product_quick_fields(product_id, sale_price, active,
                                category_id=None, series_id=None, quantity=None):
  user = Core.require_permission("catalog.manage")
  if not isinstance(product_id, str) or not product_id:
    return {"ok": False, "message": "Выберите товар."}
  product = app_tables.products.get_by_id(product_id)
  if product is None:
    return {"ok": False, "message": "Товар не найден."}
  if not isinstance(active, bool):
    return {"ok": False, "message": "Проверьте статус публикации."}
  sale_price, error = _number_value(
    {"value": sale_price}, "value", "Цена продажи"
  )
  if error:
    return {"ok": False, "message": error}
  category = product["category"]
  subcategory = product["subcategory"]
  if category_id is not None:
    if not isinstance(category_id, str) or not category_id:
      return {"ok": False, "message": "Выберите категорию товара."}
    selected_category = app_tables.catalog_categories.get_by_id(category_id)
    if selected_category is None or not selected_category["active"]:
      return {"ok": False, "message": "Выбранная категория недоступна."}
    category = selected_category
    while category["parent"] is not None:
      category = category["parent"]
    subcategory = selected_category if selected_category.get_id() != category.get_id() else None

  series = product["series"]
  if series_id is not None:
    if series_id == "":
      series = None
    elif not isinstance(series_id, str):
      return {"ok": False, "message": "Проверьте выбранную серию."}
    else:
      series = app_tables.catalog_series.get_by_id(series_id)
      if series is None or (
        not series["active"]
        and (product["series"] is None or product["series"].get_id() != series.get_id())
      ):
        return {"ok": False, "message": "Выбранная серия недоступна."}
      assigned_category = subcategory or category
      series_category = series["category"]
      if series_category is None or not _category_is_within(assigned_category, series_category):
        return {"ok": False, "message": "Серия должна относиться к выбранной категории."}

  quantity_value = None
  if quantity is not None:
    quantity_value, error = _number_value(
      {"value": quantity}, "value", "Остаток"
    )
    if error:
      return {"ok": False, "message": error}

  now = datetime.now(timezone.utc)
  cast(Any, product).update(
    active=active, category=category, subcategory=subcategory,
    series=series, updated_at=now
  )
  price = app_tables.product_prices.get(product=product)
  if price is not None:
    cast(Any, price).update(sale_price=sale_price, updated_at=now)
  elif sale_price is not None:
    app_tables.product_prices.add_row(
      product=product, sale_price=sale_price,
      currency=Core._setting_value("currency"), updated_at=now
    )
  if quantity is not None:
    stock_row = app_tables.product_stock.get(product=product)
    if stock_row is None and quantity_value is not None:
      app_tables.product_stock.add_row(
        product=product, quantity=quantity_value, updated_at=now
      )
    elif stock_row is not None:
      cast(Any, stock_row).update(quantity=quantity_value, updated_at=now)
  Core.log_audit(
    actor=user, action="catalog.product_quick_updated", entity_type="product",
    entity_id=product_id,
    details={
      "sale_price": sale_price, "active": active,
      "category": category["code"] if category is not None else None,
      "subcategory": subcategory["code"] if subcategory is not None else None,
      "series": series["code"] if series is not None else None,
      "quantity": quantity_value
    }, created_at=now
  )
  return {"ok": True, "message": "Цена, наличие, категория, серия и статус сохранены."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def bulk_update_prices(product_ids, field, value, mode):
  user = Core.require_permission("catalog.manage")
  price_fields = {
    "purchase_price", "sale_price", "special_price", "discount",
    "markup", "installation_price"
  }
  fields = price_fields | {"category_id", "series_id", "active", "quantity"}
  amount = 0.0
  target_category = None
  root_category = None
  target_series = None
  if not isinstance(product_ids, list) or not 1 <= len(product_ids) <= 100:
    return {"ok": False, "message": "Выберите от 1 до 100 товаров для одного пакета."}
  if not isinstance(field, str) or field not in fields or mode not in ("set", "percent"):
    return {"ok": False, "message": "Проверьте тип массового изменения."}
  if mode == "percent" and field not in price_fields:
    return {"ok": False, "message": "Процентное изменение доступно только для цен."}
  if any(not isinstance(product_id, str) or not product_id or len(product_id) > 100 for product_id in product_ids):
    return {"ok": False, "message": "В выборе есть некорректный товар."}
  if len(set(product_ids)) != len(product_ids):
    return {"ok": False, "message": "В выборе есть повторяющиеся товары."}

  if field in price_fields and mode == "set":
    amount, error = _number_value(
      {"amount": value}, "amount", "Цена",
      100 if field == "discount" else None
    )
    if error:
      return {"ok": False, "message": error}
    if amount is None:
      return {"ok": False, "message": "Укажите значение для массового изменения."}
  elif field in price_fields:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
      return {"ok": False, "message": "Укажите изменение в процентах."}
    try:
      amount = float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
      return {"ok": False, "message": "Укажите изменение в процентах."}
    if not math.isfinite(amount) or amount < -100 or amount > 1000:
      return {"ok": False, "message": "Процентное изменение должно быть от −100 до 1000."}
    error = None
  elif field == "active":
    if value not in ("active", "inactive"):
      return {"ok": False, "message": "Выберите состояние публикации."}
  elif field == "category_id":
    if not isinstance(value, str) or not value:
      return {"ok": False, "message": "Выберите категорию для переноса товаров."}
    target_category = app_tables.catalog_categories.get_by_id(value)
    if target_category is None or not target_category["active"]:
      return {"ok": False, "message": "Выбранная категория недоступна."}
    root_category = target_category
    while root_category["parent"] is not None:
      root_category = root_category["parent"]
  elif field == "series_id":
    if value not in (None, "") and not isinstance(value, str):
      return {"ok": False, "message": "Выберите серию для товаров."}
    target_series = app_tables.catalog_series.get_by_id(value) if value else None
    if value and (target_series is None or not target_series["active"]):
      return {"ok": False, "message": "Выбранная серия недоступна."}
  else:
    amount, error = _number_value({"amount": value}, "amount", "Остаток")
    if error:
      return {"ok": False, "message": error}
    if amount is None:
      return {"ok": False, "message": "Укажите количество для массового изменения."}

  updated = 0
  skipped = 0
  now = datetime.now(timezone.utc)
  for start in range(0, len(product_ids), 100):
    batch_ids = product_ids[start:start + 100]
    products = [
      product for product_id in batch_ids
      for product in [app_tables.products.get_by_id(product_id)]
      if product is not None
    ]
    if not products:
      skipped += len(batch_ids)
      continue
    matches = q.any_of(*[q.all_of(product=product) for product in products])
    if field in price_fields:
      price_rows = {
        row["product"].get_id(): row
        for row in app_tables.product_prices.search(
          q.fetch_only("product", field, "currency"), matches
        )
      }
      for product in products:
        row = price_rows.get(product.get_id())
        current = row[field] if row is not None else None
        if mode == "set":
          new_value = amount
        elif current is None:
          skipped += 1
          continue
        else:
          new_value = round(current * (1 + amount / 100), 2)
        if new_value < 0 or (field == "discount" and new_value > 100):
          skipped += 1
          continue
        if row is None:
          app_tables.product_prices.add_row(
            product=product,
            **{field: new_value, "currency": Core._setting_value("currency"), "updated_at": now}
          )
        else:
          row.update(**{field: new_value, "updated_at": now})
        updated += 1
    elif field == "active":
      active_value = value == "active"
      for product in products:
        product.update(active=active_value, updated_at=now)
        updated += 1
    elif field == "category_id":
      if target_category is None or root_category is None:
        return {"ok": False, "message": "Выберите корректную категорию."}
      subcategory = target_category if target_category.get_id() != root_category.get_id() else None
      for product in products:
        current_series = product["series"]
        assigned_category = subcategory or root_category
        if current_series is not None and (
          current_series["category"] is None
          or not _category_is_within(assigned_category, current_series["category"])
        ):
          skipped += 1
          continue
        cast(Any, product).update(
          category=root_category, subcategory=subcategory, updated_at=now
        )
        updated += 1
    elif field == "series_id":
      for product in products:
        assigned_category = product["subcategory"] or product["category"]
        if target_series is not None and (
          assigned_category is None or target_series["category"] is None
          or not _category_is_within(assigned_category, target_series["category"])
        ):
          skipped += 1
          continue
        cast(Any, product).update(series=target_series, updated_at=now)
        updated += 1
    else:
      stock_rows = {
        row["product"].get_id(): row
        for row in app_tables.product_stock.search(q.fetch_only("product"), matches)
      }
      for product in products:
        row = stock_rows.get(product.get_id())
        if row is None:
          app_tables.product_stock.add_row(product=product, quantity=amount, updated_at=now)
        else:
          cast(Any, row).update(quantity=amount, updated_at=now)
        updated += 1
    skipped += len(batch_ids) - len(products)

  Core.log_audit(
    actor=user,
    action="catalog.bulk_update",
    entity_type="products",
    entity_id="",
    details={"field": field, "mode": mode, "requested": len(product_ids), "updated": updated},
    created_at=now
  )
  return {
    "ok": True,
    "updated": updated,
    "skipped": skipped,
    "message": "Обновлено: {}. Пропущено: {}.".format(updated, skipped)
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_product_spec(product_id, key, value, unit="", source="",
                      sort_order=0, visible=True, spec_id=None):
  Core.require_permission("catalog.manage")
  if not isinstance(product_id, str) or not product_id:
    return {"ok": False, "message": "Некорректный идентификатор товара."}
  product = app_tables.products.get_by_id(product_id)
  if product is None:
    return {"ok": False, "message": "Товар не найден."}
  payload = {"key": key, "value": value, "unit": unit, "source": source}
  key, error = _text_value(payload, "key", "Название характеристики", 80, required=True)
  if error:
    return {"ok": False, "message": error}
  key = key or ""
  value, error = _text_value(payload, "value", "Значение характеристики", 200, required=True)
  if error:
    return {"ok": False, "message": error}
  value = value or ""
  unit, error = _text_value(payload, "unit", "Единица измерения", 32)
  if error:
    return {"ok": False, "message": error}
  unit = unit or ""
  source, error = _text_value(payload, "source", "Источник характеристики", 200)
  if error:
    return {"ok": False, "message": error}
  source = source or ""
  if not isinstance(visible, bool):
    return {"ok": False, "message": "Проверьте видимость характеристики."}
  try:
    sort_order = int(sort_order)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Порядок характеристики должен быть целым числом."}
  if sort_order < 0 or sort_order > 100000:
    return {"ok": False, "message": "Порядок характеристики должен быть от 0 до 100000."}

  now = datetime.now(timezone.utc)
  row = app_tables.product_specs.get_by_id(spec_id) if spec_id else None
  if spec_id and (row is None or row["product"].get_id() != product.get_id()):
    return {"ok": False, "message": "Характеристика не найдена у этого товара."}
  duplicate = app_tables.product_specs.get(product=product, key_key=key.casefold())
  if duplicate is not None and (row is None or duplicate.get_id() != row.get_id()):
    return {"ok": False, "message": "У товара уже есть характеристика с таким названием."}
  if row is None:
    row = duplicate
  if row is None:
    existing_specs = list(app_tables.product_specs.search(
      q.fetch_only("key_key"), q.page_size(100), product=product
    ))
    if len(existing_specs) >= 100:
      return {"ok": False, "message": "У товара уже достигнут предел в 100 характеристик."}
  values = {
    "key": key, "key_key": key.casefold(), "value": value, "unit": unit,
    "source": source, "sort_order": sort_order, "visible": visible,
    "updated_at": now
  }
  if row is None:
    app_tables.product_specs.add_row(product=product, **values)
  else:
    row.update(**values)
  return {"ok": True, "message": "Характеристика сохранена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_product_spec(spec_id):
  Core.require_permission("catalog.manage")
  if not isinstance(spec_id, str) or not spec_id:
    return {"ok": False, "message": "Некорректный идентификатор характеристики."}
  row = app_tables.product_specs.get_by_id(spec_id)
  if row is None:
    return {"ok": False, "message": "Характеристика не найдена."}
  row.delete()
  return {"ok": True, "message": "Характеристика удалена."}


def _product_media_admin_rows(product):
  result = []
  for row in app_tables.product_media.search(
    q.fetch_only("file", "url", "type", "alt_text", "is_primary", "sort_order"),
    order_by("sort_order"), product=product
  )[:20]:
    media_file = row["file"]
    image_url = media_file.get_url() if isinstance(media_file, anvil.Media) else ""
    image_url = image_url or _safe_product_image_url(row["url"] or "")
    result.append({
      "id": row.get_id(), "url": image_url,
      "alt_text": row["alt_text"] or "",
      "is_primary": bool(row["is_primary"])
        or (row["type"] or "").strip().casefold() in ("primary", "main", "cover", "hero"),
      "source": row["source"] or ""
    })
  return result


def _flatten_catalog_export_row(record):
  row = dict(record)
  for key in ("specifications", "image_urls", "source_urls", "documents"):
    row[key] = json.dumps(row[key], ensure_ascii=False, allow_nan=False)
  return row


def _csv_safe_row(row):
  safe = {}
  for key, value in row.items():
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
      safe[key] = "'" + value
    else:
      safe[key] = value
  return safe


def _xlsx_column_name(number):
  result = ""
  while number:
    number, remainder = divmod(number - 1, 26)
    result = chr(65 + remainder) + result
  return result


def _catalog_xlsx(columns, records):
  main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
  content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
  ET.register_namespace("", main_ns)
  ET.register_namespace("r", office_rel_ns)

  worksheet = ET.Element("{{{}}}worksheet".format(main_ns))
  sheet_data = ET.SubElement(worksheet, "{{{}}}sheetData".format(main_ns))
  for row_index, values in enumerate(
    [dict(zip(columns, columns))] + [
      _flatten_catalog_export_row(record) for record in records
    ], start=1
  ):
    row_element = ET.SubElement(
      sheet_data, "{{{}}}row".format(main_ns), {"r": str(row_index)}
    )
    for column_index, column in enumerate(columns, start=1):
      value = values.get(column, "")
      reference = "{}{}".format(_xlsx_column_name(column_index), row_index)
      if isinstance(value, bool):
        cell = ET.SubElement(row_element, "{{{}}}c".format(main_ns), {
          "r": reference, "t": "b"
        })
        ET.SubElement(cell, "{{{}}}v".format(main_ns)).text = "1" if value else "0"
      elif isinstance(value, (int, float)) and not isinstance(value, bool):
        cell = ET.SubElement(row_element, "{{{}}}c".format(main_ns), {"r": reference})
        ET.SubElement(cell, "{{{}}}v".format(main_ns)).text = str(value)
      else:
        cell = ET.SubElement(row_element, "{{{}}}c".format(main_ns), {
          "r": reference, "t": "inlineStr"
        })
        inline = ET.SubElement(cell, "{{{}}}is".format(main_ns))
        text = ET.SubElement(inline, "{{{}}}t".format(main_ns), {
          "{http://www.w3.org/XML/1998/namespace}space": "preserve"
        })
        text.text = "" if value is None else str(value)

  workbook = ET.Element("{{{}}}workbook".format(main_ns))
  sheets = ET.SubElement(workbook, "{{{}}}sheets".format(main_ns))
  ET.SubElement(sheets, "{{{}}}sheet".format(main_ns), {
    "name": "Каталог", "sheetId": "1",
    "{{{}}}id".format(office_rel_ns): "rId1"
  })

  root_rels = ET.Element("{{{}}}Relationships".format(package_rel_ns))
  ET.SubElement(root_rels, "{{{}}}Relationship".format(package_rel_ns), {
    "Id": "rId1",
    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "Target": "xl/workbook.xml"
  })
  workbook_rels = ET.Element("{{{}}}Relationships".format(package_rel_ns))
  ET.SubElement(workbook_rels, "{{{}}}Relationship".format(package_rel_ns), {
    "Id": "rId1",
    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
    "Target": "worksheets/sheet1.xml"
  })
  content_types = ET.Element("{{{}}}Types".format(content_ns))
  ET.SubElement(content_types, "{{{}}}Default".format(content_ns), {
    "Extension": "rels",
    "ContentType": "application/vnd.openxmlformats-package.relationships+xml"
  })
  ET.SubElement(content_types, "{{{}}}Default".format(content_ns), {
    "Extension": "xml", "ContentType": "application/xml"
  })
  ET.SubElement(content_types, "{{{}}}Override".format(content_ns), {
    "PartName": "/xl/workbook.xml",
    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
  })
  ET.SubElement(content_types, "{{{}}}Override".format(content_ns), {
    "PartName": "/xl/worksheets/sheet1.xml",
    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
  })

  result = io.BytesIO()
  with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("[Content_Types].xml", ET.tostring(content_types, encoding="utf-8", xml_declaration=True))
    archive.writestr("_rels/.rels", ET.tostring(root_rels, encoding="utf-8", xml_declaration=True))
    archive.writestr("xl/workbook.xml", ET.tostring(workbook, encoding="utf-8", xml_declaration=True))
    archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(workbook_rels, encoding="utf-8", xml_declaration=True))
    archive.writestr("xl/worksheets/sheet1.xml", ET.tostring(worksheet, encoding="utf-8", xml_declaration=True))
  return result.getvalue()


_GITHUB_CATALOG_REPO = "klimatst/anviklimat"
_GITHUB_CATALOG_BRANCH = "master"
_GITHUB_CATALOG_DIR = "theme/assets/catalog/products"


def _github_catalog_token():
  try:
    import anvil.secrets
    token = anvil.secrets.get_secret("GITHUB_CATALOG_TOKEN")
  except Exception:
    return ""
  return token.strip() if isinstance(token, str) else ""


def _safe_github_filename(value):
  value = str(value or "").strip()
  value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
  value = value.strip(".-")[:96]
  return value or "image"


def _publish_catalog_image_to_github(media, product, index=0):
  """Upload a catalog image to GitHub and return a raw URL.
  Disabled when GITHUB_CATALOG_TOKEN is not configured, preserving the old
  Anvil Media fallback without changing existing installations.
  """
  token = _github_catalog_token()
  if not token or not isinstance(media, anvil.Media) or product is None:
    return ""

  data = media.get_bytes()
  if not data:
    return ""

  model = _safe_github_filename(product["model"] or "product")
  checksum = hashlib.sha256(data).hexdigest()[:12]
  extension = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif"
  }.get(media.content_type, ".bin")
  filename = "{}-{}-{}{}".format(model, index + 1, checksum, extension)
  path = "{}/{}".format(_GITHUB_CATALOG_DIR, filename)
  api_url = "https://api.github.com/repos/{}/contents/{}".format(
    _GITHUB_CATALOG_REPO, urllib.parse.quote(path, safe="/")
  )
  payload = json.dumps({
    "message": "Catalog photo: {}".format(product["model"] or filename),
    "content": base64.b64encode(data).decode("ascii"),
    "branch": _GITHUB_CATALOG_BRANCH
  }).encode("utf-8")
  request = urllib.request.Request(
    api_url,
    data=payload,
    method="PUT",
    headers={
      "Authorization": "Bearer " + token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
      "User-Agent": "klimatst-anviklimat-catalog/1.0"
    }
  )
  try:
    with urllib.request.urlopen(request, timeout=30) as response:
      if response.status not in (200, 201):
        return ""
  except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
    return ""
  return "https://raw.githubusercontent.com/{}/{}/{}".format(
    _GITHUB_CATALOG_REPO, _GITHUB_CATALOG_BRANCH, path
  )


def _github_catalog_configured():
  return bool(_github_catalog_token())


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def upload_product_images(product_id, uploaded_files):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для загрузки изображений.")
  if not isinstance(product_id, str) or not product_id:
    return {"ok": False, "message": "Сохраните товар перед добавлением фотографий."}
  product = app_tables.products.get_by_id(product_id)
  if product is None:
    return {"ok": False, "message": "Товар не найден."}
  if not isinstance(uploaded_files, (list, tuple)) or not uploaded_files:
    return {"ok": False, "message": "Выберите одно или несколько изображений."}
  if len(uploaded_files) > 12:
    return {"ok": False, "message": "За один раз можно загрузить не более 12 изображений."}
  existing_rows = list(app_tables.product_media.search(
    q.fetch_only("file", "url", "type", "is_primary", "sort_order"),
    product=product
  )[:20])
  if len(existing_rows) + len(uploaded_files) > 20:
    return {"ok": False, "message": "Для товара уже достигнут лимит в 20 изображений."}
  existing_bytes = 0
  for row in existing_rows:
    size = row["size"]
    if isinstance(size, (int, float)) and not isinstance(size, bool):
      existing_bytes += int(size)
    elif isinstance(row["file"], anvil.Media):
      existing_bytes += row["file"].length

  allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
  max_image_size_mb = AdminStudio.get_admin_studio_setting("media.max_size_mb", 12)
  if isinstance(max_image_size_mb, bool) or not isinstance(max_image_size_mb, (int, float)):
    max_image_size_mb = 12
  max_image_bytes = int(max_image_size_mb * 1024 * 1024)
  checked_files = []
  for media in uploaded_files:
    if not isinstance(media, anvil.Media):
      return {"ok": False, "message": "Один из выбранных файлов не является изображением."}
    if media.content_type not in allowed_types:
      return {"ok": False, "message": "Поддерживаются только JPEG, PNG, WebP и GIF."}
    if media.length <= 0 or media.length > max_image_bytes:
      return {
        "ok": False,
        "message": "Размер каждого изображения должен быть не более {} МБ по настройке медиа.".format(
          max_image_size_mb
        )
      }
    checked_files.append(media)
  if existing_bytes + sum(media.length for media in checked_files) > 40 * 1024 * 1024:
    return {"ok": False, "message": "Общий размер изображений для одного товара ограничен 40 МБ."}

  now = datetime.now(timezone.utc)
  has_primary = any(
    row["is_primary"] or (row["type"] or "").strip().casefold() in ("primary", "main", "cover", "hero")
    for row in existing_rows
  )
  sort_order_value = max(
    [row["sort_order"] or 0 for row in existing_rows] or [-1]
  ) + 1
  created_rows = []
  github_used = 0
  github_ready = _github_catalog_configured()
  for index, media in enumerate(checked_files):
    is_primary = not has_primary and index == 0
    checksum = hashlib.sha256(media.get_bytes()).hexdigest()
    github_url = _publish_catalog_image_to_github(media, product, index) if github_ready else ""
    if github_url:
      file_value = None
      url_value = github_url
      source_value = "github-catalog"
      github_used += 1
      size_value = 0
    else:
      # Safe fallback for apps that have not configured the GitHub token yet.
      file_value = media
      url_value = ""
      source_value = "admin-upload"
      size_value = media.length

    created_rows.append(app_tables.product_media.add_row(
      product=product,
      file_id=uuid.uuid4().hex,
      file=file_value,
      url=url_value,
      source=source_value,
      type="primary" if is_primary else "gallery",
      alt_text=(media.name or product["model"] or "Фото модели")[:160],
      is_primary=is_primary,
      sort_order=sort_order_value + index,
      size=size_value,
      created_at=now,
      checksum=checksum
    ))
    if is_primary:
      has_primary = True
  Core.log_audit(
    actor=user, action="catalog.product_images_uploaded",
    entity_type="product", entity_id=product_id,
    details={"count": len(created_rows)}, created_at=now
  )
  storage_note = (
    " Фото опубликованы в GitHub и сайт использует прямые быстрые ссылки."
    if github_used else
    " GitHub не настроен — использовано встроенное хранилище Anvil."
  )
  return {
    "ok": True, "images": _product_media_admin_rows(product),
    "message": "Загружено изображений: {}.{}"
      .format(len(created_rows), storage_note)
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def set_product_image_primary(media_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для изменения изображений.")
  if not isinstance(media_id, str) or not media_id:
    return {"ok": False, "message": "Выберите изображение."}
  selected = app_tables.product_media.get_by_id(media_id)
  if selected is None:
    return {"ok": False, "message": "Изображение не найдено."}
  product = selected["product"]
  now = datetime.now(timezone.utc)
  for row in app_tables.product_media.search(product=product):
    is_primary = row.get_id() == media_id
    row.update(
      is_primary=is_primary,
      type="primary" if is_primary else (
        "gallery" if (row["type"] or "").strip().casefold() == "primary" else row["type"]
      ),
      sort_order=0 if is_primary else (row["sort_order"] or 1)
    )
  Core.log_audit(
    actor=user, action="catalog.product_image_primary",
    entity_type="product", entity_id=product.get_id(),
    details={"media_id": media_id}, created_at=now
  )
  return {
    "ok": True, "images": _product_media_admin_rows(product),
    "message": "Главное изображение обновлено."
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_product_image(media_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для удаления изображений.")
  if not isinstance(media_id, str) or not media_id:
    return {"ok": False, "message": "Выберите изображение."}
  row = app_tables.product_media.get_by_id(media_id)
  if row is None:
    return {"ok": False, "message": "Изображение уже удалено."}
  product = row["product"]
  was_primary = bool(row["is_primary"]) or (row["type"] or "").strip().casefold() in ("primary", "main", "cover", "hero")
  row.delete()
  images = _product_media_admin_rows(product)
  if was_primary and images:
    replacement = app_tables.product_media.get_by_id(images[0]["id"])
    if replacement is not None:
      replacement.update(is_primary=True, type="primary", sort_order=0)
    images = _product_media_admin_rows(product)
  now = datetime.now(timezone.utc)
  Core.log_audit(
    actor=user, action="catalog.product_image_deleted",
    entity_type="product", entity_id=product.get_id(),
    details={"remaining": len(images)}, created_at=now
  )
  return {"ok": True, "images": images, "message": "Изображение удалено."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_catalog_products_missing_images(search_text="", limit=200):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для просмотра медиаданных.")
  if not isinstance(search_text, str) or len(search_text) > 120:
    return {"ok": False, "message": "Поисковый запрос слишком длинный.", "rows": []}
  if isinstance(limit, bool) or not isinstance(limit, int):
    return {"ok": False, "message": "Некорректный размер списка."}
  limit = min(max(limit, 1), 500)
  products = list(app_tables.products.search(
    q.fetch_only(
      "identity_key", "model", "sku", "brand", "category",
      brand=q.fetch_only("name"), category=q.fetch_only("title")
    ),
    order_by("identity_key"), q.page_size(10001),
    active=True, identity_key=q.not_(q.ilike("demo|%"))
  )[:10001])
  if len(products) > 10000:
    return {"ok": False, "message": "Каталог слишком велик для единой проверки. Уточните поиск."}
  visible_ids = {row.get_id() for row in products}
  products_with_images = {
    row["product"].get_id()
    for row in app_tables.product_media.search(
      q.fetch_only("product", "file", "url")
    )
    if row["product"] is not None
    and row["product"].get_id() in visible_ids
    and (row["file"] is not None or _safe_product_image_url(row["url"] or ""))
  }
  term = search_text.strip().casefold()
  missing = []
  for product in products:
    if product.get_id() in products_with_images:
      continue
    brand = product["brand"]
    category = product["category"]
    row = {
      "id": product.get_id(),
      "brand": brand["name"] if brand is not None else "Бренд не указан",
      "model": product["model"] or "",
      "sku": product["sku"] or "",
      "category": category["title"] if category is not None else "Категория не указана"
    }
    if term and term not in " ".join(row.values()).casefold():
      continue
    missing.append(row)
  return {
    "ok": True, "rows": missing[:limit],
    "has_more": len(missing) > limit,
    "total": len(missing),
    "message": "Без изображений: {}{}".format(
      len(missing), " · показан первый список" if len(missing) > limit else ""
    )
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def export_catalog(search_text="", category_id=None, product_ids=None, format_name="csv",
                   series_id=None, available_only=False, minimum_price=None,
                   maximum_price=None, active_filter="all"):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для экспорта каталога.")
  if not isinstance(search_text, str) or len(search_text) > 100:
    return {"ok": False, "message": "Поисковый запрос слишком длинный."}
  if format_name not in ("csv", "xlsx", "json"):
    return {"ok": False, "message": "Выберите CSV, XLSX или JSON для экспорта."}
  if active_filter not in ("active", "inactive", "all"):
    return {"ok": False, "message": "Выберите состояние товаров для экспорта."}
  if not isinstance(available_only, bool):
    return {"ok": False, "message": "Некорректный фильтр наличия."}
  minimum_price, error = _number_value(
    {"value": minimum_price}, "value", "Минимальная цена"
  )
  if error:
    return {"ok": False, "message": error}
  maximum_price, error = _number_value(
    {"value": maximum_price}, "value", "Максимальная цена"
  )
  if error:
    return {"ok": False, "message": error}
  if minimum_price is not None and maximum_price is not None and minimum_price > maximum_price:
    return {"ok": False, "message": "Минимальная цена не может быть выше максимальной."}
  if category_id is not None and (not isinstance(category_id, str) or not category_id):
    return {"ok": False, "message": "Выберите корректную категорию."}
  selected_series = None
  if series_id is not None:
    if not isinstance(series_id, str) or not series_id:
      return {"ok": False, "message": "Выберите корректную серию."}
    selected_series = app_tables.catalog_series.get_by_id(series_id)
    if selected_series is None:
      return {"ok": False, "message": "Серия не найдена."}
  if product_ids is not None:
    if (
      not isinstance(product_ids, (list, tuple)) or len(product_ids) > 5000
      or any(not isinstance(product_id, str) or not product_id for product_id in product_ids)
    ):
      return {"ok": False, "message": "Список выбранных товаров повреждён."}
    products = []
    seen_ids = set()
    for product_id in product_ids:
      if product_id in seen_ids:
        continue
      seen_ids.add(product_id)
      product = app_tables.products.get_by_id(product_id)
      if product is not None and not (product["identity_key"] or "").startswith("demo|"):
        products.append(product)
  else:
    product_columns = q.fetch_only(
      "identity_key", "model", "sku", "type", "description", "active", "updated_at",
      "brand", "category", "subcategory", "series",
      brand=q.fetch_only("name"),
      category=q.fetch_only("title"),
      subcategory=q.fetch_only("title"),
      series=q.fetch_only("title")
    )
    product_filters = {}
    if active_filter != "all":
      product_filters["active"] = active_filter == "active"
    products = list(app_tables.products.search(
      product_columns,
      order_by("identity_key"),
      q.page_size(10001),
      q.all_of(identity_key=q.not_(q.ilike("demo|%"))),
      **product_filters
    )[:10001])
  if len(products) > 10000:
    return {"ok": False, "message": "Экспорт ограничен 10 000 товарами. Уточните фильтр."}

  if category_id:
    selected_categories = _catalog_category_scope(category_id)
    if selected_categories is None:
      return {"ok": False, "message": "Категория не найдена."}
    descendants = {row.get_id() for row in selected_categories}
    products = [
      product for product in products
      if (product["category"] is not None and product["category"].get_id() in descendants)
      or (product["subcategory"] is not None and product["subcategory"].get_id() in descendants)
    ]

  if selected_series is not None:
    products = [product for product in products if product["series"] is not None
                and product["series"].get_id() == selected_series.get_id()]
  if available_only:
    available = {
      row["product"].get_id()
      for row in app_tables.product_stock.search(
        q.fetch_only("product"), quantity=q.greater_than(0)
      ) if row["product"] is not None
    }
    products = [product for product in products if product.get_id() in available]
  if minimum_price is not None or maximum_price is not None:
    price_filter = {}
    if minimum_price is not None and maximum_price is not None:
      price_filter["sale_price"] = q.between(
        minimum_price, maximum_price,
        min_inclusive=True, max_inclusive=True
      )
    elif minimum_price is not None:
      price_filter["sale_price"] = q.greater_than_or_equal_to(minimum_price)
    else:
      price_filter["sale_price"] = q.less_than_or_equal_to(maximum_price)
    priced = {
      row["product"].get_id()
      for row in app_tables.product_prices.search(
        q.fetch_only("product", "sale_price"), **price_filter
      ) if row["product"] is not None
    }
    products = [product for product in products if product.get_id() in priced]

  term = search_text.strip().casefold()
  if term:
    products = [
      product for product in products
      if term in " ".join((
        product["model"] or "", product["sku"] or "", product["type"] or "",
        product["brand"]["name"] if product["brand"] is not None else ""
        ,product["category"]["title"] if product["category"] is not None else "",
        product["subcategory"]["title"] if product["subcategory"] is not None else "",
        product["series"]["title"] if product["series"] is not None else ""
      )).casefold()
    ]

  columns = (
    "brand", "model", "sku", "category", "subcategory", "series", "type", "description",
    "active", "sale_price", "currency", "quantity", "minimum_stock",
    "specifications", "image_urls", "source_urls", "documents", "updated_at"
  )
  records = []
  for start in range(0, len(products), 100):
    batch = products[start:start + 100]
    match = q.any_of(*[q.all_of(product=product) for product in batch])
    prices = {
      row["product"].get_id(): row
      for row in app_tables.product_prices.search(
        q.fetch_only("product", "sale_price", "currency"), match
      )
    }
    stocks = {
      row["product"].get_id(): row
      for row in app_tables.product_stock.search(
        q.fetch_only("product", "quantity", "minimum_stock"), match
      )
    }
    specs_by_product = {}
    for row in app_tables.product_specs.search(
      q.fetch_only("product", "key", "value", "unit"),
      order_by("key"), match
    ):
      specs_by_product.setdefault(row["product"].get_id(), []).append({
        "key": row["key"] or "", "value": row["value"] or "",
        "unit": row["unit"] or ""
      })
    images_by_product = {}
    for row in app_tables.product_media.search(
      q.fetch_only("product", "file", "url", "type", "alt_text", "is_primary", "sort_order"),
      order_by("sort_order"), match
    ):
      media_file = row["file"]
      image_url = media_file.get_url() if isinstance(media_file, anvil.Media) else ""
      image_url = image_url or _safe_product_image_url(row["url"] or "")
      if not image_url:
        continue
      product_id = row["product"].get_id()
      image = {
        "url": image_url,
        "alt_text": row["alt_text"] or "Фото модели",
        "is_primary": bool(row["is_primary"])
          or (row["type"] or "").strip().casefold() in ("primary", "main", "cover", "hero"),
        "sort_order": row["sort_order"] or 0
      }
      images_by_product.setdefault(product_id, []).append(image)
    sources_by_product = {}
    for row in app_tables.product_sources.search(
      q.fetch_only("product", "url", "publisher", "version"), match
    ):
      sources_by_product.setdefault(row["product"].get_id(), []).append({
        "url": _public_source_url(row["url"] or ""),
        "publisher": row["publisher"] or "", "version": row["version"] or ""
      })
    documents_by_product = {}
    for row in app_tables.catalog_documents.search(
      q.fetch_only("product", "title", "kind", "file", "url", "sort_order"),
      order_by("sort_order"), match
    ):
      product_ref = row["product"]
      if product_ref is None:
        continue
      media_file = row["file"]
      document_url = media_file.get_url() if isinstance(media_file, anvil.Media) else _public_source_url(row["url"] or "")
      documents_by_product.setdefault(product_ref.get_id(), []).append({
        "title": row["title"] or "", "kind": row["kind"] or "other",
        "url": document_url,
        "file_name": media_file.name if isinstance(media_file, anvil.Media) else ""
      })

    for product in batch:
      product_id = product.get_id()
      brand = product["brand"]
      category = product["category"]
      subcategory = product["subcategory"]
      series = product["series"]
      price = prices.get(product_id)
      stock = stocks.get(product_id)
      images = images_by_product.get(product_id, [])
      images.sort(key=lambda image: (not image["is_primary"], image["sort_order"]))
      records.append({
        "brand": brand["name"] if brand is not None else "",
        "model": product["model"] or "",
        "sku": product["sku"] or "",
        "category": category["title"] if category is not None else "",
        "subcategory": subcategory["title"] if subcategory is not None else "",
        "series": series["title"] if series is not None else "",
        "type": product["type"] or "",
        "description": product["description"] or "",
        "active": bool(product["active"]),
        "sale_price": price["sale_price"] if price is not None else None,
        "currency": price["currency"] if price is not None else "RUB",
        "quantity": stock["quantity"] if stock is not None else None,
        "minimum_stock": stock["minimum_stock"] if stock is not None else None,
        "specifications": specs_by_product.get(product_id, []),
        "image_urls": images,
        "source_urls": sources_by_product.get(product_id, []),
        "documents": documents_by_product.get(product_id, []),
        "updated_at": product["updated_at"].isoformat() if product["updated_at"] else ""
      })

  stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  if format_name == "json":
    content = json.dumps(records, ensure_ascii=False, allow_nan=False, indent=2)
    media = anvil.BlobMedia(
      "application/json", content.encode("utf-8"),
      name="catalog-{}.json".format(stamp)
    )
  elif format_name == "xlsx":
    media = anvil.BlobMedia(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      _catalog_xlsx(columns, records),
      name="catalog-{}.xlsx".format(stamp)
    )
  else:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for record in records:
      writer.writerow(_csv_safe_row(_flatten_catalog_export_row(record)))
    media = anvil.BlobMedia(
      "text/csv", output.getvalue().encode("utf-8-sig"),
      name="catalog-{}.csv".format(stamp)
    )
  if media.length > 20 * 1024 * 1024:
    return {"ok": False, "message": "Файл экспорта больше 20 МБ. Уточните фильтры."}
  Core.log_audit(
    actor=user, action="catalog.exported", entity_type="catalog",
    entity_id="", details={"format": format_name, "rows": len(records)},
    created_at=datetime.now(timezone.utc)
  )
  return {
    "ok": True, "file": media, "rows": len(records),
    "message": "Экспортировано товаров: {}.".format(len(records))
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def duplicate_product(product_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для дублирования товаров.")
  if not isinstance(product_id, str) or not product_id:
    return {"ok": False, "message": "Выберите товар для дублирования."}
  original = app_tables.products.get_by_id(product_id)
  if original is None:
    return {"ok": False, "message": "Товар не найден."}
  brand = original["brand"]
  brand_name = brand["name"] if brand is not None else ""
  base_model = (original["model"] or "Товар")[:108]
  suffix_number = 1
  while True:
    suffix = " (копия)" if suffix_number == 1 else " (копия {})".format(suffix_number)
    model = base_model[:120 - len(suffix)] + suffix
    identity_key = product_identity_key(brand_name, model, "")
    if app_tables.products.get(identity_key=identity_key) is None:
      break
    suffix_number += 1

  now = datetime.now(timezone.utc)
  duplicate = app_tables.products.add_row(
    identity_key=identity_key,
    brand=brand,
    model=model,
    sku="",
    sku_key="",
    category=original["category"],
    subcategory=original["subcategory"],
    series=original["series"],
    type=original["type"] or "",
    description=original["description"] or "",
    active=False,
    updated_at=now
  )
  original_price = app_tables.product_prices.get(product=original)
  if original_price is not None:
    price_values = {
      key: original_price[key]
      for key in (
        "purchase_price", "sale_price", "special_price", "discount",
        "markup", "installation_price"
      ) if original_price[key] is not None
    }
    price_values["currency"] = original_price["currency"] or "RUB"
    price_values["updated_at"] = now
    app_tables.product_prices.add_row(product=duplicate, **price_values)
  original_stock = app_tables.product_stock.get(product=original)
  if original_stock is not None:
    stock_values = {
      key: original_stock[key]
      for key in ("quantity", "minimum_stock")
      if original_stock[key] is not None
    }
    stock_values["updated_at"] = now
    app_tables.product_stock.add_row(product=duplicate, **stock_values)
  for row in app_tables.product_specs.search(product=original):
    app_tables.product_specs.add_row(
      product=duplicate, key=row["key"] or "", key_key=row["key_key"] or "",
      value=row["value"] or "", unit=row["unit"] or "",
      source=row["source"] or "", sort_order=row["sort_order"] or 0,
      visible=row["visible"] is not False, updated_at=now
    )
  for row in app_tables.product_sources.search(product=original):
    app_tables.product_sources.add_row(
      product=duplicate, url=row["url"] or "",
      publisher=row["publisher"] or "", version=row["version"] or "",
      manual_fields=row["manual_fields"] or {},
      import_identity_key=row["import_identity_key"] or "",
      checked_at=row["checked_at"] or now
    )
  for row in app_tables.catalog_documents.search(product=original):
    cast(Any, app_tables.catalog_documents).add_row(
      title=row["title"] or "", kind=row["kind"] or "other",
      product=duplicate, series=None, file=row["file"], url=row["url"] or "",
      sort_order=row["sort_order"] or 0, created_at=now
    )
  Core.log_audit(
    actor=user, action="catalog.product_duplicated", entity_type="product",
    entity_id=duplicate.get_id(), details={"source_product_id": product_id},
    created_at=now
  )
  return {
    "ok": True, "product_id": duplicate.get_id(),
    "message": "Создан черновик-копия товара. Проверьте артикул и активируйте после проверки."
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def delete_product(product_id):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для удаления товара.")
  if not isinstance(product_id, str) or not product_id:
    return {"ok": False, "message": "Выберите товар."}
  product = app_tables.products.get_by_id(product_id)
  if product is None:
    return {"ok": False, "message": "Товар уже удалён."}
  references = (
    ("заказах каталога", app_tables.catalog_orders.search(product=product)),
    ("BOM систем", app_tables.bom.search(product=product)),
    ("правилах совместимости", app_tables.compatibility.search(product=product)),
    ("правилах совместимости", app_tables.compatibility.search(compatible_product=product)),
    ("сметах", app_tables.estimate_lines.search(product=product)),
    ("сервисных заявках", app_tables.service.search(product=product)),
    ("системах", app_tables.system_components.search(product=product))
  )
  for reference_name, rows in references:
    if next(iter(rows), None) is not None:
      return {
        "ok": False,
        "message": "Товар связан с данными в разделе «{}». Снимите флажок публикации вместо удаления.".format(reference_name)
      }
  for row in app_tables.system_connections.search(q.fetch_only("properties")):
    properties = row["properties"] or {}
    if isinstance(properties, dict) and properties.get("material_product_id") == product_id:
      return {
        "ok": False,
        "message": "Товар используется в инженерной схеме. Снимите флажок публикации вместо удаления."
      }

  product_id = product.get_id()
  for table_name in (
    "catalog_documents", "product_media", "product_prices", "product_sources",
    "product_specs", "product_stock"
  ):
    table = getattr(app_tables, table_name)
    for row in list(table.search(product=product)):
      row.delete()
  product.delete()
  Core.log_audit(
    actor=user, action="catalog.product_deleted", entity_type="product",
    entity_id=product_id, details={}, created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Товар и неиспользуемые данные его карточки удалены."}
