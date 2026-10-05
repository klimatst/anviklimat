from ._anvil_designer import ConstructorTemplate
from anvil import handle
import anvil.server
import anvil.users
import json
from .. import Access


class Constructor(ConstructorTemplate):
  def __init__(self, system_id=None, **properties):
    super().__init__(**properties)
    if not Access.require_user_form():
      return
    context = Access.get_session_context()
    permissions = set(context["permissions"])
    self.can_manage_engineering = (
      context["role_code"] == "admin"
      or "engineering.manage" in permissions
      or "projects.manage" in permissions
    )
    self.system_id = system_id
    self._project_id = None
    self._graph = {"nodes": [], "connections": []}
    self._system_version = None
    self._selected_id = None
    self._selected_ids = set()
    self._undo_stack = []
    self._redo_stack = []
    self._revision = 0
    self._zoom = 1.0
    self._pan_x = 0
    self._pan_y = 0
    self._products_by_id = {}
    self.node_editor.visible = False
    self.catalog_product_panel.visible = False
    self.connect_panel.visible = False
    self.disconnect_panel.visible = False
    self.engineering_panel.visible = self.can_manage_engineering
    self.bom_panel.visible = False
    self.undo_button.enabled = False
    self.redo_button.enabled = False
    self.save_graph_button.enabled = False
    self._load_graph()

  def _copy_graph(self, graph=None):
    graph = graph or self._graph
    return {
      "nodes": [
        dict(node, properties=dict(node.get("properties") or {}))
        for node in graph["nodes"]
      ],
      "connections": [
        dict(connection, properties=dict(connection.get("properties") or {}))
        for connection in graph["connections"]
      ]
    }

  def _remember(self):
    self._undo_stack.append(self._copy_graph())
    if len(self._undo_stack) > 20:
      self._undo_stack.pop(0)
    self._redo_stack = []
    self._set_dirty(True)

  def _set_dirty(self, dirty):
    self.save_graph_button.enabled = dirty
    self.undo_button.enabled = bool(self._undo_stack)
    self.redo_button.enabled = bool(self._redo_stack)

  def _find_node(self, node_id):
    return next((node for node in self._graph["nodes"] if node["id"] == node_id), None)

  def _node_label(self, node_id):
    node = self._find_node(node_id)
    return node["name"] if node else "Узел удалён"

  def _load_graph(self):
    if not isinstance(self.system_id, str) or not self.system_id:
      self.constructor_message.text = "Система проекта не выбрана."
      self.save_graph_button.enabled = False
      return
    result = anvil.server.call("get_system_graph", self.system_id)
    if not result["ok"]:
      self.constructor_message.text = result["message"]
      self.save_graph_button.enabled = False
      return
    self.system = result["system"]
    self._project_id = self.system["project_id"]
    self._system_version = self.system["version"]
    self._graph = {"nodes": result["nodes"], "connections": result["connections"]}
    self._undo_stack = []
    self._redo_stack = []
    self.page_title.text = self.system["title"]
    self.system_type_label.text = dict(result["system_types"]).get(
      self.system["type"], self.system["type"]
    )
    self.node_kind_dropdown.items = result["node_kinds"]
    self.node_kind_editor_dropdown.items = result["node_kinds"]
    self.connection_type_dropdown.items = result["connection_types"]
    self.zoom_label.text = "Масштаб: 100%"
    self._render_graph()
    self.constructor_message.text = "Версия системы: {}".format(self._system_version)
    self._set_dirty(False)

  def _render_graph(self):
    self.node_rows.items = [
      dict(node, selected=node["id"] in self._selected_ids)
      for node in self._graph["nodes"]
    ]
    self._refresh_connection_choices()
    canvas = self.system_canvas
    canvas.reset_transform()
    canvas.clear_rect(0, 0, canvas.get_width(), canvas.get_height())
    canvas.save()
    canvas.set_transform(self._zoom, 0, 0, self._zoom, self._pan_x, self._pan_y)
    positions = {
      node["id"]: (float(node.get("position_x") or 0), float(node.get("position_y") or 0))
      for node in self._graph["nodes"]
    }
    for connection in self._graph["connections"]:
      source = positions.get(connection["source_id"])
      target = positions.get(connection["target_id"])
      if source is None or target is None:
        continue
      canvas.begin_path()
      canvas.move_to(source[0] + 64, source[1] + 24)
      canvas.line_to(target[0] + 64, target[1] + 24)
      canvas.stroke()
    canvas.foreground = "#c8d1da"
    for node in self._graph["nodes"]:
      x = float(node.get("position_x") or 0)
      y = float(node.get("position_y") or 0)
      canvas.stroke_rect(x, y, 128, 48)
      if node["id"] == self._selected_id:
        canvas.stroke_rect(x - 3, y - 3, 134, 54)
      canvas.fill_text(node["name"][:20], x + 6, y + 19)
      canvas.fill_text(node["kind"], x + 6, y + 37)
    canvas.restore()
    self.zoom_label.text = "Масштаб: {}%".format(int(self._zoom * 100))

  def _refresh_connection_choices(self):
    nodes = self._graph["nodes"]
    selected_node = self._find_node(self._selected_id)
    targets = [
      (node["name"], node["id"]) for node in nodes
      if selected_node is None or node["id"] != selected_node["id"]
    ]
    self.target_node_dropdown.items = targets
    choices = []
    for index, connection in enumerate(self._graph["connections"]):
      choices.append((
        "{} → {} ({})".format(
          self._node_label(connection["source_id"]),
          self._node_label(connection["target_id"]),
          connection["type"]
        ),
        str(index)
      ))
    self.connection_dropdown.items = choices

  def _select_node(self, node_id):
    node = self._find_node(node_id)
    self._selected_id = node_id if node is not None else None
    self.node_editor.visible = node is not None
    if node is not None:
      self.node_name_box.text = node["name"]
      self.node_quantity_box.text = str(node["quantity"])
      self.node_x_box.text = str(node.get("position_x") or 0)
      self.node_y_box.text = str(node.get("position_y") or 0)
      self.node_properties_box.text = json.dumps(
        node.get("properties") or {}, ensure_ascii=False, sort_keys=True
      )
      self.node_kind_dropdown.selected_value = node["kind"]
      self.selected_product_label.text = node.get("product_label") or "Товар каталога не привязан"
      self.catalog_product_panel.visible = False
      self.node_message.text = ""
    self._render_graph()

  def _load_products(self):
    result = anvil.server.call(
      "search_catalog", self.product_search_box.text or "", None, None
    )
    if not result["ok"]:
      self.constructor_message.text = result["message"]
      self.product_dropdown.items = []
      return
    self._products_by_id = {item["id"]: item for item in result["rows"]}
    self.product_dropdown.items = [("Без привязки", None)] + [
      (
        "{} · {}".format(item["brand"], item["model"]),
        item["id"]
      )
      for item in result["rows"]
    ]
    self.product_message.text = (
      "Найдено товаров: {}. Уточните поиск, если нужной модели нет."
      .format(len(result["rows"]))
    )

  def _add_node(self):
    name = (self.new_node_name_box.text or "").strip()
    if not name:
      self.constructor_message.text = "Введите название узла."
      return
    self._remember()
    self._revision += 1
    node_id = "tmp-{}".format(self._revision)
    node = {
      "id": node_id,
      "kind": self.node_kind_dropdown.selected_value or "other",
      "name": name,
      "quantity": 1.0,
      "properties": {},
      "position_x": 60 + (len(self._graph["nodes"]) % 5) * 150,
      "position_y": 60 + (len(self._graph["nodes"]) // 5) * 90,
      "product_id": None,
      "product_label": "",
      "product_snapshot": {},
      "parent_id": None
    }
    self._graph["nodes"].append(node)
    self._selected_id = node_id
    self._selected_ids = {node_id}
    self.new_node_name_box.text = ""
    self._render_graph()
    self._select_node(node_id)

  def _save_node_properties(self):
    node = self._find_node(self._selected_id)
    if node is None:
      return
    try:
      properties = json.loads(self.node_properties_box.text or "{}")
    except ValueError:
      self.node_message.text = "Проверьте JSON параметров узла."
      return
    if not isinstance(properties, dict):
      self.node_message.text = "Параметры узла должны быть JSON-объектом."
      return
    name = (self.node_name_box.text or "").strip()
    if not name:
      self.node_message.text = "Введите название узла."
      return
    kind = self.node_kind_editor_dropdown.selected_value
    if kind is None:
      self.node_message.text = "Выберите тип узла."
      return
    try:
      quantity = float(str(self.node_quantity_box.text).replace(",", "."))
      position_x = float(str(self.node_x_box.text).replace(",", "."))
      position_y = float(str(self.node_y_box.text).replace(",", "."))
    except (TypeError, ValueError):
      self.node_message.text = "Проверьте количество и положение узла."
      return
    if not all(value == value and abs(value) != float("inf") for value in (quantity, position_x, position_y)):
      self.node_message.text = "Числовые параметры должны быть конечными."
      return
    if (
      node["name"] == name and node["kind"] == kind
      and node["quantity"] == quantity
      and node.get("position_x", 0) == position_x
      and node.get("position_y", 0) == position_y
      and (node.get("properties") or {}) == properties
    ):
      self.node_message.text = "Параметры узла не изменились."
      return
    self._remember()
    node["name"] = name
    node["kind"] = kind
    node["quantity"] = quantity
    node["position_x"] = position_x
    node["position_y"] = position_y
    node["properties"] = properties
    self.node_message.text = "Изменения узла подготовлены к сохранению."
    self._render_graph()

  def _delete_selected(self):
    node = self._find_node(self._selected_id)
    if node is None:
      return
    self._remember()
    if node["kind"] == "group":
      for child in self._graph["nodes"]:
        if child.get("parent_id") == node["id"]:
          child["parent_id"] = None
    self._graph["nodes"] = [
      item for item in self._graph["nodes"] if item["id"] != node["id"]
    ]
    self._graph["connections"] = [
      item for item in self._graph["connections"]
      if item["source_id"] != node["id"] and item["target_id"] != node["id"]
    ]
    self._selected_id = None
    self._selected_ids.discard(node["id"])
    self.node_editor.visible = False
    self._render_graph()

  def _duplicate_selected(self):
    node = self._find_node(self._selected_id)
    if node is None:
      return
    self._remember()
    self._revision += 1
    clone = {}
    clone.update(node)
    clone["properties"] = dict(node.get("properties") or {})
    clone["id"] = "tmp-{}".format(self._revision)
    clone["name"] = node["name"] + " (копия)"
    clone["position_x"] = float(node.get("position_x") or 0) + 30
    clone["position_y"] = float(node.get("position_y") or 0) + 30
    clone["parent_id"] = None
    self._graph["nodes"].append(clone)
    self._selected_id = clone["id"]
    self._selected_ids = {clone["id"]}
    self._render_graph()
    self._select_node(clone["id"])

  def _connect_nodes(self):
    if self._selected_id is None or self.target_node_dropdown.selected_value is None:
      self.constructor_message.text = "Выберите исходный и целевой узел."
      return
    key = (self._selected_id, self.target_node_dropdown.selected_value,
           self.connection_type_dropdown.selected_value)
    if any((item["source_id"], item["target_id"], item["type"]) == key
           for item in self._graph["connections"]):
      self.constructor_message.text = "Такая связь уже есть."
      return
    self._remember()
    self._graph["connections"].append({
      "source_id": key[0], "target_id": key[1], "type": key[2], "properties": {}
    })
    self._render_graph()

  def _disconnect_selected(self):
    value = self.connection_dropdown.selected_value
    if value is None:
      return
    index = int(value)
    if not 0 <= index < len(self._graph["connections"]):
      return
    self._remember()
    self._graph["connections"].pop(index)
    self._render_graph()

  def _edit_selected_connection(self):
    value = self.connection_dropdown.selected_value
    if value is None:
      self.connection_properties_box.text = "{}"
      return
    index = int(value)
    if 0 <= index < len(self._graph["connections"]):
      self.connection_properties_box.text = json.dumps(
        self._graph["connections"][index].get("properties") or {},
        ensure_ascii=False, sort_keys=True
      )

  def _save_connection_properties(self):
    value = self.connection_dropdown.selected_value
    if value is None:
      self.engineering_message.text = "Выберите связь."
      return
    try:
      properties = json.loads(self.connection_properties_box.text or "{}")
    except ValueError:
      self.engineering_message.text = "Проверьте JSON параметров связи."
      return
    if not isinstance(properties, dict):
      self.engineering_message.text = "Параметры связи должны быть JSON-объектом."
      return
    index = int(value)
    if not 0 <= index < len(self._graph["connections"]):
      return
    if (self._graph["connections"][index].get("properties") or {}) == properties:
      self.engineering_message.text = "Параметры связи не изменились."
      return
    self._remember()
    self._graph["connections"][index]["properties"] = properties
    self.engineering_message.text = "Параметры связи подготовлены к сохранению."

  def _check_compatibility(self):
    if not self._ensure_graph_saved():
      return
    result = anvil.server.call("validate_system_compatibility", self.system_id)
    if not result["ok"]:
      self.engineering_message.text = result["message"]
      return
    if result["issues"]:
      self.engineering_message.text = "Проверено товаров: {}. {}".format(
        result["checked_products"], " ".join(result["issues"])
      )
    else:
      self.engineering_message.text = (
        "Проверено товаров: {}. Явных нарушений в базе правил не найдено."
        .format(result["checked_products"])
      )

  def _check_routing(self):
    if not self._ensure_graph_saved():
      return
    result = anvil.server.call("calculate_system_routing", self.system_id)
    if not result["ok"]:
      self.engineering_message.text = result["message"]
      return
    totals = ", ".join(
      "{}: {} м".format(kind, round(length, 3))
      for kind, length in result["lengths_m"].items()
    ) or "Маршрутов нет"
    missing = " " + " ".join(result["missing"]) if result["missing"] else ""
    self.engineering_message.text = totals + missing

  def _load_bom(self):
    result = anvil.server.call("get_system_bom", self.system_id)
    if not result["ok"]:
      self.engineering_message.text = result["message"]
      self.bom_rows.items = []
      return
    self.bom_rows.items = result["rows"]

  def _generate_bom(self):
    if not self._ensure_graph_saved():
      return
    result = anvil.server.call("generate_system_bom", self.system_id)
    self.engineering_message.text = result["message"]
    if not result["ok"]:
      return
    self.bom_panel.visible = True
    self._load_bom()
    if result["warnings"]:
      self.engineering_message.text += " " + " ".join(result["warnings"])

  def _group_selected(self):
    selected = [
      node for node in self._graph["nodes"]
      if node["id"] in self._selected_ids and node["kind"] != "group"
      and node.get("parent_id") is None
    ]
    title = (self.group_name_box.text or "").strip()
    if len(selected) < 2 or not title:
      self.constructor_message.text = "Выберите не менее двух узлов и назовите группу."
      return
    self._remember()
    self._revision += 1
    group_id = "tmp-{}".format(self._revision)
    group_node = {
      "id": group_id, "kind": "group", "name": title, "quantity": 1.0,
      "properties": {}, "position_x": sum(node["position_x"] for node in selected) / len(selected),
      "position_y": sum(node["position_y"] for node in selected) / len(selected),
      "product_id": None, "product_label": "", "product_snapshot": {},
      "parent_id": None
    }
    self._graph["nodes"].append(group_node)
    for node in selected:
      node["parent_id"] = group_id
    self._selected_id = group_id
    self._selected_ids = {group_id}
    self.group_name_box.text = ""
    self._render_graph()
    self._select_node(group_id)

  def _ungroup_selected(self):
    group = self._find_node(self._selected_id)
    if group is None or group["kind"] != "group":
      self.constructor_message.text = "Выберите группу."
      return
    self._remember()
    for node in self._graph["nodes"]:
      if node.get("parent_id") == group["id"]:
        node["parent_id"] = None
    self._graph["nodes"] = [
      node for node in self._graph["nodes"] if node["id"] != group["id"]
    ]
    self._selected_id = None
    self._selected_ids.clear()
    self.node_editor.visible = False
    self._render_graph()

  def _apply_history(self, undo):
    source = self._undo_stack if undo else self._redo_stack
    target = self._redo_stack if undo else self._undo_stack
    if not source:
      return
    target.append(self._copy_graph())
    self._graph = source.pop()
    self._selected_id = None
    self._selected_ids.clear()
    self.node_editor.visible = False
    self._set_dirty(True)
    self._render_graph()

  def _ensure_graph_saved(self):
    if not self.save_graph_button.enabled:
      return True
    return self._save_graph()

  def _save_graph(self):
    if not self.save_graph_button.enabled:
      return True
    self.save_graph_button.enabled = False
    try:
      result = anvil.server.call(
        "save_system_graph", self.system_id, self._graph, self._system_version
      )
    finally:
      self.save_graph_button.enabled = True
    self.constructor_message.text = result["message"]
    if result["ok"]:
      self._load_graph()
    return result["ok"]

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Projects")

  @handle("add_node_button", "click")
  def add_node_button_click(self, **event_args):
    self._add_node()

  @handle("node_rows", "x-node-select")
  def node_rows_node_select(self, node_id, **event_args):
    self._select_node(node_id)

  @handle("node_rows", "x-node-toggle")
  def node_rows_node_toggle(self, node_id, selected, **event_args):
    if selected:
      self._selected_ids.add(node_id)
    else:
      self._selected_ids.discard(node_id)
    self._render_graph()

  @handle("save_node_button", "click")
  def save_node_button_click(self, **event_args):
    self._save_node_properties()

  @handle("delete_node_button", "click")
  def delete_node_button_click(self, **event_args):
    self._delete_selected()

  @handle("duplicate_node_button", "click")
  def duplicate_node_button_click(self, **event_args):
    self._duplicate_selected()

  @handle("group_button", "click")
  def group_button_click(self, **event_args):
    self._group_selected()

  @handle("ungroup_button", "click")
  def ungroup_button_click(self, **event_args):
    self._ungroup_selected()

  @handle("connect_button", "click")
  def connect_button_click(self, **event_args):
    self._connect_nodes()

  @handle("disconnect_button", "click")
  def disconnect_button_click(self, **event_args):
    self._disconnect_selected()

  @handle("connection_dropdown", "change")
  def connection_dropdown_change(self, **event_args):
    self._edit_selected_connection()

  @handle("save_connection_properties_button", "click")
  def save_connection_properties_button_click(self, **event_args):
    self._save_connection_properties()

  @handle("check_compatibility_button", "click")
  def check_compatibility_button_click(self, **event_args):
    self._check_compatibility()

  @handle("check_routing_button", "click")
  def check_routing_button_click(self, **event_args):
    self._check_routing()

  @handle("generate_bom_button", "click")
  def generate_bom_button_click(self, **event_args):
    self._generate_bom()

  @handle("show_connect_button", "click")
  def show_connect_button_click(self, **event_args):
    self.connect_panel.visible = not self.connect_panel.visible
    self.disconnect_panel.visible = False

  @handle("show_disconnect_button", "click")
  def show_disconnect_button_click(self, **event_args):
    self.disconnect_panel.visible = not self.disconnect_panel.visible
    self.connect_panel.visible = False

  @handle("undo_button", "click")
  def undo_button_click(self, **event_args):
    self._apply_history(True)

  @handle("redo_button", "click")
  def redo_button_click(self, **event_args):
    self._apply_history(False)

  @handle("save_graph_button", "click")
  def save_graph_button_click(self, **event_args):
    self._save_graph()

  @handle("zoom_in_button", "click")
  def zoom_in_button_click(self, **event_args):
    self._zoom = min(2.0, self._zoom + 0.1)
    self._render_graph()

  @handle("zoom_out_button", "click")
  def zoom_out_button_click(self, **event_args):
    self._zoom = max(0.5, self._zoom - 0.1)
    self._render_graph()

  @handle("pan_left_button", "click")
  def pan_left_button_click(self, **event_args):
    self._pan_x -= 40
    self._render_graph()

  @handle("pan_right_button", "click")
  def pan_right_button_click(self, **event_args):
    self._pan_x += 40
    self._render_graph()

  @handle("pan_up_button", "click")
  def pan_up_button_click(self, **event_args):
    self._pan_y -= 40
    self._render_graph()

  @handle("pan_down_button", "click")
  def pan_down_button_click(self, **event_args):
    self._pan_y += 40
    self._render_graph()

  @handle("search_products_button", "click")
  def search_products_button_click(self, **event_args):
    self._load_products()

  @handle("show_products_button", "click")
  def show_products_button_click(self, **event_args):
    self.catalog_product_panel.visible = not self.catalog_product_panel.visible
    if self.catalog_product_panel.visible:
      self._load_products()

  @handle("bind_product_button", "click")
  def bind_product_button_click(self, **event_args):
    node = self._find_node(self._selected_id)
    if node is None:
      return
    product_id = self.product_dropdown.selected_value
    if node.get("product_id") == product_id:
      return
    self._remember()
    node["product_id"] = product_id
    product = self._products_by_id.get(product_id) if product_id else None
    node["product_label"] = (
      "{} {}".format(product["brand"], product["model"])
      if product is not None else ""
    )
    self.selected_product_label.text = node["product_label"] or "Товар каталога не привязан"
    self._render_graph()
