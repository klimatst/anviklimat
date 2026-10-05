import anvil.secrets
from datetime import datetime, timezone
import json
import math
from typing import Any, cast

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core


COMPATIBILITY_TYPES = {
  "compatible", "required", "optional", "alternative", "incompatible"
}
ROUTE_TYPES = {"refrigerant", "duct", "cable", "drain", "hydronic"}
MAX_PRODUCTS = 200
MAX_BOM_LINES = 600
BOM_BATCH_SIZE = 100


def _user():
  return anvil.users.get_user()


def _text(value, label, maximum, required=True):
  if value is None:
    value = ""
  if not isinstance(value, str):
    return None, "Проверьте поле «{}».".format(label)
  value = value.strip()
  if required and not value:
    return None, "Заполните поле «{}».".format(label)
  if len(value) > maximum:
    return None, "Поле «{}» слишком длинное.".format(label)
  return value, None


def _number(value, label, minimum=None, maximum=None, integer=False):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None, "Проверьте числовое поле «{}».".format(label)
  try:
    number = float(value)
  except (OverflowError, TypeError, ValueError):
    return None, "Проверьте числовое поле «{}».".format(label)
  if not math.isfinite(number):
    return None, "Значение «{}» должно быть конечным.".format(label)
  if minimum is not None and number < minimum:
    return None, "Значение «{}» ниже допустимого минимума.".format(label)
  if maximum is not None and number > maximum:
    return None, "Значение «{}» выше допустимого максимума.".format(label)
  if integer and not number.is_integer():
    return None, "Поле «{}» должно быть целым числом.".format(label)
  return number, None


def _decode_object(raw, label):
  if isinstance(raw, dict):
    return raw, None
  if not isinstance(raw, str) or len(raw) > 4000:
    return None, "Поле «{}» должно быть небольшим JSON-объектом.".format(label)
  try:
    value = json.loads(raw)
  except json.JSONDecodeError:
    return None, "Проверьте JSON в поле «{}».".format(label)
  if not isinstance(value, dict):
    return None, "Поле «{}» должно быть JSON-объектом.".format(label)
  return value, None


def _product_label(product):
  if product is None:
    return "Товар не указан"
  brand = product["brand"]
  return "{} {}".format(
    brand["name"] if brand is not None else "",
    product["model"] or ""
  ).strip()


def _products_for_system(system):
  products = {}
  for row in app_tables.system_components.search(
    q.fetch_only("product"), system=system
  )[:MAX_PRODUCTS]:
    product = row["product"]
    if product is not None:
      products[product.get_id()] = product
  return products


def _compatibility_issues(system, products):
  if not products:
    return []
  product_match = q.any_of(*[
    q.all_of(product=product) for product in products.values()
  ])
  reverse_match = q.any_of(*[
    q.all_of(compatible_product=product) for product in products.values()
  ])
  matches = list(app_tables.compatibility.search(
    q.fetch_only(
      "product", "compatible_product", "type", "rule", "source", "version",
      product=q.fetch_only("brand", "model", brand=q.fetch_only("name")),
      compatible_product=q.fetch_only("brand", "model", brand=q.fetch_only("name"))
    ),
    q.any_of(product=product_match, compatible_product=reverse_match),
    enabled=True
  )[:401])
  if len(matches) > 400:
    return ["Для проверки найдено более 400 правил совместимости; сузьте состав системы."]
  product_ids = set(products)
  issues = []
  for row in matches:
    first = row["product"]
    second = row["compatible_product"]
    if first is None or second is None:
      continue
    first_id = first.get_id()
    second_id = second.get_id()
    if row["type"] == "incompatible" and first_id in product_ids and second_id in product_ids:
      issues.append("Несовместимое оборудование: {} ↔ {}.".format(
        _product_label(first), _product_label(second)
      ))
    elif row["type"] == "required" and first_id in product_ids and second_id not in product_ids:
      issues.append("Для {} требуется {}.".format(
        _product_label(first), _product_label(second)
      ))
  return issues


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_compatibility_records(product_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": []}
  if product_id is not None and (not isinstance(product_id, str) or not product_id):
    return {"ok": False, "message": "Некорректный товар.", "rows": []}
  product = app_tables.products.get_by_id(product_id) if product_id else None
  if product_id and product is None:
    return {"ok": False, "message": "Товар не найден.", "rows": []}
  filters = {"product": product} if product is not None else {}
  rows = app_tables.compatibility.search(
    q.fetch_only(
      "product", "compatible_product", "type", "rule", "source", "version",
      "enabled", "updated_at",
      product=q.fetch_only("model", "brand", brand=q.fetch_only("name")),
      compatible_product=q.fetch_only("model", "brand", brand=q.fetch_only("name"))
    ),
    order_by("type"), **filters
  )[:100]
  return {
    "ok": True,
    "rows": [{
      "id": row.get_id(),
      "product_id": row["product"].get_id() if row["product"] is not None else None,
      "compatible_product_id": (
        row["compatible_product"].get_id()
        if row["compatible_product"] is not None else None
      ),
      "product": _product_label(row["product"]),
      "compatible_product": _product_label(row["compatible_product"]),
      "type": row["type"], "rule": row["rule"] or {},
      "source": row["source"], "version": row["version"],
      "enabled": row["enabled"], "updated_at": row["updated_at"]
    } for row in rows],
    "can_edit": Core.has_permission(user, "catalog.manage"),
    "types": [
      ("compatible", "Совместимо"), ("required", "Обязательно"),
      ("optional", "Опционально"), ("alternative", "Альтернатива"),
      ("incompatible", "Несовместимо")
    ]
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def save_compatibility(product_id, compatible_product_id, compatibility_type,
                       rule_raw, source, version, enabled=True, compatibility_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  Core.require_permission("catalog.manage")
  if (
    not isinstance(product_id, str) or not product_id
    or not isinstance(compatible_product_id, str) or not compatible_product_id
    or product_id == compatible_product_id
  ):
    return {"ok": False, "message": "Выберите два разных товара."}
  product = app_tables.products.get_by_id(product_id)
  compatible_product = app_tables.products.get_by_id(compatible_product_id)
  if product is None or compatible_product is None:
    return {"ok": False, "message": "Один из товаров не найден."}
  if not isinstance(compatibility_type, str) or compatibility_type not in COMPATIBILITY_TYPES:
    return {"ok": False, "message": "Выберите тип совместимости."}
  rule, error = _decode_object(rule_raw, "Правило")
  if error:
    return {"ok": False, "message": error}
  try:
    if len(json.dumps(rule, ensure_ascii=False, allow_nan=False)) > 4000:
      return {"ok": False, "message": "Правило совместимости слишком большое."}
  except (TypeError, ValueError):
    return {"ok": False, "message": "Проверьте значения правила совместимости."}
  source, error = _text(source, "Источник", 300)
  if error:
    return {"ok": False, "message": error}
  version, error = _text(version, "Версия источника", 80)
  if error:
    return {"ok": False, "message": error}
  if not isinstance(enabled, bool):
    return {"ok": False, "message": "Проверьте состояние правила."}
  if compatibility_id is not None and (
    not isinstance(compatibility_id, str) or not compatibility_id
  ):
    return {"ok": False, "message": "Некорректное правило совместимости."}
  row = app_tables.compatibility.get_by_id(compatibility_id) if compatibility_id else None
  if compatibility_id and (
    row is None or row["product"] is None
    or row["product"].get_id() != product_id
  ):
    return {"ok": False, "message": "Правило не найдено для выбранного товара."}
  duplicate = app_tables.compatibility.get(
    product=product, compatible_product=compatible_product,
    type=compatibility_type
  )
  if duplicate is not None and (row is None or duplicate.get_id() != row.get_id()):
    return {"ok": False, "message": "Такое правило уже существует."}
  now = datetime.now(timezone.utc)
  values = {
    "product": product, "compatible_product": compatible_product,
    "type": compatibility_type, "rule": rule, "source": source,
    "version": version, "enabled": enabled, "updated_at": now
  }
  if row is None:
    row = app_tables.compatibility.add_row(**values)
    action = "engineering.compatibility_created"
  else:
    row.update(**values)
    action = "engineering.compatibility_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="compatibility",
    entity_id=row.get_id(),
    details={"type": compatibility_type, "version": version, "enabled": enabled},
    created_at=now
  )
  return {"ok": True, "id": row.get_id(), "message": "Правило совместимости сохранено."}


@anvil.server.callable(require_user=True)
def validate_system_compatibility(system_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(system_id, str) or not system_id:
    return {"ok": False, "message": "Некорректный идентификатор системы."}
  system = app_tables.systems.get_by_id(system_id)
  if system is None:
    return {"ok": False, "message": "Система не найдена."}
  if not Core.can_access_project(system["project"], anvil.users.get_user()):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  products = _products_for_system(system)
  issues = _compatibility_issues(system, products)
  return {
    "ok": True, "valid": not issues,
    "issues": issues,
    "checked_products": len(products)
  }


@anvil.server.callable(require_user=True)
def calculate_system_routing(system_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(system_id, str) or not system_id:
    return {"ok": False, "message": "Некорректный идентификатор системы."}
  system = app_tables.systems.get_by_id(system_id)
  if system is None:
    return {"ok": False, "message": "Система не найдена."}
  if not Core.can_access_project(system["project"], anvil.users.get_user()):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  routes = []
  totals = {}
  missing = []
  for row in app_tables.system_connections.search(
    q.fetch_only(
      "type", "properties", "source_component", "target_component",
      source_component=q.fetch_only("name"),
      target_component=q.fetch_only("name")
    ),
    system=system
  )[:400]:
    route_type = row["type"]
    if route_type not in ROUTE_TYPES:
      continue
    properties = row["properties"] or {}
    source = row["source_component"]
    target = row["target_component"]
    length = properties.get("length_m")
    diameter = properties.get("diameter_mm")
    slope = properties.get("slope_percent")
    elevation = properties.get("elevation_m")
    branches = properties.get("branches")
    fittings = properties.get("fittings")
    route_name = "{} → {}".format(
      source["name"] if source is not None else "Узел",
      target["name"] if target is not None else "Узел"
    )
    item: dict = {"type": route_type, "name": route_name}
    if length is None:
      missing.append("{}: укажите длину в метрах.".format(route_name))
    else:
      length, error = _number(length, "Длина", 0.000001, 1000000)
      if error:
        return {"ok": False, "message": "{}: {}".format(route_name, error)}
      item["length_m"] = length or 0.0
      totals[route_type] = totals.get(route_type, 0.0) + (length or 0.0)
    if diameter is not None:
      diameter, error = _number(diameter, "Диаметр", 0.000001, 1000000)
      if error:
        return {"ok": False, "message": "{}: {}".format(route_name, error)}
      item["diameter_mm"] = diameter or 0.0
    if slope is not None:
      slope, error = _number(slope, "Уклон", -100, 100)
      if error:
        return {"ok": False, "message": "{}: {}".format(route_name, error)}
      item["slope_percent"] = slope or 0.0
    if elevation is not None:
      elevation, error = _number(elevation, "Перепад высот", -10000, 10000)
      if error:
        return {"ok": False, "message": "{}: {}".format(route_name, error)}
      item["elevation_m"] = elevation or 0.0
    for key, value in (("branches", branches), ("fittings", fittings)):
      if value is not None:
        value, error = _number(value, key, 0, 1000000, integer=True)
        if error:
          return {"ok": False, "message": "{}: {}".format(route_name, error)}
        item[key] = int(value or 0)
    routes.append(item)
  return {
    "ok": True, "complete": not missing, "routes": routes,
    "lengths_m": totals, "missing": missing,
    "message": "Маршруты проверены по заданным длинам и параметрам."
  }


def _sync_bom_rows(table, desired, existing_rows, now):
  existing = {}
  duplicate_rows = []
  for row in existing_rows:
    key = row["line_key"]
    if not key or key in existing:
      duplicate_rows.append(row)
    else:
      existing[key] = row

  rows_to_add = []
  rows_to_update = []
  for key, values in desired.items():
    row = existing.pop(key, None)
    if row is None:
      new_values = dict(values)
      new_values["created_at"] = now
      rows_to_add.append(new_values)
      continue
    changes = {}
    for field, value in values.items():
      if field == "system":
        continue
      current = row[field]
      if field == "product":
        current_id = current.get_id() if current is not None else None
        value_id = value.get_id() if value is not None else None
        if current_id == value_id:
          continue
      elif current == value:
        continue
      changes[field] = value
    if changes:
      rows_to_update.append((row, changes))

  rows_to_delete = duplicate_rows + list(existing.values())
  for start in range(0, len(rows_to_add), BOM_BATCH_SIZE):
    table.add_rows(rows_to_add[start:start + BOM_BATCH_SIZE])
  for row, changes in rows_to_update:
    row.update(**changes)
  for row in rows_to_delete:
    row.delete()
  updated = len(rows_to_update)
  return len(rows_to_add), updated, len(rows_to_delete)


@anvil.server.callable(require_user=True)
def generate_system_bom(system_id):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(system_id, str) or not system_id:
    return {"ok": False, "message": "Некорректный идентификатор системы."}
  system = app_tables.systems.get_by_id(system_id)
  if system is None:
    return {"ok": False, "message": "Система не найдена."}
  if not Core.can_access_project(system["project"], user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  components = list(app_tables.system_components.search(
    q.fetch_only("kind", "name", "quantity", "properties", "product",
                 "product_snapshot"),
    system=system
  )[:MAX_PRODUCTS + 1])
  if len(components) > MAX_PRODUCTS:
    return {"ok": False, "message": "Слишком много узлов для одного пакета BOM."}
  products = {}
  for row in components:
    if row["product"] is not None:
      products[row["product"].get_id()] = row["product"]
  route_rows = list(app_tables.system_connections.search(
    q.fetch_only("type", "properties", "source_component", "target_component"),
    system=system
  )[:401])
  if len(route_rows) > 400:
    return {"ok": False, "message": "Слишком много связей для одного пакета BOM."}
  for route in route_rows:
    material_id = (route["properties"] or {}).get("material_product_id")
    if isinstance(material_id, str) and material_id not in products:
      material = app_tables.products.get_by_id(material_id)
      if material is not None:
        products[material_id] = material
  price_by_product = {}
  if products:
    product_match = q.any_of(*[
      q.all_of(product=product) for product in products.values()
    ])
    for price in app_tables.product_prices.search(
      q.fetch_only("product", "sale_price", "currency", "updated_at"),
      product_match
    ):
      price_by_product[price["product"].get_id()] = price

  desired = {}
  warnings = []
  for row in components:
    product = row["product"]
    properties = row["properties"] or {}
    description = ""
    snapshot = row["product_snapshot"] or {}
    price_snapshot = {}
    if product is not None:
      description = snapshot.get("label") or _product_label(product)
      price = price_by_product.get(product.get_id())
      if price is not None:
        price_snapshot = {
          "sale_price": price["sale_price"],
          "currency": price["currency"] or "",
          "updated_at": price["updated_at"].isoformat() if price["updated_at"] else ""
        }
      item_snapshot = {
        "product": snapshot,
        "price": price_snapshot
      }
      desired["component:" + row.get_id()] = {
        "system": system, "line_key": "component:" + row.get_id(),
        "product": product, "kind": "equipment", "description": description,
        "quantity": row["quantity"], "unit": properties.get("bom_unit") or "шт.",
        "source": "catalog", "properties": item_snapshot
      }
    else:
      description = properties.get("bom_description", "")
      if description:
        unit, error = _text(properties.get("bom_unit"), "Единица BOM", 24)
        if error:
          return {"ok": False, "message": "{}: {}".format(row["name"], error)}
        quantity, error = _number(row["quantity"], "Количество BOM", 0.000001, 1000000)
        if error:
          return {"ok": False, "message": "{}: {}".format(row["name"], error)}
        desired["component:" + row.get_id()] = {
          "system": system, "line_key": "component:" + row.get_id(),
          "product": None, "kind": "material", "description": description,
          "quantity": quantity, "unit": unit, "source": "project",
          "properties": dict(properties)
        }
      elif row["kind"] in ("equipment", "material"):
        warnings.append("{} не привязан к товару и не содержит описания BOM.".format(row["name"]))

  for route in route_rows:
    properties = route["properties"] or {}
    description, error = _text(
      properties.get("bom_description"), "Описание маршрута BOM", 200,
      required=False
    )
    if error:
      return {"ok": False, "message": error}
    if not description:
      continue
    unit, error = _text(properties.get("bom_unit"), "Единица маршрута BOM", 24)
    if error:
      return {"ok": False, "message": error}
    quantity = properties.get("bom_quantity", properties.get("length_m"))
    quantity, error = _number(quantity, "Количество маршрута BOM", 0.000001, 1000000)
    if error:
      return {"ok": False, "message": error}
    material_id = properties.get("material_product_id")
    material = None
    price_snapshot = {}
    if material_id:
      if not isinstance(material_id, str) or len(material_id) > 100:
        return {"ok": False, "message": "Некорректный товар материала маршрута."}
      material = products.get(material_id)
      if material is None:
        return {"ok": False, "message": "Товар материала маршрута не найден."}
      price = price_by_product.get(material.get_id())
      if price is not None:
        price_snapshot = {
          "sale_price": price["sale_price"], "currency": price["currency"] or "",
          "updated_at": price["updated_at"].isoformat() if price["updated_at"] else ""
        }
    source = route["source_component"]
    target = route["target_component"]
    line_key = "route:{}:{}:{}".format(
      source.get_id() if source is not None else "",
      target.get_id() if target is not None else "",
      route["type"]
    )
    desired[line_key] = {
      "system": system, "line_key": line_key, "product": material,
      "kind": "material", "description": description, "quantity": quantity,
      "unit": unit, "source": "route",
      "properties": {"price": price_snapshot, "route_type": route["type"]}
    }

  issues = _compatibility_issues(system, products)
  warnings.extend(issues)
  existing_rows = list(app_tables.bom.search(
    q.fetch_only(
      "line_key", "product", "kind", "description", "quantity", "unit",
      "source", "properties"
    ), system=system
  )[:MAX_BOM_LINES + 1])
  if len(existing_rows) > MAX_BOM_LINES:
    return {"ok": False, "message": "Спецификация превышает предел 600 строк."}
  now = datetime.now(timezone.utc)
  created, updated, removed = _sync_bom_rows(
    cast(Any, app_tables.bom), desired, existing_rows, now
  )
  Core.log_audit(
    actor=user, action="engineering.bom_generated", entity_type="system",
    entity_id=system_id,
    details={"lines": len(desired), "created": created, "updated": updated,
             "removed": removed, "warnings": len(warnings)}, created_at=now
  )
  return {
    "ok": True, "lines": len(desired), "warnings": warnings,
    "message": "Спецификация обновлена по явным компонентам и материалам."
  }


@anvil.server.callable(require_user=True)
def get_system_bom(system_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": []}
  if not isinstance(system_id, str) or not system_id:
    return {"ok": False, "message": "Некорректный идентификатор системы.", "rows": []}
  system = app_tables.systems.get_by_id(system_id)
  if system is None:
    return {"ok": False, "message": "Система не найдена.", "rows": []}
  if not Core.can_access_project(system["project"], anvil.users.get_user()):
    return {"ok": False, "message": "Проект недоступен этой учётной записи.", "rows": []}
  return {
    "ok": True,
    "rows": [{
      "description": row["description"], "kind": row["kind"],
      "quantity": row["quantity"], "unit": row["unit"],
      "quantity_label": "{} {}".format(row["quantity"], row["unit"]),
      "source": row["source"] or ""
    } for row in app_tables.bom.search(
      q.fetch_only("description", "kind", "quantity", "unit", "source"),
      order_by("line_key"), system=system
    )[:MAX_BOM_LINES]]
  }
