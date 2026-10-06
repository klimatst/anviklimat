from ._anvil_designer import InstallationCalculatorTemplate
from .. import Access
from anvil import handle
import anvil.server
import anvil.users


class InstallationCalculator(InstallationCalculatorTemplate):
  def __init__(self, project_id=None, **properties):
    super().__init__(**properties)
    self._project_id = project_id
    self._context_project_id = project_id
    self._project_cursor_stack = []
    self._current_project_cursor = None
    self._next_project_cursor = None
    self._ready = False
    self._updating_controls = False
    self._can_quote = False
    self._signed_in = anvil.users.get_user() is not None
    self._can_view_installer = False
    self._staff_estimate = False
    self._materials = []
    self._selected_materials = []
    self.profile_dropdown.items = [
      ("Кондиционеры", "ac"), ("VRV / VRF", "vrf_vrv"),
      ("Вентиляция", "ventilation")
    ]
    self.profile_dropdown.selected_value = "ac"
    self.profile_dropdown.visible = False
    self.complexity_dropdown.items = [
      ("Стандартный доступ", "standard"),
      ("Ограниченный доступ", "limited_access"),
      ("Высотные работы", "height_work")
    ]
    self.complexity_dropdown.selected_value = "standard"
    self.room_type_dropdown.items = anvil.server.call("get_hvac_calculation_setup")["room_types"]
    self.room_type_dropdown.selected_value = "apartment"
    self.floor_type_dropdown.items = [
      ("Обычный этаж", "regular"), ("Последний этаж / кровля", "top")
    ]
    self.floor_type_dropdown.selected_value = "regular"
    self.exposure_dropdown.items = [
      ("Тень", "shade"), ("Обычная инсоляция", "normal"),
      ("Высокая инсоляция", "high")
    ]
    self.exposure_dropdown.selected_value = "normal"
    self._set_defaults()
    self.save_installation_button.visible = self._signed_in
    self.create_installation_quote_button.visible = self._signed_in
    self.create_installation_quote_button.enabled = False
    self.installation_result_panel.visible = False
    self.vrf_install_fields.visible = False
    self.vent_install_fields.visible = False
    self._apply_profile_fields()
    self.material_price_status.text = "Цена и единица берутся из карточки товара каталога."
    options = anvil.server.call("get_installation_options")
    self._can_view_installer = bool(options.get("can_view_installer"))
    self._materials = options["materials"] if self._can_view_installer else []
    self.estimate_kind_dropdown.items = [
      ("Смета для заказчика", "customer"),
      ("Рабочая смета монтажника", "staff")
    ]
    self.estimate_kind_dropdown.selected_value = "customer"
    self.estimate_kind_dropdown.visible = False
    self.customer_estimate_label.visible = not self._can_view_installer
    self.estimate_kind_label.visible = self._can_view_installer
    self.customer_estimate_button.visible = self._can_view_installer
    self.staff_estimate_button.visible = self._can_view_installer
    self.staff_estimate_controls.visible = False
    self.staff_installation_inputs_panel.visible = False
    self.complexity_label.visible = False
    self.complexity_dropdown.visible = False
    self.discount_type_dropdown.items = [
      ("Скидка в процентах", "percent"),
      ("Скидка в рублях", "amount")
    ]
    self.discount_type_dropdown.selected_value = "percent"
    self.discount_value_box.text = "0"
    self.discount_type_dropdown.visible = self._can_view_installer
    self.discount_value_box.visible = self._can_view_installer
    self.create_installation_quote_button.visible = self._signed_in
    self.material_category_dropdown.items = [
      ("{} · {}".format(item["group_title"], item["title"]), item["code"])
      for item in self._materials
    ]
    if self._materials:
      self.material_category_dropdown.selected_value = self._materials[0]["code"]
      self._load_material_products()
    self._load_projects()
    self._bind_auto_calculation()
    self._sync_selector_buttons()
    self._ready = True
    self._calculate_installation()

  def _set_defaults(self):
    defaults = {
      "site_name_box": "Новый объект", "room_name_box": "Помещение 1",
      "area_box": "", "height_box": "", "people_box": "",
      "equipment_heat_box": "", "equipment_count_box": "",
      "route_length_box": "", "duct_length_box": "",
      "drain_length_box": "", "cable_length_box": "",
      "height_difference_box": "", "floor_count_box": "1",
      "wall_crossings_box": "", "bracket_count_box": "",
      "fastener_points_box": "", "sealant_units_box": "",
      "duct_fittings_box": "", "outlet_count_box": "",
      "valve_count_box": "", "consumables_units_box": "",
      "air_changes_box": "", "fresh_air_box": "",
      "air_velocity_box": "", "supply_balance_box": "",
      "exhaust_balance_box": "", "material_quantity_box": ""
    }
    for name, value in defaults.items():
      getattr(self, name).text = value

  def _bind_auto_calculation(self):
    names = (
      "site_name_box", "room_name_box", "area_box", "height_box",
      "people_box", "equipment_heat_box", "equipment_count_box",
      "route_length_box", "duct_length_box", "drain_length_box",
      "cable_length_box", "height_difference_box", "floor_count_box",
      "wall_crossings_box", "bracket_count_box", "fastener_points_box",
      "sealant_units_box", "duct_fittings_box", "outlet_count_box",
      "valve_count_box", "consumables_units_box", "air_changes_box",
      "fresh_air_box", "air_velocity_box", "supply_balance_box",
      "exhaust_balance_box", "discount_value_box", "room_type_dropdown", "floor_type_dropdown",
      "exposure_dropdown", "complexity_dropdown"
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

  def _inputs(self):
    keys = {
      "area_m2": self.area_box, "height_m": self.height_box,
      "people_count": self.people_box, "equipment_kw": self.equipment_heat_box,
      "equipment_count": self.equipment_count_box,
      "route_length_m": self.route_length_box,
      "duct_length_m": self.duct_length_box,
      "drain_length_m": self.drain_length_box,
      "cable_length_m": self.cable_length_box,
      "height_difference_m": self.height_difference_box,
      "floor_count": self.floor_count_box,
      "wall_crossings": self.wall_crossings_box,
      "bracket_count": self.bracket_count_box,
      "fastener_points": self.fastener_points_box,
      "sealant_units": self.sealant_units_box,
      "duct_fittings_count": self.duct_fittings_box,
      "outlet_count": self.outlet_count_box,
      "valve_count": self.valve_count_box,
      "consumables_units": self.consumables_units_box,
      "air_changes_per_hour": self.air_changes_box,
      "fresh_air_m3_h_person": self.fresh_air_box,
      "air_velocity_m_s": self.air_velocity_box,
      "supply_balance_pct": self.supply_balance_box,
      "exhaust_balance_pct": self.exhaust_balance_box
    }
    values = {key: component.text or "" for key, component in keys.items()}
    values.update({
      "site_name": self.site_name_box.text or "",
      "room_name": self.room_name_box.text or "",
      "room_type": self.room_type_dropdown.selected_value,
      "floor_type": self.floor_type_dropdown.selected_value,
      "exposure": self.exposure_dropdown.selected_value,
      "complexity": self.complexity_dropdown.selected_value
    })
    return values

  def _auto_calculate(self, **event_args):
    if self._ready and not self._updating_controls:
      self._calculate_installation()

  def _apply_profile_fields(self):
    ventilation = self.profile_dropdown.selected_value == "ventilation"
    can_edit_dimensions = self._staff_estimate
    for field_name in ("route_length", "drain_length", "bracket_count", "sealant_units"):
      getattr(self, field_name + "_label").visible = can_edit_dimensions and not ventilation
      getattr(self, field_name + "_box").visible = can_edit_dimensions and not ventilation
    for field_name in ("duct_length", "duct_fittings", "outlet_count", "valve_count"):
      getattr(self, field_name + "_label").visible = can_edit_dimensions and ventilation
      getattr(self, field_name + "_box").visible = can_edit_dimensions and ventilation
    self.vrf_install_fields.visible = (
      can_edit_dimensions and self.profile_dropdown.selected_value == "vrf_vrv"
    )
    self.vent_install_fields.visible = can_edit_dimensions and ventilation
    self.installation_dimensions_heading.visible = can_edit_dimensions

  def _sync_selector_buttons(self):
    active_profile = self.profile_dropdown.selected_value
    for code, button in (
      ("ac", self.ac_profile_button),
      ("vrf_vrv", self.vrf_profile_button),
      ("ventilation", self.ventilation_profile_button)
    ):
      button.role = "calculator-tab-active" if code == active_profile else "calculator-tab"
    active_estimate = self.estimate_kind_dropdown.selected_value
    self.customer_estimate_button.role = (
      "calculator-tab-active" if active_estimate == "customer" else "calculator-tab"
    )
    self.staff_estimate_button.role = (
      "calculator-tab-active" if active_estimate == "staff" else "calculator-tab"
    )
    self.customer_estimate_label.visible = not self._can_view_installer
    self.estimate_kind_label.visible = self._can_view_installer
    self.customer_estimate_button.visible = self._can_view_installer
    self.staff_estimate_button.visible = self._can_view_installer
    self.complexity_label.visible = self._staff_estimate
    self.complexity_dropdown.visible = self._staff_estimate

  def _load_material_products(self):
    code = self.material_category_dropdown.selected_value
    category = next((item for item in self._materials if item["code"] == code), None)
    products = category["products"] if category else []
    self._updating_controls = True
    try:
      self.material_product_dropdown.items = [
        (item["label"], item["id"]) for item in products
      ]
      self.material_product_dropdown.selected_value = products[0]["id"] if products else None
      self.add_material_button.enabled = bool(products)
      self.material_price_status.text = (
        "Цена берётся из каталога; без цены позиция не войдёт в КП."
        if products else
        "В этой категории пока нет материалов в каталоге. Добавьте товар в каталог."
      )
      self.material_quantity_box.text = self._suggested_material_quantity(category)
    finally:
      self._updating_controls = False

  def _suggested_material_quantity(self, category):
    if category is None:
      return "1"
    key = category["quantity_key"]
    inputs = self._last_result["inputs"] if getattr(self, "_last_result", None) else self._inputs()
    mapping = {
      "route": "route_length_m", "drain": "drain_length_m",
      "duct": "duct_length_m", "cable": "cable_length_m",
      "fasteners": "fastener_points", "brackets": "bracket_count",
      "sleeves": "wall_crossings", "sealant": "sealant_units",
      "fittings": "duct_fittings_count", "outlets": "outlet_count",
      "valves": "valve_count", "consumables": "consumables_units"
    }
    value = inputs.get(mapping.get(key, "equipment_count"), "1")
    if key == "route" and self.profile_dropdown.selected_value == "ventilation":
      value = "0"
    if key == "route" and self.profile_dropdown.selected_value != "ventilation":
      value = inputs["route_length_m"]
    return str(value)

  def _material_selections_for_server(self):
    return [{
      "category_code": row["category_code"],
      "product_id": row["product_id"],
      "quantity": row["quantity"]
    } for row in self._selected_materials]

  def _item_row(self, title, result, context):
    return {
      "title": title,
      "display_result": result,
      "display_version": "",
      "display_context": context,
      "created_at": ""
    }

  def _refresh_selected_materials(self):
    self.selected_material_rows.items = [
      self._item_row(
        row["category_title"], "{} {}".format(row["quantity"], row["unit"]),
        row["product_title"]
      ) for row in self._selected_materials
    ]

  def _calculate_installation(self, selected_equipment_id=None):
    if self._updating_controls:
      return
    selected_equipment_id = selected_equipment_id or self.equipment_dropdown.selected_value
    self._staff_estimate = bool(
      self._can_view_installer
      and self.estimate_kind_dropdown.selected_value == "staff"
    )
    self._sync_selector_buttons()
    self.staff_estimate_controls.visible = self._staff_estimate
    self.staff_installation_inputs_panel.visible = self._staff_estimate
    self.complexity_label.visible = self._staff_estimate
    self.complexity_dropdown.visible = self._staff_estimate
    self._apply_profile_fields()
    self.create_installation_quote_button.visible = (
      self._signed_in and not self._staff_estimate
    )
    self.calculate_installation_button.enabled = False
    try:
      if self._staff_estimate:
        result = anvil.server.call(
          "calculate_staff_installation", self.profile_dropdown.selected_value,
          self._inputs(), self._material_selections_for_server(), False,
          self.project_dropdown.selected_value, selected_equipment_id,
          self.discount_type_dropdown.selected_value or "percent",
          self.discount_value_box.text or "0"
        )
      else:
        result = anvil.server.call(
          "calculate_installation", self.profile_dropdown.selected_value,
          self._inputs(), [], False, self.project_dropdown.selected_value,
          selected_equipment_id
        )
    finally:
      self.calculate_installation_button.enabled = True
    if not result["ok"]:
      self.installation_result_panel.visible = False
      self.installation_message.text = result["message"]
      self._can_quote = False
      self.create_installation_quote_button.enabled = False
      return

    recommendations = result["equipment_recommendations"]
    self._updating_controls = True
    try:
      equipment_options = []
      for item in recommendations:
        price = "{} {}".format(item["price"], item["currency"]) if item["has_price"] else "цена не задана"
        equipment_options.append((
          "{} {} · {} {} · {}".format(
            item["brand"], item["model"], item["capacity"],
            item["capacity_unit"], price
          ), item["id"]
        ))
      ids = [value for _, value in equipment_options]
      chosen_id = selected_equipment_id if selected_equipment_id in ids else None
      if chosen_id is None and equipment_options:
        chosen_id = equipment_options[0][1]
      self.equipment_dropdown.items = equipment_options
      self.equipment_dropdown.selected_value = chosen_id
    finally:
      self._updating_controls = False
    returned = result.get("equipment")
    returned_id = returned["id"] if returned else None
    if returned_id != chosen_id:
      self._calculate_installation(chosen_id)
      return
    self._render_installation_result(result)

  def _render_installation_result(self, result):
    self._last_result = result
    self.installation_result_panel.visible = True
    self._can_quote = result["can_quote"]
    self.installation_design_value.text = "{} {}".format(
      round(result["design_value"], 3), result["design_unit"]
    )
    estimate_title = "рабочая смета монтажника" if self._staff_estimate else "смета для заказчика"
    self.installation_result_title.text = "{} · {}".format(estimate_title, result["profile_title"])
    self.installation_inputs_summary.text = (
      "{} · {} м² · высота {} м · {} ед. оборудования · трасса {} м · воздуховоды {} м · {} этаж(а)"
      .format(result["site_name"], result["inputs"]["area_m2"],
              result["inputs"]["height_m"], result["inputs"]["equipment_count"],
              result["inputs"]["route_length_m"], result["inputs"]["duct_length_m"],
              result["inputs"]["floor_count"])
    )
    self.equipment_summary.text = (
      "{} {} · {} {}".format(result["equipment"]["brand"], result["equipment"]["model"],
                             result["equipment"]["capacity"], result["equipment"]["capacity_unit"])
      if result["equipment"] else
      "Подходящее оборудование появится после импорта характеристик мощности в каталог."
    )
    lines = []
    if self._staff_estimate:
      for item in result["components"]:
        lines.append(self._item_row(
          item["label"], "{} {}".format(item["value"], item["unit"]),
          "Расчётная величина"
        ))
      for item in result["equipment_lines"] + result["work_lines"] + result["material_lines"]:
        unit_price = (
          "{} {} / {}".format(item["unit_price"], item.get("currency", result["currency"]), item["unit"])
          if item.get("unit_price") is not None else "Цена не задана в каталоге"
        )
        amount = (
          "{} {} · {} · {} {}".format(
            item["quantity"], item["unit"], unit_price,
            item["line_total"], item.get("currency", result["currency"])
          ) if item.get("line_total") is not None else
          "{} {} · {}".format(item["quantity"], item["unit"], unit_price)
        )
        lines.append(self._item_row(item["description"], amount, item.get("group_title", item["group"])))
      if result.get("catalog_discount_amount"):
        lines.append(self._item_row(
          "Скидка каталога · {}%".format(result.get("catalog_discount_percent", 0)),
          "{} {} · уже учтена в ценах выше".format(
            result["catalog_discount_amount"], result["currency"]
          ),
          "Экономия по каталогу"
        ))
      if result.get("additional_discount_amount"):
        lines.append(self._item_row(
          "Дополнительная скидка · {}%".format(result.get("additional_discount_percent", 0)),
          "−{} {}".format(result["additional_discount_amount"], result["currency"]),
          "Цена для заказчика"
        ))
    else:
      for item in result.get("customer_lines", []):
        amount = item.get("amount")
        amount_text = (
          "{} {}".format(amount, result["currency"])
          if amount is not None else "не рассчитано"
        )
        lines.append(self._item_row(item["description"], amount_text, "Стоимость для заказчика"))
    self.installation_result_rows.items = lines
    self.material_cost_value.text = (
      "{} {}".format(
        result["materials_cost"] if self._staff_estimate else result.get("equipment_cost"),
        result["currency"]
      )
      if (result.get("materials_cost") if self._staff_estimate else result.get("equipment_cost")) is not None
      else "не рассчитана"
    )
    self.work_cost_value.text = (
      "{} {}".format(result["labor_cost"], result["currency"])
      if result["labor_cost"] is not None else "не рассчитана"
    )
    self.installation_total_value.text = (
      "{} {}".format(result["total"], result["currency"])
      if result["total"] is not None else "Итог появится после заполнения цен каталога"
    )
    self.material_cost_label.text = (
      "Оборудование и материалы" if self._staff_estimate else "Оборудование после скидки"
    )
    discount_amount = result.get("catalog_discount_amount", 0.0) or 0.0
    discount_percent = result.get("catalog_discount_percent", 0.0) or 0.0
    additional_amount = result.get("additional_discount_amount", 0.0) or 0.0
    additional_percent = result.get("additional_discount_percent", 0.0) or 0.0
    self.installation_discount_value.text = (
      "Каталог: {}% · {} {} (учтена в ценах выше); дополнительная: {}% · {} {}".format(
        discount_percent, discount_amount, result["currency"],
        additional_percent, additional_amount, result["currency"]
      ) if self._staff_estimate else
      "Скидка каталога: {}% · {} {}".format(
        discount_percent, discount_amount, result["currency"]
      )
    )
    self.bill_heading.text = (
      "Рабочая ведомость · оборудование, материалы и работы"
      if self._staff_estimate else "Клиентская смета · цена и скидка"
    )
    self.installation_warnings.text = "\n".join(result["warnings"])
    self.installation_source.text = "Источник: {} · версия {}".format(
      result["source"], result["version"]
    )
    self.create_installation_quote_button.enabled = bool(
      self._signed_in and self.project_dropdown.selected_value and result["can_quote"]
    )
    self.installation_message.text = "Результат обновлён автоматически. Количества материалов можно изменить в блоке состава."

  def _report_text(self):
    from .. import ReportTools
    return ReportTools.calculation_report(self._last_result)

  @handle("download_report_button", "click")
  def download_report_button_click(self, **event_args):
    from .. import ReportTools
    ReportTools.download_report(self._report_text(), "eko-klimat-montazh.txt")

  @handle("email_report_button", "click")
  def email_report_button_click(self, **event_args):
    if not self._signed_in:
      Access.open_window("Profile", window_title="Войдите, чтобы отправить отчёт")
      return
    result = anvil.server.call(
      "email_my_hvac_report", "Смета монтажа", self._report_text(),
      self.email_recipient_box.text or ""
    )
    self.installation_message.text = result["message"]

  @handle("telegram_report_button", "click")
  def telegram_report_button_click(self, **event_args):
    from .. import ReportTools
    ReportTools.open_telegram_share("Смета монтажа", self._report_text())

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("calculations_button", "click")
  def calculations_button_click(self, **event_args):
    Access.open_window("Calculations", project_id=self.project_dropdown.selected_value)

  @handle("profile_dropdown", "change")
  def profile_dropdown_change(self, **event_args):
    self._sync_selector_buttons()
    self._calculate_installation()

  @handle("complexity_dropdown", "change")
  def complexity_dropdown_change(self, **event_args):
    self._auto_calculate(**event_args)

  @handle("estimate_kind_dropdown", "change")
  def estimate_kind_dropdown_change(self, **event_args):
    self._auto_calculate(**event_args)

  def _select_profile(self, profile):
    if profile == self.profile_dropdown.selected_value:
      return
    self._updating_controls = True
    try:
      self.profile_dropdown.selected_value = profile
    finally:
      self._updating_controls = False
    self._sync_selector_buttons()
    self._calculate_installation()

  def _select_estimate_kind(self, kind):
    if not self._can_view_installer or kind == self.estimate_kind_dropdown.selected_value:
      return
    self._updating_controls = True
    try:
      self.estimate_kind_dropdown.selected_value = kind
    finally:
      self._updating_controls = False
    self._sync_selector_buttons()
    self._calculate_installation()

  @handle("ac_profile_button", "click")
  def ac_profile_button_click(self, **event_args):
    self._select_profile("ac")

  @handle("vrf_profile_button", "click")
  def vrf_profile_button_click(self, **event_args):
    self._select_profile("vrf_vrv")

  @handle("ventilation_profile_button", "click")
  def ventilation_profile_button_click(self, **event_args):
    self._select_profile("ventilation")

  @handle("customer_estimate_button", "click")
  def customer_estimate_button_click(self, **event_args):
    self._select_estimate_kind("customer")

  @handle("staff_estimate_button", "click")
  def staff_estimate_button_click(self, **event_args):
    self._select_estimate_kind("staff")

  @handle("discount_type_dropdown", "change")
  def discount_type_dropdown_change(self, **event_args):
    self._auto_calculate(**event_args)

  @handle("calculate_installation_button", "click")
  def calculate_installation_button_click(self, **event_args):
    self._calculate_installation()

  @handle("equipment_dropdown", "change")
  def equipment_dropdown_change(self, **event_args):
    self._auto_calculate(**event_args)

  @handle("material_category_dropdown", "change")
  def material_category_dropdown_change(self, **event_args):
    self._load_material_products()

  @handle("add_material_button", "click")
  def add_material_button_click(self, **event_args):
    code = self.material_category_dropdown.selected_value
    product_id = self.material_product_dropdown.selected_value
    category = next((item for item in self._materials if item["code"] == code), None)
    product = next((item for item in category["products"] if item["id"] == product_id), None) if category else None
    if category is None or product is None:
      self.installation_message.text = "Выберите материал из соответствующей категории каталога."
      return
    quantity = self.material_quantity_box.text or ""
    selection = {
      "category_code": code, "category_title": category["title"],
      "product_id": product_id, "product_title": product["title"],
      "quantity": quantity, "unit": category["unit"]
    }
    existing = next((i for i, row in enumerate(self._selected_materials)
                     if row["category_code"] == code), None)
    if existing is None:
      self._selected_materials.append(selection)
    else:
      self._selected_materials[existing] = selection
    self._refresh_selected_materials()
    self._calculate_installation()

  @handle("remove_material_button", "click")
  def remove_material_button_click(self, **event_args):
    code = self.material_category_dropdown.selected_value
    self._selected_materials = [row for row in self._selected_materials
                                if row["category_code"] != code]
    self._refresh_selected_materials()
    self._calculate_installation()

  @handle("project_dropdown", "change")
  def project_dropdown_change(self, **event_args):
    self._project_id = self.project_dropdown.selected_value
    if self._ready:
      self._calculate_installation()

  @handle("project_next_button", "click")
  def project_next_button_click(self, **event_args):
    if self._next_project_cursor:
      self._project_cursor_stack.append(self._current_project_cursor)
      self._load_projects(self._next_project_cursor)

  @handle("project_previous_button", "click")
  def project_previous_button_click(self, **event_args):
    if self._project_cursor_stack:
      self._load_projects(self._project_cursor_stack.pop())

  @handle("save_installation_button", "click")
  def save_installation_button_click(self, **event_args):
    self.save_installation_button.enabled = False
    try:
      if self._staff_estimate:
        result = anvil.server.call(
          "calculate_staff_installation", self.profile_dropdown.selected_value,
          self._inputs(), self._material_selections_for_server(), True,
          self.project_dropdown.selected_value, self.equipment_dropdown.selected_value,
          self.discount_type_dropdown.selected_value or "percent",
          self.discount_value_box.text or "0"
        )
      else:
        result = anvil.server.call(
          "calculate_installation", self.profile_dropdown.selected_value,
          self._inputs(), [], True, self.project_dropdown.selected_value,
          self.equipment_dropdown.selected_value
        )
    finally:
      self.save_installation_button.enabled = self._signed_in
    self.installation_message.text = result.get("message", "Расчёт монтажа сохранён.")
    if result["ok"]:
      self._render_installation_result(result)
      self.installation_message.text = "Расчёт монтажа сохранён в истории."

  @handle("create_installation_quote_button", "click")
  def create_installation_quote_button_click(self, **event_args):
    project_id = self.project_dropdown.selected_value
    if not project_id:
      self.installation_message.text = "Выберите свой проект для создания КП."
      return
    self.create_installation_quote_button.enabled = False
    try:
      result = anvil.server.call(
        "create_installation_quote", self.profile_dropdown.selected_value,
        self._inputs(), self._material_selections_for_server(), project_id,
        self.equipment_dropdown.selected_value, self.quote_terms_box.text or ""
      )
    except Exception as exc:
      self.installation_message.text = "Не удалось создать предложение по монтажу: {}".format(exc)
      return
    finally:
      self.create_installation_quote_button.enabled = bool(
        self._signed_in and self._can_quote and project_id
      )
    self.installation_message.text = result.get("message", "")
