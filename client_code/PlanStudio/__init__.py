from ._anvil_designer import PlanStudioTemplate
from anvil import handle
import anvil.server
import anvil.users
import anvil.image
from .. import Access
import math
import uuid


TOOLS = [
  ("select", "Выбор"),
  ("room", "Помещение"),
  ("indoor", "Внутренний блок"),
  ("outdoor", "Наружный блок"),
  ("vrf", "VRF / VRV блок"),
  ("ahu", "Венткамера / AHU"),
  ("diffuser", "Решётка / диффузор"),
  ("vent", "Вентиляционный элемент"),
  ("drain", "Дренаж"),
  ("route_refrigerant", "Трасса хладагента"),
  ("route_duct", "Воздуховод"),
  ("route_cable", "Кабель"),
  ("route_hydronic", "Гидролиния"),
  ("note", "Примечание"),
  ("measure", "Измерение")
]


class PlanStudio(PlanStudioTemplate):
  def __init__(self, project_id=None, **properties):
    super().__init__(**properties)
    if not Access.require_user_form():
      return
    self.project_id = project_id
    self._plan = None
    self._settings = {"objects": [], "routes": [], "scale_m_per_px": 0.01}
    self._selected = None
    self._pending_route = []
    self._measure_points = []
    self._zoom = 1.0
    self._dirty = False
    self.tool_dropdown.items = TOOLS
    self.tool_dropdown.selected_value = "select"
    self.layer_dropdown.items = [
      ("Все слои", "all"), ("Архитектура", "architecture"),
      ("Оборудование", "equipment"), ("Трассы", "routes"), ("Примечания", "notes")
    ]
    self.layer_dropdown.selected_value = "all"
    self.grid_checkbox.checked = True
    self.snap_checkbox.checked = True
    self.system_dropdown.items = [("Без системы", None)]
    self.save_plan_button.enabled = False
    self._load()

  def _load(self):
    if not isinstance(self.project_id, str) or not self.project_id:
      self.plan_status.text = "Проект не выбран."
      return
    result = anvil.server.call("get_project_plan", self.project_id)
    if not result["ok"]:
      self.plan_status.text = result["message"]
      return
    self._plan = result.get("plan")
    if self._plan:
      self.plan_title.text = self._plan["title"]
      self.plan_name_box.text = self._plan["title"]
      self._settings = dict(self._plan.get("settings") or {})
      self._settings.setdefault("objects", [])
      self._settings.setdefault("routes", [])
      self._settings.setdefault("scale_m_per_px", 0.01)
      self.scale_box.text = str(self._settings["scale_m_per_px"])
      self.plan_status.text = "{} · {}".format(
        self._plan["file_name"], self._plan["content_type"]
      )
    else:
      self.plan_title.text = "План объекта"
      self.plan_status.text = "Загрузите PNG/JPG/WebP для визуальной подложки или PDF/DWG/DXF как исходный документ."
    self._load_systems()
    self._render()

  def _load_systems(self):
    if not self.project_id:
      return
    result = anvil.server.call("get_project_workspace", self.project_id)
    if result.get("ok"):
      self.system_dropdown.items = [("Без системы", None)] + [
        (row["title"], row["id"]) for row in result.get("systems", [])
      ]

  def _image_media(self):
    if not self._plan:
      return None
    media = self._plan.get("file")
    if media is None:
      return None
    return media if str(self._plan.get("content_type", "")).startswith("image/") else None

  def _snap(self, value):
    if not self.snap_checkbox.checked:
      return float(value)
    return round(float(value) / 10.0) * 10.0

  def _layer_for_object(self, obj):
    kind = obj.get("kind")
    if kind == "room":
      return "architecture"
    if kind == "note":
      return "notes"
    return "equipment"

  def _visible(self, layer):
    selected = self.layer_dropdown.selected_value or "all"
    return selected == "all" or selected == layer

  def _draw_grid(self, canvas):
    if not self.grid_checkbox.checked:
      return
    width, height = canvas.get_width(), canvas.get_height()
    step = max(10, int(20 * self._zoom))
    canvas.stroke_style = "rgba(110,140,155,0.16)"
    for x in range(0, int(width), step):
      canvas.begin_path(); canvas.move_to(x, 0); canvas.line_to(x, height); canvas.stroke()
    for y in range(0, int(height), step):
      canvas.begin_path(); canvas.move_to(0, y); canvas.line_to(width, y); canvas.stroke()

  def _render(self):
    canvas = self.plan_canvas
    canvas.reset_transform()
    canvas.clear_rect(0, 0, canvas.get_width(), canvas.get_height())
    canvas.save()
    canvas.scale(self._zoom, self._zoom)
    media = self._image_media()
    if media is not None:
      try:
        canvas.draw_image(media, 0, 0, canvas.get_width() / self._zoom, canvas.get_height() / self._zoom)
      except Exception:
        pass
    self._draw_grid(canvas)

    # Routes are drawn first so equipment sits above the engineering network.
    for route in self._settings.get("routes", []):
      if not self._visible("routes"):
        continue
      points = route.get("points") or []
      if len(points) < 2:
        continue
      canvas.stroke_style = {
        "route_refrigerant": "#24d4ed", "route_duct": "#f4b942",
        "route_cable": "#a5b0ba", "route_hydronic": "#5aa9ff"
      }.get(route.get("kind"), "#24d4ed")
      canvas.line_width = 4
      canvas.begin_path()
      canvas.move_to(points[0][0], points[0][1])
      for point in points[1:]:
        canvas.line_to(point[0], point[1])
      canvas.stroke()
      canvas.line_width = 1

    for obj in self._settings.get("objects", []):
      if not self._visible(self._layer_for_object(obj)):
        continue
      x, y = float(obj.get("x", 0)), float(obj.get("y", 0))
      selected = obj.get("id") == self._selected
      kind = obj.get("kind")
      if kind == "room":
        canvas.stroke_style = "rgba(36,212,237,0.75)"
        canvas.fill_style = "rgba(36,212,237,0.08)"
        canvas.fill_rect(x, y, obj.get("w", 180), obj.get("h", 100))
        canvas.stroke_rect(x, y, obj.get("w", 180), obj.get("h", 100))
        canvas.fill_style = "#e7f0f3"
        canvas.fill_text(obj.get("name", "Помещение")[:28], x + 8, y + 20)
      elif kind == "note":
        canvas.fill_style = "rgba(244,185,66,0.18)"
        canvas.fill_rect(x, y, 150, 44)
        canvas.stroke_style = "#f4b942"
        canvas.stroke_rect(x, y, 150, 44)
        canvas.fill_style = "#e7f0f3"
        canvas.fill_text(obj.get("name", "Примечание")[:22], x + 8, y + 25)
      else:
        canvas.fill_style = "#121a21"
        canvas.stroke_style = "#24d4ed" if kind in ("indoor", "vrf", "diffuser") else "#f4b942"
        canvas.begin_path()
        canvas.arc(x, y, 13, 0, math.pi * 2)
        canvas.fill()
        canvas.stroke()
        canvas.fill_style = "#e7f0f3"
        canvas.fill_text(obj.get("name", kind)[:18], x + 18, y + 4)
      if selected:
        canvas.stroke_style = "#ffffff"
        canvas.stroke_rect(x - 5, y - 5, 170 if kind in ("room", "note") else 30, 30 if kind not in ("room", "note") else (obj.get("h", 100) + 10))

    canvas.restore()
    self.zoom_label.text = "{}%".format(int(self._zoom * 100))
    self.stats_label.text = "Элементов: {} · трасс: {} · масштаб: {} м/пиксель".format(
      len(self._settings.get("objects", [])),
      len(self._settings.get("routes", [])),
      self._settings.get("scale_m_per_px", 0.01)
    )
    self.save_plan_button.enabled = self._dirty

  def _world_point(self, x, y):
    return self._snap(float(x) / self._zoom), self._snap(float(y) / self._zoom)

  def _hit(self, x, y):
    for obj in reversed(self._settings.get("objects", [])):
      ox, oy = float(obj.get("x", 0)), float(obj.get("y", 0))
      if obj.get("kind") == "room":
        if ox <= x <= ox + obj.get("w", 180) and oy <= y <= oy + obj.get("h", 100):
          return obj["id"]
      elif abs(x - ox) <= 18 and abs(y - oy) <= 18:
        return obj["id"]
    return None

  def _add_object(self, kind, x, y):
    name = (self.element_name_box.text or "").strip() or dict(TOOLS).get(kind, kind)
    obj = {
      "id": "obj-" + uuid.uuid4().hex[:10],
      "kind": kind, "name": name, "x": x, "y": y,
      "system_id": self.system_dropdown.selected_value
    }
    if kind == "room":
      obj.update({"w": 180, "h": 100, "room_id": None})
    self._settings.setdefault("objects", []).append(obj)
    self._selected = obj["id"]
    self._dirty = True

  def _add_route_point(self, kind, x, y):
    self._pending_route.append((x, y))
    if len(self._pending_route) < 2:
      self.tools_hint.text = "Точка 1 установлена. Кликните вторую точку трассы."
      return
    p1, p2 = self._pending_route[:2]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    scale = float(self._settings.get("scale_m_per_px") or 0.01)
    length = math.sqrt(dx * dx + dy * dy) * scale
    route = {
      "id": "route-" + uuid.uuid4().hex[:10],
      "kind": kind, "points": [list(p1), list(p2)],
      "system_id": self.system_dropdown.selected_value,
      "length_m": round(length, 3)
    }
    self._settings.setdefault("routes", []).append(route)
    self._selected = route["id"]
    self._pending_route = []
    self._dirty = True
    self.tools_hint.text = "Трасса создана: {:.2f} м. Можно продолжить следующую.".format(length)

  @handle("plan_file_loader", "change")
  def plan_file_loader_change(self, file, **event_args):
    if not self.project_id or file is None:
      return
    self.plan_status.text = "Загрузка {}…".format(file.name or "файла")
    result = anvil.server.call(
      "upload_project_plan", self.project_id, file,
      (self.plan_name_box.text or file.name or "План объекта")
    )
    if not result["ok"]:
      self.plan_status.text = result["message"]
      return
    self._plan = result["plan"]
    self.plan_title.text = self._plan["title"]
    self.plan_name_box.text = self._plan["title"]
    self.plan_status.text = result["message"]
    self._dirty = False
    self._render()
    self.plan_file_loader.clear()

  @handle("plan_canvas", "show")
  def plan_canvas_show(self, **event_args):
    self._render()

  @handle("plan_canvas", "mouse_down")
  def plan_canvas_mouse_down(self, x, y, button, keys, **event_args):
    if button != 1:
      return
    wx, wy = self._world_point(x, y)
    tool = self.tool_dropdown.selected_value or "select"
    if tool == "select":
      self._selected = self._hit(wx, wy)
      if self._selected and self._selected.startswith("route-"):
        for route in self._settings.get("routes", []):
          if route["id"] == self._selected:
            self.selection_label.text = "{} · {:.2f} м".format(
              route.get("kind"), route.get("length_m", 0)
            )
      else:
        selected = next((o for o in self._settings.get("objects", []) if o["id"] == self._selected), None)
        self.selection_label.text = selected.get("name", "Элемент") if selected else "Ничего не выбрано"
      self._render()
      return
    if tool.startswith("route_"):
      self._add_route_point(tool, wx, wy)
    elif tool == "measure":
      self._measure_points.append((wx, wy))
      if len(self._measure_points) == 2:
        p1, p2 = self._measure_points
        px = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
        scale = float(self._settings.get("scale_m_per_px") or 0.01)
        self.tools_hint.text = "Измерение: {:.2f} м ({} пикс.)".format(px * scale, round(px, 1))
        self._measure_points = []
    else:
      self._add_object(tool, wx, wy)
    self._render()

  @handle("save_plan_button", "click")
  def save_plan_button_click(self, **event_args):
    if not self.project_id:
      return
    result = anvil.server.call(
      "save_project_plan", self.project_id,
      {"title": self.plan_name_box.text or self.plan_title.text, "settings": self._settings}
    )
    self.plan_status.text = result["message"]
    if result["ok"]:
      self._dirty = False
      self._render()

  @handle("save_scale_button", "click")
  def save_scale_button_click(self, **event_args):
    try:
      scale = float(str(self.scale_box.text).replace(",", "."))
    except (TypeError, ValueError):
      self.plan_status.text = "Масштаб должен быть числом."
      return
    if scale <= 0:
      self.plan_status.text = "Масштаб должен быть больше нуля."
      return
    self._settings["scale_m_per_px"] = scale
    self._dirty = True
    self._render()

  @handle("delete_selected_button", "click")
  def delete_selected_button_click(self, **event_args):
    if not self._selected:
      return
    self._settings["objects"] = [o for o in self._settings.get("objects", []) if o["id"] != self._selected]
    self._settings["routes"] = [r for r in self._settings.get("routes", []) if r["id"] != self._selected]
    self._selected = None
    self.selection_label.text = "Ничего не выбрано"
    self._dirty = True
    self._render()

  @handle("clear_selection_button", "click")
  def clear_selection_button_click(self, **event_args):
    self._selected = None
    self._pending_route = []
    self._measure_points = []
    self.selection_label.text = "Ничего не выбрано"
    self._render()

  @handle("save_selected_button", "click")
  def save_selected_button_click(self, **event_args):
    if not self._selected:
      return
    for route in self._settings.get("routes", []):
      if route["id"] == self._selected:
        try:
          route["length_m"] = float(str(self.selected_length_box.text).replace(",", "."))
        except (TypeError, ValueError):
          self.plan_status.text = "Проверьте длину трассы."
          return
    self._dirty = True
    self._render()

  @handle("grid_checkbox", "change")
  def grid_checkbox_change(self, **event_args):
    self._render()

  @handle("snap_checkbox", "change")
  def snap_checkbox_change(self, **event_args):
    self._render()

  @handle("layer_dropdown", "change")
  def layer_dropdown_change(self, **event_args):
    self._render()

  @handle("zoom_in_button", "click")
  def zoom_in_button_click(self, **event_args):
    self._zoom = min(2.5, self._zoom + 0.1)
    self._render()

  @handle("zoom_out_button", "click")
  def zoom_out_button_click(self, **event_args):
    self._zoom = max(0.5, self._zoom - 0.1)
    self._render()

  @handle("back_button", "click")
  def back_button_click(self, **event_args):
    Access.open_window("Projects")

  @handle("open_constructor_button", "click")
  def open_constructor_button_click(self, **event_args):
    result = anvil.server.call("get_project_workspace", self.project_id)
    if result.get("ok") and result.get("systems"):
      Access.open_window("Constructor", system_id=result["systems"][0]["id"])
    else:
      self.plan_status.text = "Сначала создайте HVAC-систему проекта."

  @handle("open_calculations_button", "click")
  def open_calculations_button_click(self, **event_args):
    Access.open_window("Calculations", project_id=self.project_id)
