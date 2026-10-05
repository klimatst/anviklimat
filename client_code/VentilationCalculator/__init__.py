from ._anvil_designer import VentilationCalculatorTemplate
from anvil import handle
from anvil.js.window import document
import anvil.server

from .. import Access


INPUT_NAMES = (
  "area_box", "length_box", "width_box", "height_box", "people_box",
  "air_changes_box", "required_flow_box", "equipment_capacity_box", "temperature_delta_box",
  "duct_length_box", "duct_diameter_box", "branches_box", "grilles_box",
  "diffusers_box", "fans_box", "recuperators_box", "filters_box",
  "silencers_box", "valves_box", "automation_box", "mounting_box",
  "additional_work_box"
)


class VentilationCalculator(VentilationCalculatorTemplate):
  """Independent ventilation estimator; formulas and prices live on the server."""

  def __init__(self, **properties):
    super().__init__(**properties)
    self._setup = anvil.server.call("get_ventilation_calculator_setup")
    self._ready = False
    self._manual_area = True
    self._equipment_label_defaults = {
      name: getattr(self, name).text for name in (
        "fans_label", "recuperators_label", "filters_label", "silencers_label",
        "valves_label", "grilles_label", "diffusers_label", "automation_label"
      )
    }
    self._result_schema = []
    self._result_options = self._setup.get("result_options", {})
    self.room_purpose_dropdown.items = self._setup["rooms"]
    self.system_type_dropdown.items = self._setup["systems"]
    self._custom_fields = sorted(
      (dict(field) for field in self._setup.get("custom_fields", [])),
      key=lambda field: (
        field.get("order", 0) if isinstance(field.get("order", 0), int)
        and not isinstance(field.get("order", 0), bool) else 0
      )
    )
    self.custom_field_rows.items = self._custom_fields
    self._apply_result_schema(self._setup.get("result_schema", []))
    self._apply_page_content(self._setup.get("content", {}))
    self._apply_field_labels(self._setup.get("labels", {}), self._setup.get("units", {}))
    self.room_purpose_dropdown.selected_value = (
      self._setup["rooms"][0][0] if self._setup["rooms"] else None
    )
    self.system_type_dropdown.selected_value = (
      self._setup["systems"][0][0] if self._setup["systems"] else None
    )
    self._set_defaults()
    self._apply_equipment_config()
    for name in INPUT_NAMES:
      if name in ("area_box", "length_box", "width_box"):
        continue
      getattr(self, name).set_event_handler("change", self._auto_calculate)
    self.area_box.set_event_handler("change", self._area_changed)
    self.length_box.set_event_handler("change", self._geometry_changed)
    self.width_box.set_event_handler("change", self._geometry_changed)
    self.room_purpose_dropdown.set_event_handler("change", self._auto_calculate)
    self.system_type_dropdown.set_event_handler("change", self._auto_calculate)
    self._ready = True
    self._calculate()

  def _set_defaults(self):
    defaults = self._setup["defaults"]
    for name, key in (
      ("area_box", "area"), ("length_box", "length"),
      ("width_box", "width"), ("height_box", "height"),
      ("people_box", "people"), ("air_changes_box", "air_changes"),
      ("temperature_delta_box", "temperature_delta"),
      ("equipment_capacity_box", "equipment_capacity"),
      ("duct_length_box", "duct_length"), ("duct_diameter_box", "duct_diameter"),
      ("branches_box", "branches"), ("grilles_box", "grilles"),
      ("diffusers_box", "diffusers"), ("fans_box", "fans"),
      ("recuperators_box", "recuperators"), ("filters_box", "filters"),
      ("silencers_box", "silencers"), ("valves_box", "valves"),
      ("automation_box", "automation"), ("mounting_box", "mounting"),
      ("additional_work_box", "additional_work")
    ):
      value = defaults.get(key, 0)
      getattr(self, name).text = str(value)
    self.required_flow_box.text = "0"

  def _auto_calculate(self, **event_args):
    if self._ready:
      self._calculate()

  def _area_changed(self, **event_args):
    if self._ready:
      self._manual_area = True
      self._calculate()

  def _geometry_changed(self, **event_args):
    if self._ready:
      self._manual_area = False
      self._sync_area_from_dimensions()
      self._calculate()

  def _sync_area_from_dimensions(self):
    try:
      length = float((self.length_box.text or "").strip().replace(",", "."))
      width = float((self.width_box.text or "").strip().replace(",", "."))
    except (TypeError, ValueError):
      self.area_box.text = ""
      return
    if not (0 < length <= 10000 and 0 < width <= 10000):
      self.area_box.text = ""
      return
    area = length * width
    if self._setup.get("units", {}).get("area") == "ft²":
      area /= 0.09290304
    self.area_box.text = "{:.2f}".format(area).rstrip("0").rstrip(".")

  def _collect_inputs(self):
    values = {}
    for name in INPUT_NAMES:
      key = name[:-4] if name.endswith("_box") else name
      values[key] = (getattr(self, name).text or "").strip().replace(",", ".")
    if not self._manual_area:
      values["area"] = "0"
    values["room_type"] = self.room_purpose_dropdown.selected_value
    values["ventilation_type"] = self.system_type_dropdown.selected_value
    values["custom_fields"] = {
      field.get("code"): field.get("value", field.get("default", ""))
      for field in self.custom_field_rows.items
      if isinstance(field, dict) and field.get("code")
    }
    return values

  def _apply_result_schema(self, schema):
    allowed = {
      "volume", "air_exchange", "supply", "exhaust", "fan", "duct",
      "cooling_capacity", "recovery_power", "equipment_cost",
      "installation_cost", "additional_cost", "total"
    }
    self._result_schema = []
    for item in schema:
      if not isinstance(item, dict) or item.get("key") not in allowed:
        continue
      self._result_schema.append(dict(item))
    self._result_schema.sort(key=lambda item: item.get("order", 0))
    total = next((item for item in self._result_schema if item["key"] == "total"), None)
    self.total_result.visible = total is not None and total.get("visible", True) is not False
    self.result_main_label.visible = self.total_result.visible
    if total is not None:
      self.result_main_label.text = str(total.get("label", "Ориентировочная итоговая стоимость"))

  def _apply_page_content(self, content):
    self.page_title.text = str(content.get("page_title", "Расчёт вентиляции"))
    self.ventilation_heading.text = str(content.get("page_title", "Профессиональный расчёт вентиляции"))
    self.ventilation_lede.text = str(content.get("page_description", ""))
    self.calculate_ventilation_button.text = str(content.get("primary_button", "Рассчитать стоимость"))
    self._formula_notes = str(content.get("formula_notes", "")).strip()
    seo_title = str(content.get("seo_title", "")).strip()
    if seo_title:
      document.title = "{} | ЭКО-Климат".format(seo_title)
    self._set_meta(
      'meta[name="description"]', "name", "description",
      str(content.get("seo_description", ""))
    )
    self._set_meta(
      'meta[name="keywords"]', "name", "keywords",
      str(content.get("seo_keywords", ""))
    )
    self._set_meta(
      'meta[property="og:title"]', "property", "og:title", seo_title
    )
    self._set_meta(
      'meta[property="og:description"]', "property", "og:description",
      str(content.get("seo_description", ""))
    )
    self.system_type_rows.items = [
      row for row in content.get("system_cards", []) if isinstance(row, dict)
    ]
    self.advantage_rows.items = [
      dict(row, index="{:02d}".format(index + 1))
      for index, row in enumerate(content.get("advantages", []))
      if isinstance(row, dict)
    ]
    self.process_rows.items = [
      dict(row, order=index + 1)
      for index, row in enumerate(content.get("process", []))
      if isinstance(row, dict)
    ]
    self.faq_rows.items = [row for row in content.get("faq", []) if isinstance(row, dict)]
    self.ventilation_image_rows.items = [
      row for row in content.get("images", []) if isinstance(row, (str, dict))
    ]
    self.ventilation_types_section.visible = content.get("show_types", True) is not False
    self.ventilation_advantages_section.visible = bool(self.advantage_rows.items)
    self.ventilation_process_section.visible = content.get("show_process", True) is not False
    self.ventilation_faq_section.visible = content.get("show_faq", True) is not False
    self.ventilation_media_section.visible = (
      content.get("show_media", True) is not False and bool(self.ventilation_image_rows.items)
    )

  @staticmethod
  def _set_meta(selector, key_attribute, key_value, content):
    element = document.querySelector(selector)
    if element is None:
      element = document.createElement("meta")
      element.setAttribute(key_attribute, key_value)
      if document.head is not None:
        document.head.appendChild(element)
    element.setAttribute("content", content)

  def _apply_field_labels(self, labels, units):
    self.area_label.text = "{}, {}".format(labels.get("area", "Площадь помещения"), units.get("area", "м²"))
    self.length_label.text = "{}, м".format(labels.get("length", "Длина помещения"))
    self.width_label.text = "{}, м".format(labels.get("width", "Ширина помещения"))
    self.height_label.text = "{}, м".format(labels.get("height", "Высота потолка"))
    self.people_label.text = "{}, чел.".format(labels.get("people", "Количество людей"))
    self.duct_length_label.text = "{}, м".format(labels.get("duct_length", "Длина воздуховодов"))
    self.branches_label.text = "{}, шт.".format(labels.get("branches", "Количество ответвлений"))
    flow_unit = units.get("flow", "м³/ч")
    self.required_flow_label.text = "Требуемый расход, {}".format(flow_unit)
    self.equipment_capacity_label.text = "Производительность оборудования, {}".format(flow_unit)

  def _apply_equipment_config(self):
    equipment = self._setup.get("equipment", {})
    controls = {
      "fan": ("fans_label", "fans_box"),
      "recovery": ("recuperators_label", "recuperators_box"),
      "filter": ("filters_label", "filters_box"),
      "silencer": ("silencers_label", "silencers_box"),
      "valve": ("valves_label", "valves_box"),
      "grille": ("grilles_label", "grilles_box"),
      "diffuser": ("diffusers_label", "diffusers_box"),
      "automation": ("automation_label", "automation_box")
    }
    for code, names in controls.items():
      enabled = equipment.get(code, {}).get("enabled", True) is not False
      label = getattr(self, names[0])
      field = getattr(self, names[1])
      label.text = self._equipment_label_defaults[names[0]]
      field.enabled = enabled
      if not enabled:
        field.text = "0"
        label.text = "{} · отключено администратором".format(label.text)

  @staticmethod
  def _whole(value):
    return "{:,.0f}".format(float(value)).replace(",", " ")

  @classmethod
  def _money(cls, value):
    return "{} ₽".format(cls._whole(value))

  @staticmethod
  def _kw(value):
    return "{:.2f}".format(float(value)).replace(".", ",")

  def _calculate(self):
    result = anvil.server.call("calculate_ventilation_estimate", self._collect_inputs())
    self.ventilation_result_panel.visible = bool(result.get("ok"))
    if not result.get("ok"):
      self.calculation_message.text = result.get("message", "Проверьте исходные данные.")
      return
    self.calculation_message.text = "Расчёт обновлён по текущим исходным данным."
    units = self._setup.get("units", {})
    show_units = self._result_options.get("show_units", True) is not False
    result_values = {
      "volume": result["volume"], "air_exchange": result["air_exchange"],
      "supply": result["supply"], "exhaust": result["exhaust"],
      "fan": result["fan"], "duct": result["duct_diameter"],
      "cooling_capacity": result["cooling_capacity_kw"],
      "recovery_power": result["recovery_power_kw"],
      "equipment_cost": result["equipment_cost"],
      "installation_cost": result["installation_cost"],
      "additional_cost": result["additional_cost"], "total": result["total"]
    }
    result_rows = []
    total_item = None
    for item in self._result_schema:
      if item.get("visible", True) is False:
        continue
      key = item["key"]
      if key == "total":
        total_item = item
        continue
      value = result_values[key]
      unit = str(item.get("unit", "")).strip()
      if key == "volume":
        target_unit = units.get("volume", unit or "м³")
        displayed = value * 35.3146667 if target_unit == "ft³" else value
        display_value = self._whole(displayed)
        unit = target_unit
      elif key in ("air_exchange", "supply", "exhaust", "fan"):
        target_unit = units.get("flow", unit or "м³/ч")
        displayed = value / 3.6 if target_unit == "л/с" else value
        display_value = self._whole(displayed)
        unit = target_unit
      elif key == "duct":
        target_unit = unit or "мм"
        diameter = result["duct_diameter"] / 10.0 if target_unit in ("см", "cm") else result["duct_diameter"]
        diameter_text = self._kw(diameter) if target_unit in ("см", "cm") else self._whole(diameter)
        size_unit = target_unit if show_units else ""
        area_unit = "см²" if show_units else ""
        display_value = "Ø {}{} · {} {}".format(
          diameter_text, (" " + size_unit) if size_unit else "",
          self._whole(result["duct_area"]), area_unit
        ).rstrip()
        unit = ""
      elif key in ("cooling_capacity", "recovery_power"):
        display_value = self._kw(value)
        unit = unit or "кВт"
      else:
        display_value = self._whole(value)
        unit = unit or "₽"
      if show_units and unit:
        display_value = "{} {}".format(display_value, unit)
      result_rows.append({
        "label": str(item.get("label", key)), "value": display_value,
        "order": item.get("order", 0)
      })
    self.metric_result_rows.items = result_rows
    if total_item is not None:
      total_value = self._whole(result["total"])
      if show_units:
        total_value = "{} {}".format(total_value, str(total_item.get("unit", "₽")) or "₽")
      self.total_result.text = total_value
      self.result_main_label.text = str(total_item.get("label", "Ориентировочная итоговая стоимость"))
    counts = result["counts"]
    self.counts_result.text = (
      "Ответвления: {} · решётки: {} · диффузоры: {} · вентиляторы: {} · "
      "рекуператоры: {} · охлаждающие блоки: {} · фильтры: {} · шумоглушители: {} · клапаны: {} · автоматика: {}"
    ).format(
      counts["branches"], counts["grilles"], counts["diffusers"], counts["fans"],
      counts["recuperators"], counts["cooling_units"], counts["filters"], counts["silencers"],
      counts["valves"], counts["automation"]
    )
    show_breakdown = self._result_options.get("show_breakdown", True) is not False
    show_prices = self._result_options.get("show_prices", True) is not False
    self.breakdown_heading.visible = show_breakdown
    self.breakdown_result.visible = show_breakdown
    if show_breakdown:
      self.breakdown_result.text = "\n".join(
        "{}: {}".format(row["label"], self._money(row["value"])) if show_prices
        else row["label"] for row in result["breakdown"]
      )
    context = result["context"]
    self.result_basis.text = (
      "{} · {} · кратность {} 1/ч. Расход выбран как большее значение "
      "по объёму помещения, людям и заданному расходу."
    ).format(context["room"], context["system"], context["air_changes"])
    if self._formula_notes:
      self.result_basis.text += " Формула: {}".format(self._formula_notes)
    if context.get("recovery_efficiency"):
      self.result_basis.text += " · расчётная эффективность рекуперации: {}%.".format(
        context["recovery_efficiency"]
      )

  @handle("calculate_ventilation_button", "click")
  def calculate_ventilation_button_click(self, **event_args):
    self._calculate()

  @handle("reset_ventilation_button", "click")
  def reset_ventilation_button_click(self, **event_args):
    self._ready = False
    self._manual_area = True
    self._set_defaults()
    self._apply_equipment_config()
    self._ready = True
    self._calculate()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("home_bottom_button", "click")
  def home_bottom_button_click(self, **event_args):
    Access.open_context_home()

  @handle("contact_button", "click")
  def contact_button_click(self, **event_args):
    Access.open_window("Contacts")

  @handle("portfolio_button", "click")
  def portfolio_button_click(self, **event_args):
    Access.open_window("Gallery")
