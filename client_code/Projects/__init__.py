from ._anvil_designer import ProjectsTemplate
from anvil import handle
import anvil.server
import anvil.users
import json
from .. import Access


class Projects(ProjectsTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_user_form():
      return
    context = Access.get_session_context()
    self.compatibility_button.visible = (
      context["role_code"] == "admin" or "catalog.manage" in context["permissions"]
    )
    self._project_id = None
    self._room_id = None
    self._cursor_stack = []
    self._current_cursor = None
    self._next_cursor = None
    self.project_editor.visible = False
    self.engineering_lifecycle_panel.visible = False
    self.engineering_action_panel.visible = False
    self.engineering_decision_panel.visible = False
    self.engineering_control_button.visible = False
    self.project_calculation_button.visible = False
    self.rooms_panel.visible = False
    self.room_editor.visible = False
    self.save_project_button.enabled = True
    self.save_room_button.enabled = True
    self._load_page()

  def _load_page(self, cursor=None):
    self._current_cursor = cursor
    result = anvil.server.call(
      "get_projects_page", self.project_search_box.text or "", cursor
    )
    if not result["ok"]:
      self.project_rows.items = []
      self.next_button.visible = False
      self.projects_message.text = result["message"]
      return
    self.project_rows.items = result["rows"]
    self._next_cursor = result["next_cursor"]
    self.next_button.visible = result["has_more"]
    self.previous_button.visible = bool(self._cursor_stack)
    self.projects_message.text = "Проектов на странице: {}".format(len(result["rows"]))
    if not self.project_type_dropdown.items:
      self.project_type_dropdown.items = result["object_types"]
      self.project_status_dropdown.items = result["statuses"]
      self.system_type_dropdown.items = result["system_types"]
      self.engineering_profile_dropdown.items = [
        ("Комплексный HVAC-проект", "combined"),
        ("VRV / VRF", "vrv_vrf"),
        ("Вентиляция", "ventilation"),
        ("Сплит / мультисплит", "split_multi"),
      ]
      self.engineering_goal_dropdown.items = [
        ("Проектирование и подбор", "design"),
        ("Оптимизация существующей системы", "optimization"),
        ("Модернизация / замена", "modernization"),
        ("Расчёт стоимости и КП", "commercial"),
        ("Подготовка к монтажу", "installation"),
        ("Сервис и жизненный цикл", "service"),
      ]
      self.project_priority_dropdown.items = [
        ("Стандарт", "standard"),
        ("Сроки", "speed"),
        ("Экономия CAPEX", "capex"),
        ("Минимум OPEX", "opex"),
        ("Надёжность", "reliability"),
      ]

  def _start_project(self):
    self._project_id = None
    self._room_id = None
    self.project_editor.visible = True
    self.rooms_panel.visible = False
    self.systems_panel.visible = False
    self.room_editor.visible = False
    self.engineering_lifecycle_panel.visible = False
    self.engineering_control_button.visible = False
    self.project_code_label.text = "Новый проект"
    self.project_title_box.text = ""
    self.object_name_box.text = ""
    self.object_address_box.text = ""
    self.object_parameters_box.text = "{}"
    self.project_calculation_button.visible = False
    self.project_type_dropdown.selected_value = "other"
    self.engineering_profile_dropdown.selected_value = "combined"
    self.engineering_goal_dropdown.selected_value = "design"
    self.project_priority_dropdown.selected_value = "standard"
    self.object_constraints_box.text = ""
    self.project_status_dropdown.selected_value = "draft"
    self.project_message.text = ""

  def _open_project(self, project_id):
    result = anvil.server.call("get_project_workspace", project_id)
    if not result["ok"]:
      self.projects_message.text = result["message"]
      return
    project = result["project"]
    self._project_id = project["id"]
    self._room_id = None
    self.project_editor.visible = True
    self.project_calculation_button.visible = True
    self.rooms_panel.visible = True
    self.systems_panel.visible = True
    self.room_editor.visible = False
    self.project_code_label.text = project["code"]
    self.project_title_box.text = project["title"]
    self.object_name_box.text = project["object_name"]
    self.object_address_box.text = project["address"]
    self.object_parameters_box.text = json.dumps(
      project["object_parameters"], ensure_ascii=False, indent=2
    )
    self.project_type_dropdown.items = result["object_types"]
    self.project_type_dropdown.selected_value = project["object_type"]
    self.engineering_profile_dropdown.items = [
      ("Комплексный HVAC-проект", "combined"),
      ("VRV / VRF", "vrv_vrf"),
      ("Вентиляция", "ventilation"),
      ("Сплит / мультисплит", "split_multi"),
    ]
    self.engineering_goal_dropdown.items = [
      ("Проектирование и подбор", "design"),
      ("Оптимизация существующей системы", "optimization"),
      ("Модернизация / замена", "modernization"),
      ("Расчёт стоимости и КП", "commercial"),
      ("Подготовка к монтажу", "installation"),
      ("Сервис и жизненный цикл", "service"),
    ]
    self.project_priority_dropdown.items = [
      ("Стандарт", "standard"),
      ("Сроки", "speed"),
      ("Экономия CAPEX", "capex"),
      ("Минимум OPEX", "opex"),
      ("Надёжность", "reliability"),
    ]
    project_parameters = project["object_parameters"] or {}
    self.engineering_profile_dropdown.selected_value = project_parameters.get("engineering_profile") or "combined"
    self.engineering_goal_dropdown.selected_value = project_parameters.get("engineering_goal") or "design"
    self.project_priority_dropdown.selected_value = project_parameters.get("project_priority") or "standard"
    self.object_constraints_box.text = project_parameters.get("constraints", "") or ""
    self.project_status_dropdown.items = result["statuses"]
    self.project_status_dropdown.selected_value = project["status"]
    self.room_rows.items = result["rooms"]
    self.system_rows.items = result["systems"]
    self.project_message.text = ""
    self.engineering_lifecycle_panel.visible = True
    self.engineering_action_panel.visible = True
    self.engineering_control_button.visible = True
    self._load_engineering_snapshot()
    self._load_engineering_actions()
    self.engineering_decision_panel.visible = False
    self.engineering_decision_message.text = "Smart Selection запускается только по запросу, чтобы не нагружать проект при открытии."
    self.room_message.text = "Помещений: {}".format(len(result["rooms"]))

  def _project_parameters_with_profile(self):
    raw = self.object_parameters_box.text or "{}"
    try:
      parameters = json.loads(raw)
    except Exception:
      return raw
    if not isinstance(parameters, dict):
      return raw
    profile = self.engineering_profile_dropdown.selected_value or "combined"
    parameters["engineering_profile"] = profile
    parameters["engineering_goal"] = self.engineering_goal_dropdown.selected_value or "design"
    parameters["project_priority"] = self.project_priority_dropdown.selected_value or "standard"
    parameters["constraints"] = (self.object_constraints_box.text or "").strip()[:500]
    parameters["engineering_workflow_version"] = 2
    return json.dumps(parameters, ensure_ascii=False, separators=(",", ":"))

  def _save_project(self):
    self.save_project_button.enabled = False
    try:
      result = anvil.server.call(
        "save_project",
        {
          "title": self.project_title_box.text or "",
          "object_name": self.object_name_box.text or "",
          "object_type": self.project_type_dropdown.selected_value,
          "address": self.object_address_box.text or "",
          "object_parameters": self._project_parameters_with_profile(),
          "status": self.project_status_dropdown.selected_value
        },
        self._project_id
      )
    except Exception as exc:
      self.project_message.text = "Не удалось сохранить проект: {}".format(exc)
      return
    finally:
      self.save_project_button.enabled = True
    if not isinstance(result, dict):
      self.project_message.text = "Сервер вернул некорректный ответ при сохранении проекта."
      return
    self.project_message.text = result.get("message", "Проект сохранён." if result.get("ok") else "Проект не сохранён.")
    if result.get("ok"):
      self._project_id = result.get("project_id")
      if self._project_id:
        self._open_project(self._project_id)
      self._cursor_stack = []
      self._load_page()


  def _load_engineering_snapshot(self):
    if not self._project_id:
      return
    try:
      result = anvil.server.call("get_project_engineering_snapshot", self._project_id)
    except Exception as exc:
      self.engineering_stage_label.text = "Инженерный контур временно недоступен"
      self.engineering_stage_description.text = str(exc)
      return
    if not result.get("ok"):
      self.engineering_stage_label.text = "Инженерный контур недоступен"
      self.engineering_stage_description.text = result.get("message", "")
      return
    snapshot = result["snapshot"]
    self.engineering_stage_label.text = "{} · {}%".format(snapshot["stage_title"], snapshot["progress"])
    self.engineering_stage_description.text = snapshot["stage_description"]
    self.engineering_next_action_label.text = "Следующее действие: " + snapshot.get("next_action", "")
    risks = snapshot.get("risk_flags") or []
    self.engineering_risk_label.text = (
      "Риски / пробелы: " + " · ".join(risks)
      if risks else
      "Риски / пробелы: критических пропусков не обнаружено."
    )
    profile_titles = {
      "combined": "Комплексный HVAC",
      "vrv_vrf": "VRV / VRF",
      "ventilation": "Вентиляция",
      "split_multi": "Сплит / мультисплит"
    }
    self.engineering_score_label.text = "Engineering Score: {}/100 · {}".format(
      snapshot["engineering_score"],
      profile_titles.get(snapshot.get("engineering_profile"), "HVAC")
    )
    self.engineering_lifecycle_label.text = (
      "Объект {} · {} помещений · {} систем · {} компонентов · {} расчётов · {} смет · {} сервисных записей"
      .format(snapshot["object_name"] or "не задан", snapshot["room_count"], snapshot["system_count"],
              snapshot["system_component_count"], snapshot["calculation_count"], snapshot["estimate_count"],
              snapshot["service_count"])
    )
    families = snapshot.get("system_family_counts", {})
    self.engineering_lifecycle_label.text += " · VRV/VRF {} · вентиляция {} · сплит/мультисплит {}".format(
      families.get("VRV / VRF", 0), families.get("Вентиляция", 0), families.get("Кондиционирование", 0)
    )
    self.engineering_lifecycle_label.text += " · BOM {} · согласовано КП {} · монтаж {} · ПНР {} · сервис {}".format(
      snapshot.get("bom_line_count", 0),
      snapshot.get("approved_quote_count", 0),
      snapshot.get("installation_count", 0),
      snapshot.get("commissioning_completed_count", 0),
      snapshot.get("service_completed_count", 0)
    )

  def _load_engineering_actions(self):
    if not self._project_id:
      return
    try:
      result = anvil.server.call("get_project_action_center", self._project_id)
    except Exception as exc:
      self.engineering_action_rows.items = []
      self.engineering_action_message.text = "Маршрут действий временно недоступен: {}".format(exc)
      return
    if not result.get("ok"):
      self.engineering_action_rows.items = []
      self.engineering_action_message.text = result.get("message", "Маршрут действий недоступен.")
      return
    self.engineering_action_rows.items = result.get("actions", [])
    self.engineering_action_message.text = (
      "Engineering Score: {} · приоритетных действий: {}"
      .format(result.get("engineering_score", 0), len(result.get("actions", [])))
    )


  def _load_engineering_decision(self):
    if not self._project_id:
      return
    try:
      result = anvil.server.call("get_project_engineering_decisions", self._project_id)
    except Exception as exc:
      self.engineering_decision_panel.visible = True
      self.engineering_decision_message.text = "Smart Selection недоступен: {}".format(exc)
      self.engineering_decision_rows.items = []
      return
    if not result.get("ok"):
      self.engineering_decision_panel.visible = True
      self.engineering_decision_message.text = result.get("message", "Подбор недоступен.")
      self.engineering_decision_rows.items = []
      return
    labels = {"recommended": "RECOMMENDED · Рекомендация", "candidate": "CANDIDATE · Кандидат"}
    rows = []
    for system in result.get("systems", []):
      for item in system.get("candidates", []):
        candidate = dict(item)
        candidate["decision_label"] = "{} · {}".format(system.get("system_title", "Система"), labels.get(candidate.get("decision"), "Кандидат"))
        candidate["score_label"] = "Decision Score: {}/100".format(candidate.get("score", 0))
        capacity, target, unit = candidate.get("capacity"), candidate.get("target"), candidate.get("capacity_unit") or ""
        if capacity is not None and target is not None:
          candidate["capacity_label"] = "Ёмкость: {} {} · цель: {} {}".format(capacity, unit, target, unit)
        elif capacity is not None:
          candidate["capacity_label"] = "Ёмкость: {} {}".format(capacity, unit)
        else:
          candidate["capacity_label"] = "Структурированная ёмкость не найдена"
        candidate["readiness_label"] = ("Коммерчески готово · совместимость подтверждена" if candidate.get("price_ready") and candidate.get("compatible") else "Нужна цена · совместимость подтверждена" if candidate.get("compatible") else "Нужна инженерная проверка совместимости")
        candidate["reasons_label"] = "Почему: " + (" · ".join(candidate.get("reasons") or []) or "Недостаточно подтверждённых факторов.")
        candidate["warnings_label"] = "Контроль: " + (" · ".join(candidate.get("warnings") or []) or "Критических замечаний нет.")
        rows.append(candidate)
    self.engineering_decision_panel.visible = bool(rows or result.get("system_count"))
    self.engineering_decision_rows.items = rows
    self.engineering_decision_summary.text = "Инженерных систем: {} · кандидатов: {}".format(result.get("system_count", 0), len(rows))
    self.engineering_decision_message.text = result.get("message", "")

  def _start_room(self):
    self._room_id = None
    self.room_editor.visible = True
    self.room_name_box.text = ""
    self.room_area_box.text = ""
    self.room_height_box.text = ""
    self.room_parameters_box.text = "{}"
    self.room_message.text = ""

  def _edit_room(self, room_id, name, area, height, parameters):
    self._room_id = room_id
    self.room_editor.visible = True
    self.room_name_box.text = name
    self.room_area_box.text = str(area)
    self.room_height_box.text = str(height or "")
    self.room_parameters_box.text = json.dumps(
      parameters or {}, ensure_ascii=False, indent=2
    )

  def _save_room(self):
    self.save_room_button.enabled = False
    try:
      result = anvil.server.call(
        "save_room",
        self._project_id,
        {
          "name": self.room_name_box.text or "",
          "area": self.room_area_box.text or "",
          "height": self.room_height_box.text or "",
          "parameters": self.room_parameters_box.text or "{}"
        },
        self._room_id
      )
    except Exception as exc:
      self.room_message.text = "Не удалось сохранить помещение: {}".format(exc)
      return
    finally:
      self.save_room_button.enabled = True
    self.room_message.text = result["message"]
    if result["ok"]:
      self._open_project(self._project_id)

  def _create_system(self):
    result = anvil.server.call(
      "create_system_for_project",
      self._project_id,
      self.system_type_dropdown.selected_value,
      self.system_title_box.text or ""
    )
    self.system_message.text = result["message"]
    if result["ok"]:
      self._open_project(self._project_id)
      Access.open_window("Constructor", system_id=result["system_id"])

  @handle("project_calculation_button", "click")
  def project_calculation_button_click(self, **event_args):
    if self._project_id:
      Access.open_window("Calculations", project_id=self._project_id)

  @handle("engineering_control_button", "click")
  def engineering_control_button_click(self, **event_args):
    Access.open_admin_window("EngineeringControlRoom", window_title="Engineering Control Room")


  @handle("engineering_decision_load_button", "click")
  def engineering_decision_load_button_click(self, **event_args):
    self.engineering_decision_panel.visible = True
    self.engineering_decision_message.text = "Проверяю инженерные системы и фактические характеристики каталога…"
    self._load_engineering_decision()

  @handle("engineering_decision_rows", "x-apply-engineering-recommendation")
  def engineering_decision_apply_recommendation(self, system_id, product_id, **event_args):
    if not self._project_id or not system_id or not product_id:
      return
    try:
      result = anvil.server.call(
        "apply_engineering_recommendation",
        self._project_id, system_id, product_id
      )
      if not result.get("ok"):
        self.engineering_decision_message.text = result.get("message", "Рекомендацию не удалось применить.")
        return
      bom = anvil.server.call("generate_system_bom", system_id)
      if bom.get("ok"):
        self.engineering_decision_message.text = "Рекомендация применена · BOM сформирован. Система готова к смете."
      else:
        self.engineering_decision_message.text = (
          "Рекомендация применена, но BOM требует ручного запуска: " +
          bom.get("message", "проверьте состав системы.")
        )
      self._load_engineering_snapshot()
      self._load_engineering_actions()
      self._load_engineering_decision()
    except Exception as exc:
      self.engineering_decision_message.text = "Не удалось применить рекомендацию: {}".format(exc)

  @handle("system_rows", "x-engineering-decision")
  def system_rows_engineering_decision(self, system_id, **event_args):
    if not self._project_id or not system_id:
      return
    try:
      result = anvil.server.call("get_engineering_decision", self._project_id, system_id)
    except Exception as exc:
      self.engineering_decision_panel.visible = True
      self.engineering_decision_message.text = "Smart Selection недоступен: {}".format(exc)
      return
    if not result.get("ok"):
      self.engineering_decision_panel.visible = True
      self.engineering_decision_message.text = result.get("message", "Подбор недоступен.")
      return
    rows = []
    for item in result.get("candidates", [])[:12]:
      candidate = dict(item)
      candidate["system_id"] = system_id
      candidate["decision_label"] = "SELECTED SYSTEM · {}".format(candidate.get("decision", "candidate").upper())
      candidate["score_label"] = "Decision Score: {}/100 · Confidence: {}%".format(candidate.get("score", 0), candidate.get("confidence", 0))
      capacity, target, unit = candidate.get("capacity"), candidate.get("target"), candidate.get("capacity_unit") or ""
      candidate["capacity_label"] = ("Ёмкость: {} {} · цель: {} {}".format(capacity, unit, target, unit) if capacity is not None and target is not None else "Ёмкость: {} {}".format(capacity, unit) if capacity is not None else "Структурированная ёмкость не найдена")
      candidate["readiness_label"] = ("VALIDATED · цена и совместимость подтверждены" if candidate.get("decision_state") == "validated" and candidate.get("price_ready") and candidate.get("compatible") else "REVIEW · требуется инженерная проверка")
      candidate["reasons_label"] = "Почему: " + (" · ".join(candidate.get("reasons") or []) or "Недостаточно подтверждённых факторов.")
      candidate["warnings_label"] = "Контроль: " + (" · ".join(candidate.get("warnings") or []) or "Критических замечаний нет.")
      rows.append(candidate)
    self.engineering_decision_panel.visible = True
    self.engineering_decision_rows.items = rows
    self.engineering_decision_summary.text = "Выбрана система · кандидатов: {} · confidence: {}% · статус: {}".format(len(rows), result.get("selection_confidence", 0), result.get("selection_state", "review").upper())
    self.engineering_decision_message.text = result.get("message", "")

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("catalog_button", "click")
  def catalog_button_click(self, **event_args):
    Access.open_window("Catalog")

  @handle("calculations_button", "click")
  def calculations_button_click(self, **event_args):
    Access.open_window("Calculations")

  @handle("compatibility_button", "click")
  def compatibility_button_click(self, **event_args):
    Access.open_window("Compatibility")

  @handle("new_project_button", "click")
  def new_project_button_click(self, **event_args):
    self._start_project()

  @handle("project_search_button", "click")
  def project_search_button_click(self, **event_args):
    self._cursor_stack = []
    self._load_page()

  @handle("project_rows", "x-project-open")
  def project_rows_project_open(self, project_id, **event_args):
    self._open_project(project_id)

  @handle("save_project_button", "click")
  def save_project_button_click(self, **event_args):
    self._save_project()

  @handle("cancel_project_button", "click")
  def cancel_project_button_click(self, **event_args):
    self.project_editor.visible = False
    self.rooms_panel.visible = False

  @handle("add_room_button", "click")
  def add_room_button_click(self, **event_args):
    self._start_room()

  @handle("save_room_button", "click")
  def save_room_button_click(self, **event_args):
    self._save_room()

  @handle("cancel_room_button", "click")
  def cancel_room_button_click(self, **event_args):
    self.room_editor.visible = False

  @handle("room_rows", "x-room-edit")
  def room_rows_room_edit(self, room_id, name, area, height, parameters, **event_args):
    self._edit_room(room_id, name, area, height, parameters)

  @handle("room_rows", "x-room-changed")
  def room_rows_room_changed(self, **event_args):
    self._open_project(self._project_id)

  @handle("create_system_button", "click")
  def create_system_button_click(self, **event_args):
    self._create_system()

  @handle("next_button", "click")
  def next_button_click(self, **event_args):
    if self._next_cursor is None:
      return
    self._cursor_stack.append(self._current_cursor)
    self._load_page(self._next_cursor)

  @handle("previous_button", "click")
  def previous_button_click(self, **event_args):
    if not self._cursor_stack:
      return
    cursor = self._cursor_stack.pop()
    self._load_page(cursor)
