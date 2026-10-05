from ._anvil_designer import VentilationCalculatorTemplate
from anvil import handle
import anvil.server

from .. import Access


INPUT_NAMES = (
  "area_box", "length_box", "width_box", "height_box", "people_box",
  "air_changes_box", "required_flow_box", "equipment_capacity_box",
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
    self.room_purpose_dropdown.items = self._setup["rooms"]
    self.system_type_dropdown.items = self._setup["systems"]
    self._custom_fields = [dict(field) for field in self._setup.get("custom_fields", [])]
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
    for name in INPUT_NAMES:
      getattr(self, name).set_event_handler("change", self._auto_calculate)
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

  def _collect_inputs(self):
    values = {}
    for name in INPUT_NAMES:
      key = name[:-4] if name.endswith("_box") else name
      values[key] = (getattr(self, name).text or "").strip().replace(",", ".")
    values["room_type"] = self.room_purpose_dropdown.selected_value
    values["ventilation_type"] = self.system_type_dropdown.selected_value
    values["custom_fields"] = {
      field.get("code"): field.get("value", field.get("default", ""))
      for field in self.custom_field_rows.items
      if isinstance(field, dict) and field.get("code")
    }
    return values

  def _apply_result_schema(self, schema):
    labels = {
      "volume": self.volume_result, "air_exchange": self.exchange_result,
      "supply": self.supply_result, "exhaust": self.exhaust_result,
      "fan": self.fan_result, "duct": self.duct_result,
      "equipment_cost": self.equipment_result,
      "installation_cost": self.installation_result, "total": self.total_result
    }
    for item in schema:
      if not isinstance(item, dict) or item.get("key") not in labels:
        continue
      key = item["key"]
      labels[key].visible = item.get("visible", True) is not False
      unit = str(item.get("unit", "")).strip()
      if unit:
        if key in ("volume", "air_exchange", "supply", "exhaust", "fan"):
          labels[key].text = "—"

  def _apply_page_content(self, content):
    self.page_title.text = str(content.get("page_title", "Расчёт вентиляции"))
    self.ventilation_heading.text = str(content.get("page_title", "Профессиональный расчёт вентиляции"))
    self.ventilation_lede.text = str(content.get("page_description", ""))
    self.calculate_ventilation_button.text = str(content.get("primary_button", "Рассчитать стоимость"))

  def _apply_field_labels(self, labels, units):
    self.area_label.text = "{}, {}".format(labels.get("area", "Площадь помещения"), units.get("area", "м²"))
    self.length_label.text = "{}, м".format(labels.get("length", "Длина помещения"))
    self.width_label.text = "{}, м".format(labels.get("width", "Ширина помещения"))
    self.height_label.text = "{}, м".format(labels.get("height", "Высота потолка"))
    self.people_label.text = "{}, чел.".format(labels.get("people", "Количество людей"))
    self.duct_length_label.text = "{}, м".format(labels.get("duct_length", "Длина воздуховодов"))
    self.branches_label.text = "{}, шт.".format(labels.get("branches", "Количество ответвлений"))
    self.exchange_result.text = "— {}".format(units.get("flow", "м³/ч"))

  @staticmethod
  def _whole(value):
    return "{:,.0f}".format(float(value)).replace(",", " ")

  @classmethod
  def _money(cls, value):
    return "{} ₽".format(cls._whole(value))

  @classmethod
  def _flow(cls, value):
    return "{} м³/ч".format(cls._whole(value))

  def _calculate(self):
    result = anvil.server.call("calculate_ventilation_estimate", self._collect_inputs())
    self.ventilation_result_panel.visible = bool(result.get("ok"))
    if not result.get("ok"):
      self.calculation_message.text = result.get("message", "Проверьте исходные данные.")
      return
    self.calculation_message.text = "Расчёт обновлён по текущим исходным данным."
    self.volume_result.text = "{} м³".format(self._whole(result["volume"]))
    self.exchange_result.text = self._flow(result["air_exchange"])
    self.supply_result.text = self._flow(result["supply"])
    self.exhaust_result.text = self._flow(result["exhaust"])
    self.fan_result.text = self._flow(result["fan"])
    self.duct_result.text = "Ø {} мм · {} см²".format(
      result["duct_diameter"], self._whole(result["duct_area"])
    )
    self.rect_duct_result.text = result["duct_rect"]
    self.equipment_result.text = self._money(result["equipment_cost"])
    self.installation_result.text = self._money(result["installation_cost"])
    self.additional_result.text = self._money(result["additional_cost"])
    self.total_result.text = self._money(result["total"])
    counts = result["counts"]
    self.counts_result.text = (
      "Ответвления: {} · решётки: {} · диффузоры: {} · вентиляторы: {} · "
      "рекуператоры: {} · фильтры: {} · шумоглушители: {} · клапаны: {} · автоматика: {}"
    ).format(
      counts["branches"], counts["grilles"], counts["diffusers"], counts["fans"],
      counts["recuperators"], counts["filters"], counts["silencers"],
      counts["valves"], counts["automation"]
    )
    self.breakdown_result.text = "\n".join(
      "{}: {}".format(row["label"], self._money(row["value"]))
      for row in result["breakdown"]
    )
    context = result["context"]
    self.result_basis.text = (
      "{} · {} · кратность {} 1/ч. Расход выбран как большее значение "
      "по объёму помещения, людям и заданному расходу."
    ).format(context["room"], context["system"], context["air_changes"])

  @handle("calculate_ventilation_button", "click")
  def calculate_ventilation_button_click(self, **event_args):
    self._calculate()

  @handle("reset_ventilation_button", "click")
  def reset_ventilation_button_click(self, **event_args):
    self._ready = False
    self._set_defaults()
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
