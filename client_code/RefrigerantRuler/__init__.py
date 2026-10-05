from ._anvil_designer import RefrigerantRulerTemplate
from .. import Access
from anvil import handle
import anvil.server


class RefrigerantRuler(RefrigerantRulerTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._mode = "pressure"
    self._ready = False
    self._updating_controls = False
    initial = anvil.server.call(
      "calculate_refrigerant_ruler", "R600a", "pressure", "0", True
    )
    self.refrigerant_dropdown.items = [
      ("{} · {}".format(row["code"], row["name"]), row["code"])
      for row in initial.get("refrigerants", [])
    ]
    self.refrigerant_dropdown.selected_value = "R600a"
    self.pressure_input.text = "0"
    self.temperature_input.text = "0"
    self.pressure_input.set_event_handler("change", self._pressure_changed)
    self.temperature_input.set_event_handler("change", self._temperature_changed)
    self._ready = True
    self._show_result(initial)

  def _show_result(self, result):
    if not result["ok"]:
      self.ruler_message.text = result["message"]
      return
    self._updating_controls = True
    try:
      self.pressure_input.text = "{:.2f}".format(result["pressure_gauge_bar"])
      self.temperature_input.text = "{:.1f}".format(result["temperature_c"])
      pressure_slider = self.dom_nodes["pressure_slider"]
      pressure_slider.min = str(result["minimum_pressure_bar"])
      pressure_slider.max = str(result["maximum_pressure_bar"])
      pressure_slider.value = str(result["pressure_gauge_bar"])
      temperature_slider = self.dom_nodes["temperature_slider"]
      temperature_slider.min = str(result["minimum_temperature_c"])
      temperature_slider.max = str(result["maximum_temperature_c"])
      temperature_slider.value = str(result["temperature_c"])
    finally:
      self._updating_controls = False
    self.ruler_result_name.text = result["code"]
    self.ruler_pressure_value.text = "{:.2f} бар изб.".format(result["pressure_gauge_bar"])
    self.ruler_temperature_value.text = "{:.1f} °C".format(result["temperature_c"])
    self.ruler_absolute_pressure.text = (
      "Абсолютное давление: {:.2f} бар · {}".format(
        result["pressure_absolute_bar"], result["name"]
      )
    )
    self.refrigerant_info.text = "{} · Tкип {:.1f} °C".format(
      result["type"], result["boiling_point_c"]
    )
    self.ruler_limits.text = (
      "Рабочий диапазон линейки: {:.2f}…{:.2f} бар изб. · {:.1f}…{:.1f} °C".format(
        result["minimum_pressure_bar"], result["maximum_pressure_bar"],
        result["minimum_temperature_c"], result["maximum_temperature_c"]
      )
    )
    self.ruler_zone.text = "Зона: {}".format(result["zone"])
    self.ruler_critical_data.text = (
      "Критическая точка: {:.1f} °C · {:.1f} бар абс.".format(
        result["critical_temp_c"], result["critical_pressure_bar"]
      )
    )
    self.ruler_message.text = "Пересчёт выполнен автоматически."

  def _calculate(self, mode, value):
    if not self._ready or self._updating_controls:
      return
    self._mode = mode
    self.pressure_mode_button.role = (
      "calculator-tab-active" if mode == "pressure" else "calculator-tab"
    )
    self.temperature_mode_button.role = (
      "calculator-tab-active" if mode == "temperature" else "calculator-tab"
    )
    result = anvil.server.call(
      "calculate_refrigerant_ruler",
      self.refrigerant_dropdown.selected_value,
      mode,
      value
    )
    self._show_result(result)

  def _pressure_changed(self, **event_args):
    self._calculate("pressure", self.pressure_input.text or "")

  def _temperature_changed(self, **event_args):
    self._calculate("temperature", self.temperature_input.text or "")

  def pressure_slider_change(self, event):
    value = event.target.value
    self.pressure_input.text = value
    self._calculate("pressure", value)

  def temperature_slider_change(self, event):
    value = event.target.value
    self.temperature_input.text = value
    self._calculate("temperature", value)

  @handle("refrigerant_dropdown", "change")
  def refrigerant_dropdown_change(self, **event_args):
    if not self._ready or self._updating_controls:
      return
    self._calculate(self._mode, self.pressure_input.text if self._mode == "pressure" else self.temperature_input.text)

  @handle("pressure_mode_button", "click")
  def pressure_mode_button_click(self, **event_args):
    self._calculate("pressure", self.pressure_input.text or "")

  @handle("temperature_mode_button", "click")
  def temperature_mode_button_click(self, **event_args):
    self._calculate("temperature", self.temperature_input.text or "")

  @handle("ruler_calculate_button", "click")
  def ruler_calculate_button_click(self, **event_args):
    value = self.pressure_input.text if self._mode == "pressure" else self.temperature_input.text
    self._calculate(self._mode, value or "")

  @handle("calculations_button", "click")
  def calculations_button_click(self, **event_args):
    Access.open_window("Calculations")
