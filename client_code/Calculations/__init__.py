from ._anvil_designer import CalculationsTemplate
from .. import Access
from anvil import handle
import anvil.server
import anvil.users
import json


PROFILES = [
  ("Кондиционеры", "ac"),
  ("VRV / VRF", "vrf_vrv")
]


class Calculations(CalculationsTemplate):
  def __init__(self, project_id=None, system_id=None, module_code=None, **properties):
    super().__init__(**properties)
    try:
      setup = anvil.server.call("get_hvac_calculation_setup")
    except Exception as exc:
      self._set_server_error("Не удалось загрузить настройки расчётов: {}".format(exc))
      return
    self._profile = "ac"
    self._project_id = project_id
    self._context_project_id = project_id
    self._project_cursor_stack = []
    self._current_project_cursor = None
    self._next_project_cursor = None
    self._system_id = system_id
    self._ready = False
    self._updating_controls = False
    self._can_quote = False
    self._history_loaded = False
    self._can_edit_formulas = setup["can_edit_formulas"]
    self._signed_in = setup["signed_in"]
    self._room_type_titles = {code: title for title, code in setup["room_types"]}
    self.profile_buttons = {
      "ac": self.ac_tab_button,
      "vrf_vrv": self.vrf_tab_button
    }
    self.room_type_dropdown.items = setup["room_types"]
    self.room_type_dropdown.selected_value = "apartment"
    self.floor_type_dropdown.items = setup["floor_types"]
    self.floor_type_dropdown.selected_value = "regular"
    self.exposure_dropdown.items = setup["exposures"]
    self.exposure_dropdown.selected_value = "normal"
    self._set_defaults()
    self.vrf_fields.visible = False
    self.formula_tools_panel.visible = False
    self.formula_tools_button.visible = self._can_edit_formulas
    self.history_panel.visible = False
    self.history_toggle_button.visible = self._signed_in
    self.save_calculation_button.visible = self._signed_in
    self.create_quote_button.visible = self._signed_in
    self.save_calculation_button.enabled = self._signed_in
    self.create_quote_button.enabled = False
    self._load_projects()
    self._bind_auto_calculation()
    if module_code in self.profile_buttons:
      self._set_profile(module_code, calculate=False)
    self._ready = True
    if properties.get("open_formula_editor") and self._can_edit_formulas:
      self.formula_tools_panel.visible = True
      try:
        self._load_admin_formulas(properties.get("formula_code"))
      except Exception as exc:
        self.formula_editor_message.text = "Не удалось открыть редактор формул: {}".format(exc)
    self._set_context_message()
    self._calculate_hvac()


  def _set_server_error(self, message):
    self.calculation_message.text = message
    self.result_panel.visible = False
    self.formula_tools_panel.visible = False

  def _set_defaults(self):
    defaults = {
      "room_name_box": "Помещение 1", "area_box": "", "height_box": "",
      "people_box": "", "equipment_heat_box": "",
      "indoor_units_box": "", "route_length_box": "",
      "height_difference_box": ""
    }
    for name, value in defaults.items():
      getattr(self, name).text = value

  def _bind_auto_calculation(self):
    names = (
      "room_name_box", "area_box", "height_box", "people_box",
      "equipment_heat_box", "indoor_units_box", "route_length_box",
      "height_difference_box",
      "room_type_dropdown", "floor_type_dropdown", "exposure_dropdown"
    )
    for name in names:
      getattr(self, name).set_event_handler("change", self._auto_calculate)

  def _load_projects(self, cursor=None):
    self.project_dropdown.items = [("Без проекта", None)]
    self.project_dropdown.selected_value = None
    if not self._signed_in:
      self.project_dropdown.enabled = False
      return
    result = anvil.server.call("get_projects_page", "", cursor)
    if not result["ok"]:
      self.project_status.text = result["message"]
      return
    options = [("{} · {}".format(row["code"], row["title"]), row["id"])
               for row in result["rows"]]
    option_ids = [value for _, value in options]
    selected_id = self.project_dropdown.selected_value or self._context_project_id
    if self._context_project_id and self._context_project_id not in option_ids:
      project = anvil.server.call("get_project_workspace", self._context_project_id)
      if project["ok"]:
        data = project["project"]
        options.insert(0, ("{} · {}".format(data["code"], data["title"]), data["id"]))
        option_ids.append(data["id"])
    self.project_dropdown.items = [("Без проекта", None)] + options
    if selected_id in option_ids:
      self.project_dropdown.selected_value = selected_id
    elif options:
      self.project_dropdown.selected_value = options[0][1]
    self._project_id = self.project_dropdown.selected_value
    self._context_project_id = None
    self._current_project_cursor = cursor
    self._next_project_cursor = result["next_cursor"]
    self.project_next_button.visible = result["has_more"]
    self.project_previous_button.visible = bool(self._project_cursor_stack)
    self.project_status.text = "Проектов на странице: {}. Используйте пагинацию для остальных.".format(len(result["rows"]))

  def _set_context_message(self):
    if self._system_id:
      self.calculation_context.text = "Результат будет связан с выбранной системой."
    elif self._project_id:
      self.calculation_context.text = "Результат будет связан с выбранным проектом."
    elif self._signed_in:
      self.calculation_context.text = "Расчёты доступны сразу. Выберите проект, чтобы сохранить результат и подготовить КП."
    else:
      self.calculation_context.text = "Расчёты доступны без входа. Войдите, чтобы сохранять результаты и создавать КП."

  def _set_profile(self, profile, calculate=True):
    self._profile = profile
    self.profile_title.text = dict((code, title) for title, code in PROFILES)[profile]
    self.vrf_fields.visible = profile == "vrf_vrv"
    for code, button in self.profile_buttons.items():
      button.role = "calculator-tab-active" if code == profile else "calculator-tab"
    self._set_context_message()
    if calculate and self._ready:
      self._calculate_hvac()

  def _inputs(self):
    inputs = {
      "room_name": self.room_name_box.text or "",
      "area_m2": self.area_box.text or "",
      "height_m": self.height_box.text or "",
      "people_count": self.people_box.text or "",
      "equipment_kw": self.equipment_heat_box.text or "",
      "room_type": self.room_type_dropdown.selected_value,
      "floor_type": self.floor_type_dropdown.selected_value,
      "exposure": self.exposure_dropdown.selected_value
    }
    if self._profile == "vrf_vrv":
      inputs.update({
        "indoor_unit_count": self.indoor_units_box.text or "",
        "route_length_m": self.route_length_box.text or "",
        "height_difference_m": self.height_difference_box.text or ""
      })
    return inputs

  def _auto_calculate(self, **event_args):
    if self._ready and not self._updating_controls:
      self._calculate_hvac()

  def _component_rows(self, rows, context):
    return [{
      "title": row["label"],
      "display_result": "{} {}".format(row["value"], row["unit"]).strip(),
      "display_version": "",
      "display_context": context,
      "created_at": ""
    } for row in rows]

  def _calculate_hvac(self, selected_product_id=None):
    if self._updating_controls:
      return
    selected_product_id = selected_product_id or self.product_dropdown.selected_value
    self.calculate_button.enabled = False
    try:
      result = anvil.server.call(
        "calculate_hvac_engine", self._profile, self._inputs(), False,
        self.project_dropdown.selected_value, selected_product_id
      )
    except Exception as exc:
      self.calculation_message.text = "Не удалось выполнить расчёт: {}".format(exc)
      self.result_panel.visible = False
      return
    finally:
      self.calculate_button.enabled = True
    if not result["ok"]
      self.result_panel.visible = False
      self.calculation_message.text = result["message"]
      self._can_quote = False
      self.create_quote_button.enabled = False
      return

    recommendations = result["recommendations"]
    self._updating_controls = True
    try:
      recommendation_options = []
      for item in recommendations:
        price = (
          "{} {}".format(item["price"], item["currency"])
          if item["has_price"] else "цена не задана"
        )
        recommendation_options.append((
          "{} {} · {} {} · {}".format(
            item["brand"], item["model"], item["capacity"],
            item["capacity_unit"], price
          ), item["id"]
        ))
      available_ids = [value for _, value in recommendation_options]
      chosen_id = selected_product_id if selected_product_id in available_ids else None
      if chosen_id is None and recommendation_options:
        chosen_id = recommendation_options[0][1]
      self.product_dropdown.items = recommendation_options
      self.product_dropdown.selected_value = chosen_id
    finally:
      self._updating_controls = False

    returned_product = result.get("selected_product")
    returned_id = returned_product["id"] if returned_product else None
    if returned_id != chosen_id:
      self._calculate_hvac(chosen_id)
      return
    self._render_hvac_result(result)

  def _render_hvac_result(self, result):
    self._last_result = result
    self.result_panel.visible = True
    self._can_quote = result["can_quote"]
    self.result_value.text = "{} {}".format(
      round(result["result"], 3), result["result_unit"]
    )
    btu_h = result.get("cooling_btu_h") if self._profile in ("ac", "vrf_vrv") else None
    self.result_capacity_btu.visible = btu_h is not None
    self.result_capacity_btu.text = (
      "{} BTU/ч".format(round(btu_h)) if btu_h is not None else ""
    )
    self.result_subtitle.text = result["profile_title"]
    self.result_rows.items = self._component_rows(
      result["components"], "Промежуточная составляющая"
    )
    inputs = result["inputs"]
    input_details = [
      "{} м² площадь".format(inputs["area_m2"]),
      "{} м высота".format(inputs["height_m"]),
      "{} чел.".format(inputs["people_count"]),
      "{} кВт тепловыделение".format(inputs["equipment_kw"]),
      "помещение: {}".format(self._room_type_titles.get(inputs["room_type"], inputs["room_type"]))
    ]
    profile_units = {
      "indoor_unit_count": ("внутренних блока", "шт."),
      "route_length_m": ("трасса", "м"), "height_difference_m": ("перепад высот", "м"),
    }
    for key, (label, unit) in profile_units.items():
      if key in inputs:
        input_details.append("{} {} {}".format(inputs[key], unit, label))
    self.result_inputs.text = "Исходные данные: " + " · ".join(input_details)
    extra = result.get("extra", {})
    line_parts = []
    if extra.get("route_length_m") is not None:
      line_parts.append("трасса {} м".format(extra["route_length_m"]))
    if extra.get("height_difference_m") is not None:
      line_parts.append("перепад {} м".format(extra["height_difference_m"]))
    if extra.get("liquid_pipe_diameter"):
      line_parts.append("жидкостная линия {}".format(extra["liquid_pipe_diameter"]))
    if extra.get("gas_pipe_diameter"):
      line_parts.append("газовая линия {}".format(extra["gas_pipe_diameter"]))
    if extra.get("additional_refrigerant_kg") is not None:
      line_parts.append("дозаправка {} кг".format(extra["additional_refrigerant_kg"]))
    self.refrigerant_line_detail.visible = self._profile in ("ac", "vrf_vrv")
    self.refrigerant_line_detail.text = (
      "Линейка холодильщика: " + " · ".join(line_parts)
      if line_parts else
      "Линейка холодильщика: размеры и дозаправка появятся только при наличии паспортных данных модели в каталоге."
    )
    recommendations = result["recommendations"]
    self.catalog_status.text = (
      "Оборудование подобрано по мощности из каталога проекта."
      if recommendations else
      "Подходящего оборудования с подтверждённой характеристикой мощности в каталоге нет."
    )
    self.recommendation_details.text = self._selected_product_summary(result)
    self.result_warning.text = "\n".join(result["warnings"])
    self.result_source.text = "Источник: {} · версия {}".format(
      result["source"], result["version"]
    )
    self.create_quote_button.enabled = bool(
      self._signed_in and self.project_dropdown.selected_value
      and result["can_quote"] and self.product_dropdown.selected_value
    )
    self.calculation_message.text = "Расчёт обновлён автоматически по текущим параметрам."

  def _selected_product_summary(self, result):
    product = result.get("selected_product")
    if not product:
      return "Подбор появится после импорта товаров с техническими характеристиками."
    price = "{} {}".format(product["price"], product["currency"]) if product["has_price"] else "Цена в каталоге не задана"
    return "{} {} · {} {} · {}".format(
      product["brand"], product["model"], product["capacity"],
      product["capacity_unit"], price
    )

  def _load_admin_formulas(self, selected_code=None):
    result = anvil.server.call("get_calculation_catalog", True)
    self._formula_catalog = result["formulas"]
    for formula in self._formula_catalog:
      formula["can_edit"] = True
      formula["state_title"] = "Включена" if formula["enabled"] else "Выключена"
    self.module_filter.items = [("Все модули", None)] + result["modules"]
    self.formula_rows.items = self._filtered_formulas()
    if selected_code:
      self._select_formula(selected_code)

  def _filtered_formulas(self):
    module = self.module_filter.selected_value
    return [item for item in self._formula_catalog
            if module is None or item["module"] == module]

  def _select_formula(self, code):
    formula = next((item for item in self._formula_catalog if item["code"] == code), None)
    if formula is None:
      return
    self.formula_editor.visible = True
    self.formula_code_box.text = formula["code"]
    self.formula_module_dropdown.items = anvil.server.call("get_calculation_catalog", True)["modules"]
    self.formula_module_dropdown.selected_value = formula["module"]
    self.formula_title_box.text = formula["title"]
    self.formula_expression_box.text = formula["expression"]
    self.input_schema_box.text = json.dumps(formula["input_schema"], ensure_ascii=False, indent=2)
    self.coefficients_box.text = json.dumps(formula["coefficients"], ensure_ascii=False, indent=2)
    self.output_unit_box.text = formula["output_unit"]
    self.source_box.text = formula["source"] or ""
    self.version_box.text = formula["version"] or ""
    self.formula_enabled_dropdown.items = [("Включена", True), ("Выключена", False)]
    self.formula_enabled_dropdown.selected_value = formula["enabled"]

  def _save_hvac(self):
    self.save_calculation_button.enabled = False
    try:
      result = anvil.server.call(
        "calculate_hvac_engine", self._profile, self._inputs(), True,
        self.project_dropdown.selected_value, self.product_dropdown.selected_value
      )
    except Exception as exc:
      self.calculation_message.text = "Не удалось сохранить расчёт: {}".format(exc)
      return
    finally:
      self.save_calculation_button.enabled = self._signed_in
    if not result["ok"]:
      self.calculation_message.text = result["message"]
      return
    self._render_hvac_result(result)
    self.calculation_message.text = "Расчёт сохранён в истории." \
      + (" ID: {}".format(result["calculation_id"]) if result.get("calculation_id") else "")
    if self._history_loaded:
      self._refresh_calculation_history()

  def _report_text(self):
    from .. import ReportTools
    return ReportTools.calculation_report(self._last_result)

  @handle("download_report_button", "click")
  def download_report_button_click(self, **event_args):
    from .. import ReportTools
    ReportTools.download_report(self._report_text(), "eko-klimat-raschet.txt")

  @handle("email_report_button", "click")
  def email_report_button_click(self, **event_args):
    if not self._signed_in:
      Access.open_window("Profile", window_title="Войдите, чтобы отправить отчёт")
      return
    result = anvil.server.call(
      "email_my_hvac_report", "Расчёт HVAC", self._report_text(),
      self.email_recipient_box.text or ""
    )
    self.calculation_message.text = result["message"]

  @handle("telegram_report_button", "click")
  def telegram_report_button_click(self, **event_args):
    from .. import ReportTools
    ReportTools.open_telegram_share("Расчёт HVAC", self._report_text())

  def _create_hvac_quote(self):
    if not self.project_dropdown.selected_value:
      self.calculation_message.text = "Выберите свой проект для создания КП."
      return
    self.create_quote_button.enabled = False
    try:
      result = anvil.server.call(
        "create_hvac_quote", self._profile, self._inputs(),
        self.project_dropdown.selected_value, self.product_dropdown.selected_value,
        self.quote_terms_box.text or ""
      )
    except Exception as exc:
      self.calculation_message.text = "Не удалось создать коммерческое предложение: {}".format(exc)
      return
    finally:
      self.create_quote_button.enabled = bool(
        self._signed_in and self._can_quote and self.project_dropdown.selected_value
        and self.product_dropdown.selected_value
      )
    self.calculation_message.text = result.get("message", "")
    if result["ok"]:
      if self._history_loaded:
        self._refresh_calculation_history()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("installation_button", "click")
  def installation_button_click(self, **event_args):
    Access.open_window("InstallationCalculator", project_id=self.project_dropdown.selected_value)

  @handle("refrigerant_ruler_button", "click")
  def refrigerant_ruler_button_click(self, **event_args):
    Access.open_window("RefrigerantRuler")

  @handle("ac_tab_button", "click")
  def ac_tab_button_click(self, **event_args):
    self._set_profile("ac")

  @handle("vrf_tab_button", "click")
  def vrf_tab_button_click(self, **event_args):
    self._set_profile("vrf_vrv")

  @handle("product_dropdown", "change")
  def product_dropdown_change(self, **event_args):
    self._auto_calculate(**event_args)

  @handle("project_dropdown", "change")
  def project_dropdown_change(self, **event_args):
    self._project_id = self.project_dropdown.selected_value
    self._set_context_message()
    if self._ready:
      self._calculate_hvac()

  @handle("project_next_button", "click")
  def project_next_button_click(self, **event_args):
    if self._next_project_cursor:
      self._project_cursor_stack.append(self._current_project_cursor)
      self._load_projects(self._next_project_cursor)

  @handle("project_previous_button", "click")
  def project_previous_button_click(self, **event_args):
    if self._project_cursor_stack:
      self._load_projects(self._project_cursor_stack.pop())

  @handle("calculate_button", "click")
  def calculate_button_click(self, **event_args):
    self._calculate_hvac()

  @handle("save_calculation_button", "click")
  def save_calculation_button_click(self, **event_args):
    self._save_hvac()

  @handle("create_quote_button", "click")
  def create_quote_button_click(self, **event_args):
    self._create_hvac_quote()

  @handle("formula_tools_button", "click")
  def formula_tools_button_click(self, **event_args):
    self.formula_tools_panel.visible = not self.formula_tools_panel.visible
    if self.formula_tools_panel.visible:
      self._load_admin_formulas()

  @handle("module_filter", "change")
  def module_filter_change(self, **event_args):
    self.formula_rows.items = self._filtered_formulas()

  @handle("formula_rows", "x-formula-edit")
  def formula_rows_formula_edit(self, code, **event_args):
    self._select_formula(code)

  @handle("new_formula_button", "click")
  def new_formula_button_click(self, **event_args):
    self.formula_editor.visible = True
    self.formula_code_box.text = ""
    self.formula_module_dropdown.items = anvil.server.call("get_calculation_catalog", True)["modules"]
    self.formula_module_dropdown.selected_value = "ac"
    self.formula_title_box.text = ""
    self.formula_expression_box.text = ""
    self.input_schema_box.text = "{}"
    self.coefficients_box.text = "{}"
    self.output_unit_box.text = ""
    self.source_box.text = ""
    self.version_box.text = ""
    self.formula_enabled_dropdown.items = [("Включена", True), ("Выключена", False)]
    self.formula_enabled_dropdown.selected_value = True

  @handle("save_formula_button", "click")
  def save_formula_button_click(self, **event_args):
    result = anvil.server.call(
      "save_formula", self.formula_code_box.text or "",
      self.formula_module_dropdown.selected_value, self.formula_title_box.text or "",
      self.formula_expression_box.text or "", self.input_schema_box.text or "{}",
      self.coefficients_box.text or "{}", self.output_unit_box.text or "",
      self.source_box.text or "", self.version_box.text or "",
      self.formula_enabled_dropdown.selected_value
    )
    self.formula_editor_message.text = result["message"]
    if result["ok"]:
      self.formula_editor.visible = False
      self._load_admin_formulas(result["code"])

  @handle("cancel_formula_button", "click")
  def cancel_formula_button_click(self, **event_args):
    self.formula_editor.visible = False

  @handle("history_refresh_button", "click")
  def history_refresh_button_click(self, **event_args):
    self._refresh_calculation_history()

  def _refresh_calculation_history(self):
    self.calculation_history.items = anvil.server.call("get_recent_calculations")
    self._history_loaded = True

  @handle("history_toggle_button", "click")
  def history_toggle_button_click(self, **event_args):
    is_open = not self.history_panel.visible
    self.history_panel.visible = is_open
    self.history_toggle_button.text = "Скрыть историю" if is_open else "Мои расчёты"
    if is_open and not self._history_loaded:
      self._refresh_calculation_history()
