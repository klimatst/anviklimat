import anvil.secrets
from datetime import datetime, timezone
import json
import math

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core


SYSTEM_TYPES = [
  ("split", "Сплит-система"), ("multi_split", "Мульти-сплит"),
  ("commercial_ac", "Коммерческое кондиционирование"), ("vrf_vrv", "VRF/VRV"),
  ("ventilation", "Вентиляция"), ("ahu", "AHU"),
  ("heat_recovery", "Рекуперация"), ("humidification", "Увлажнение"),
  ("dehumidification", "Осушение"), ("purification", "Очистка воздуха"),
  ("heating", "Отопление"), ("heat_pump", "Тепловой насос"),
  ("hydronics", "Гидравлика"), ("refrigeration", "Холодоснабжение"),
  ("bms", "BMS"), ("drainage", "Дренаж"), ("electrical", "Электрика"),
  ("combined_hvac", "Объединённая HVAC-система")
]
NODE_KINDS = {
  "equipment", "controller", "sensor", "valve", "pump",
  "route", "branch", "group", "other"
}
CONNECTION_TYPES = {
  "refrigerant", "duct", "cable", "drain", "hydronic", "control", "related"
}
MAX_NODES = 200
MAX_CONNECTIONS = 400
MAX_GRAPH_BYTES = 512 * 1024


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


def _number(value, label, minimum=None, maximum=None):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None, "Проверьте числовое поле «{}».".format(label)
  try:
    value = float(value)
  except (OverflowError, TypeError, ValueError):
    return None, "Проверьте числовое поле «{}».".format(label)
  if not math.isfinite(value) or (minimum is not None and value < minimum) or (
    maximum is not None and value > maximum
  ):
    return None, "Значение поля «{}» вне допустимого диапазона.".format(label)
  return value, None


def _finite(value):
  try:
    return math.isfinite(float(value))
  except (OverflowError, TypeError, ValueError):
    return False


def _properties(value):
  if not isinstance(value, dict) or len(value) > 24:
    return None, "Параметры узла должны быть небольшим JSON-объектом."
  cleaned = {}
  for key, item in value.items():
    if not isinstance(key, str) or not key or len(key) > 40:
      return None, "Проверьте название параметра узла."
    if item is None or isinstance(item, bool):
      cleaned[key] = item
    elif isinstance(item, str) and len(item) <= 200:
      cleaned[key] = item
    elif isinstance(item, (int, float)) and not isinstance(item, bool) and _finite(item):
      cleaned[key] = item
    else:
      return None, "Параметры узла допускают только короткий текст и конечные числа."
  return cleaned, None


@anvil.server.callable(require_user=True)
def create_system_for_project(project_id, system_type, title):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный идентификатор проекта."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден."}
  if not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  if not isinstance(system_type, str) or system_type not in dict(SYSTEM_TYPES):
    return {"ok": False, "message": "Выберите тип HVAC-системы."}
  title, error = _text(title, "Название системы", 120)
  if error:
    return {"ok": False, "message": error}
  title = title or ""
  now = datetime.now(timezone.utc)
  system = app_tables.systems.add_row(
    project=project, type=system_type, title=title, parameters={},
    status="draft", version="1", created_at=now, updated_at=now
  )
  Core.log_audit(
    actor=user, action="constructor.system_created",
    entity_type="system", entity_id=system.get_id(),
    details={"project": project["code"], "type": system_type},
    created_at=now
  )
  return {"ok": True, "system_id": system.get_id(), "message": "Система добавлена."}


@anvil.server.callable(require_user=True)
def get_system_graph(system_id):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(system_id, str) or not system_id:
    return {"ok": False, "message": "Некорректный идентификатор системы."}
  system = app_tables.systems.get_by_id(system_id)
  if system is None:
    return {"ok": False, "message": "Система не найдена."}
  project = system["project"]
  if not Core.can_access_project(project, user):
    return {"ok": False, "message": "Система недоступна этой учётной записи."}
  nodes = []
  node_rows = list(app_tables.system_components.search(
    q.fetch_only(
      "kind", "name", "quantity", "properties", "product", "product_snapshot",
      "position_x", "position_y", "parent",
      product=q.fetch_only("model", "sku", "updated_at",
                           brand=q.fetch_only("name"))
    ),
    order_by("sort_order"), system=system
  )[:MAX_NODES + 1])
  if len(node_rows) > MAX_NODES:
    return {"ok": False, "message": "Система превышает предел отображения в 200 узлов."}
  for row in node_rows:
    product = row["product"]
    snapshot = row["product_snapshot"] or {}
    brand = product["brand"] if product is not None else None
    product_label = snapshot.get("label", "")
    if not product_label and product is not None:
      product_label = "{} {}".format(
        brand["name"] if brand is not None else "",
        product["model"] or ""
      ).strip()
    elif product is None and product_label:
      product_label = "Снимок каталога: " + product_label
    parent = row["parent"]
    nodes.append({
      "id": row.get_id(), "kind": row["kind"], "name": row["name"],
      "quantity": row["quantity"], "properties": row["properties"] or {},
      "position_x": row["position_x"], "position_y": row["position_y"],
      "product_id": product.get_id() if product is not None else None,
      "product_label": product_label,
      "product_snapshot": snapshot,
      "parent_id": parent.get_id() if parent is not None else None
    })
  node_ids = {row.get_id() for row in node_rows}
  connections = []
  connection_rows = list(app_tables.system_connections.search(
    q.fetch_only(
      "type", "properties", "source_component", "target_component",
      source_component=q.fetch_only(), target_component=q.fetch_only()
    ),
    system=system
  )[:MAX_CONNECTIONS + 1])
  if len(connection_rows) > MAX_CONNECTIONS:
    return {"ok": False, "message": "Система превышает предел отображения в 400 связей."}
  for row in connection_rows:
    source = row["source_component"]
    target = row["target_component"]
    if source is not None and target is not None and (
      source.get_id() in node_ids and target.get_id() in node_ids
    ):
      connections.append({
        "source_id": source.get_id(), "target_id": target.get_id(),
        "type": row["type"], "properties": row["properties"] or {}
      })
  return {
    "ok": True,
    "system": {
      "id": system.get_id(), "title": system["title"],
      "type": system["type"], "version": system["version"] or "1",
      "project_id": system["project"].get_id()
    },
    "nodes": nodes, "connections": connections,
    "system_types": SYSTEM_TYPES,
    "node_kinds": [
      ("equipment", "Оборудование"), ("controller", "Контроллер"),
      ("sensor", "Датчик"), ("valve", "Клапан"), ("pump", "Насос"),
      ("route", "Трасса"), ("branch", "Ответвление"),
      ("group", "Группа"), ("other", "Другой узел")
    ],
    "connection_types": [
      ("refrigerant", "Хладагент"), ("duct", "Воздуховод"),
      ("cable", "Кабель"), ("drain", "Дренаж"),
      ("hydronic", "Гидравлика"), ("control", "Управление"),
      ("related", "Связь")
    ]
  }


@anvil.server.callable(require_user=True)
def save_system_graph(system_id, graph, expected_version):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(system_id, str) or not system_id or not isinstance(graph, dict):
    return {"ok": False, "message": "Проверьте данные системы."}
  try:
    graph_size = len(json.dumps(
      graph, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8"))
  except (TypeError, ValueError, OverflowError, RecursionError):
    return {"ok": False, "message": "Данные схемы должны быть корректным JSON-объектом."}
  if graph_size > MAX_GRAPH_BYTES:
    return {"ok": False, "message": "Схема превышает допустимый объём 512 КБ."}
  system = app_tables.systems.get_by_id(system_id)
  if system is None:
    return {"ok": False, "message": "Система не найдена."}
  if not Core.can_access_project(system["project"], user):
    return {"ok": False, "message": "Система недоступна этой учётной записи."}
  current_version = system["version"] or "1"
  if not isinstance(expected_version, str) or expected_version != current_version:
    return {"ok": False, "message": "Систему изменили в другой сессии. Загрузите её заново."}
  try:
    next_version = str(int(current_version) + 1)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Не удалось проверить версию схемы. Обновите систему."}
  nodes = graph.get("nodes")
  connections = graph.get("connections")
  if not isinstance(nodes, list) or len(nodes) > MAX_NODES:
    return {"ok": False, "message": "Система может содержать не более 200 узлов."}
  if not isinstance(connections, list) or len(connections) > MAX_CONNECTIONS:
    return {"ok": False, "message": "Система может содержать не более 400 связей."}

  current_rows = {
    row.get_id(): row
    for row in app_tables.system_components.search(system=system)[:MAX_NODES + 1]
  }
  if len(current_rows) > MAX_NODES:
    return {"ok": False, "message": "Система превышает предел изменения в 200 узлов."}
  node_ids = set()
  staged_nodes = []
  for node in nodes:
    if not isinstance(node, dict):
      return {"ok": False, "message": "Проверьте узлы системы."}
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id or len(node_id) > 100 or node_id in node_ids:
      return {"ok": False, "message": "В системе есть повторный или некорректный узел."}
    if node_id not in current_rows and not node_id.startswith("tmp-"):
      return {"ok": False, "message": "Узел не принадлежит этой системе. Загрузите систему заново."}
    node_ids.add(node_id)
    kind = node.get("kind")
    if not isinstance(kind, str) or kind not in NODE_KINDS:
      return {"ok": False, "message": "Выберите допустимый тип узла."}
    name, error = _text(node.get("name"), "Название узла", 120)
    if error:
      return {"ok": False, "message": error}
    quantity, error = _number(node.get("quantity"), "Количество", 0.000001, 1000000)
    if error:
      return {"ok": False, "message": error}
    x, error = _number(node.get("position_x"), "Положение X", -10000, 10000)
    if error:
      return {"ok": False, "message": error}
    y, error = _number(node.get("position_y"), "Положение Y", -10000, 10000)
    if error:
      return {"ok": False, "message": error}
    properties, error = _properties(node.get("properties", {}))
    if error:
      return {"ok": False, "message": error}
    parent_id = node.get("parent_id")
    if parent_id is not None and (not isinstance(parent_id, str) or parent_id == node_id):
      return {"ok": False, "message": "Некорректная вложенность групп."}
    product_id = node.get("product_id")
    product = None
    if product_id is not None:
      if not isinstance(product_id, str) or not product_id or len(product_id) > 100:
        return {"ok": False, "message": "Некорректная привязка товара."}
      product = app_tables.products.get_by_id(product_id)
      if product is None or not product["active"]:
        return {"ok": False, "message": "Выбранный товар больше не доступен."}
    staged_nodes.append({
      "id": node_id, "kind": kind, "name": name or "",
      "quantity": quantity, "x": x, "y": y, "properties": properties,
      "parent_id": parent_id, "product": product
    })
  nodes_by_id = {node["id"]: node for node in staged_nodes}
  for node in staged_nodes:
    parent_id = node["parent_id"]
    if parent_id is not None and (
      parent_id not in nodes_by_id
      or nodes_by_id[parent_id]["kind"] != "group"
      or node["kind"] == "group"
      or nodes_by_id[parent_id]["parent_id"] is not None
    ):
      return {"ok": False, "message": "Узел может входить только в одну группу."}

  staged_connections = []
  connection_keys = set()
  for connection in connections:
    if not isinstance(connection, dict):
      return {"ok": False, "message": "Проверьте связи системы."}
    source_id = connection.get("source_id")
    target_id = connection.get("target_id")
    connection_type = connection.get("type")
    if (
      not isinstance(source_id, str) or not isinstance(target_id, str)
      or not isinstance(connection_type, str)
      or
      source_id not in node_ids or target_id not in node_ids
      or source_id == target_id or connection_type not in CONNECTION_TYPES
    ):
      return {"ok": False, "message": "Связь ссылается на неизвестный узел или тип."}
    key = (source_id, target_id, connection_type)
    if key in connection_keys:
      return {"ok": False, "message": "В системе есть повторяющаяся связь."}
    connection_keys.add(key)
    properties, error = _properties(connection.get("properties", {}))
    if error:
      return {"ok": False, "message": error}
    staged_connections.append({
      "key": key, "source_id": source_id, "target_id": target_id,
      "type": connection_type, "properties": properties
    })

  existing_connection_rows = list(app_tables.system_connections.search(
    q.fetch_only("source_component", "target_component", "type", "properties"),
    system=system
  )[:MAX_CONNECTIONS + 1])
  if len(existing_connection_rows) > MAX_CONNECTIONS:
    return {"ok": False, "message": "Система превышает предел изменения в 400 связей."}

  now = datetime.now(timezone.utc)
  component_rows = {}
  for node in staged_nodes:
    row = current_rows.get(node["id"])
    product = node["product"]
    if product is None:
      snapshot = (row["product_snapshot"] or {}) if row is not None else {}
    elif row is not None and row["product"] is not None and (
      row["product"].get_id() == product.get_id()
    ):
      snapshot = row["product_snapshot"] or {}
    else:
      brand = product["brand"]
      snapshot = {
        "label": "{} {}".format(
          brand["name"] if brand is not None else "", product["model"]
        ).strip(),
        "model": product["model"], "sku": product["sku"] or "",
        "catalog_updated_at": (
          product["updated_at"].isoformat() if product["updated_at"] else ""
        )
      }
    values = {
      "system": system, "product": product, "kind": node["kind"],
      "name": node["name"], "quantity": node["quantity"],
      "properties": node["properties"], "product_snapshot": snapshot,
      "position_x": node["x"], "position_y": node["y"],
      "sort_order": node["y"] * 20000 + node["x"]
    }
    if row is None:
      row = app_tables.system_components.add_row(**values)
    else:
      row.update(**values)
    component_rows[node["id"]] = row
  for node in staged_nodes:
    row = component_rows[node["id"]]
    parent = component_rows.get(node["parent_id"]) if node["parent_id"] else None
    row["parent"] = parent

  existing_connections = {}
  for row in existing_connection_rows:
    source = row["source_component"]
    target = row["target_component"]
    if source is not None and target is not None:
      existing_connections[(source.get_id(), target.get_id(), row["type"])] = row
  wanted_keys = set()
  for connection in staged_connections:
    source = component_rows[connection["source_id"]]
    target = component_rows[connection["target_id"]]
    key = (source.get_id(), target.get_id(), connection["type"])
    wanted_keys.add(key)
    row = existing_connections.get(key)
    if row is None:
      app_tables.system_connections.add_row(
        system=system, source_component=source, target_component=target,
        type=connection["type"], properties=connection["properties"]
      )
    elif (row["properties"] or {}) != connection["properties"]:
      row["properties"] = connection["properties"]
  for key, row in existing_connections.items():
    if key not in wanted_keys:
      row.delete()
  for node_id, row in current_rows.items():
    if node_id not in node_ids:
      row.delete()

  version = next_version
  system.update(version=version, updated_at=now)
  Core.log_audit(
    actor=user, action="constructor.graph_saved", entity_type="system",
    entity_id=system_id,
    details={"nodes": len(staged_nodes), "connections": len(staged_connections),
             "version": version},
    created_at=now
  )
  return {"ok": True, "version": version, "message": "Схема системы сохранена."}
