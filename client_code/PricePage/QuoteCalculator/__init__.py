from ._anvil_designer import QuoteCalculatorTemplate
import anvil.server


INSTALLATION_TYPES = (
  ("Приточная установка", "supply"),
  ("Вытяжная установка", "exhaust"),
  ("Приточно-вытяжная установка", "supply_exhaust"),
)

FAN_OPTIONS = (
  ("Круглый канал · Ø100 мм", "fan_round_100"),
  ("Круглый канал · Ø125 мм", "fan_round_125"),
  ("Круглый канал · Ø160 мм", "fan_round_160"),
  ("Круглый канал · Ø200 мм", "fan_round_200"),
  ("Круглый канал · Ø250 мм", "fan_round_250"),
  ("Прямоугольный канал · 400×200 мм", "fan_rect_400x200"),
  ("Прямоугольный канал · 500×250 мм", "fan_rect_500x250"),
  ("Крышный вентилятор", "fan_roof"),
  ("Радиальный вентилятор", "fan_radial"),
)

INPUT_FIELDS = (
  ("room_area_box", "Площадь помещения", False, 1000000),
  ("room_height_box", "Высота помещения", False, 100),
  ("occupants_box", "Количество людей", True, 100000),
  ("air_change_box", "Кратность воздухообмена", False, 100),
  ("installation_flow_box", "Производительность установки", False, 100000),
  ("installation_count_box", "Количество установок", True, 1000),
  ("equipment_unit_price_box", "Цена оборудования за установку", False, 100000000),
  ("fan_count_box", "Количество вентиляторов", True, 10000),
  ("fan_equipment_price_box", "Цена одного вентилятора", False, 100000000),
  ("duct_length_box", "Длина воздуховодов", False, 100000),
  ("rigid_duct_area_box", "Площадь жёстких воздуховодов", False, 1000000),
  ("pipe_length_box", "Длина инженерных труб", False, 100000),
  ("branch_count_box", "Количество ответвлений", True, 10000),
  ("filter_count_box", "Количество фильтров", True, 10000),
  ("diffuser_count_box", "Количество диффузоров", True, 10000),
  ("throttle_damper_count_box", "Количество дроссель-клапанов", True, 10000),
  ("outer_grille_count_box", "Количество наружных решёток", True, 10000),
  ("smoke_damper_count_box", "Количество клапанов дымоудаления", True, 10000),
  ("binding_unit_count_box", "Количество узлов обвязки", True, 10000),
  ("silencer_count_box", "Количество шумоглушителей", True, 10000),
  ("valve_count_box", "Количество воздушных клапанов", True, 10000),
  ("automation_count_box", "Комплекты автоматики", True, 10000),
  ("extra_work_price_box", "Дополнительные работы", False, 100000000),
)

COMPONENT_RATES = (
  ("filter_count_box", "install_filter", "material_filter", "Монтаж и фильтры", "шт."),
  ("diffuser_count_box", "install_diffuser", "material_diffuser", "Диффузоры", "шт."),
  ("throttle_damper_count_box", "install_throttle_damper", "material_throttle_damper", "Дроссель-клапаны", "шт."),
  ("outer_grille_count_box", "install_outer_grille", "material_outer_grille", "Наружные решётки", "шт."),
  ("smoke_damper_count_box", "install_smoke_damper", "material_smoke_damper", "Клапаны дымоудаления", "шт."),
  ("binding_unit_count_box", "install_binding_unit", "material_binding_unit", "Узлы обвязки", "шт."),
  ("silencer_count_box", "install_silencer", "material_silencer", "Шумоглушители", "шт."),
  ("valve_count_box", "install_valve", "material_valve", "Воздушные клапаны", "шт."),
  ("automation_count_box", "install_automation", "material_automation", "Автоматика", "компл."),
)


class QuoteCalculator(QuoteCalculatorTemplate):
  """Ventilation installation estimator with separate tariffs and state."""

  def __init__(self, **properties):
    super().__init__(**properties)
    self._ready = False
    self._rates = {}
    self.installation_type_dropdown.items = list(INSTALLATION_TYPES)
    self.fan_installation_dropdown.items = list(FAN_OPTIONS)
    self.duct_type_dropdown.items = [
      ("Не включать воздуховоды", "none"),
      ("Жёсткие воздуховоды", "rigid"),
      ("Гибкие воздуховоды", "flexible"),
    ]
    self.duct_diameter_dropdown.items = [
      ("D100", "100"), ("D160", "160"),
      ("D200", "200"), ("D250", "250"),
    ]
    self.installation_type_dropdown.selected_value = "supply"
    self.fan_installation_dropdown.selected_value = "fan_round_100"
    self.duct_type_dropdown.selected_value = "none"
    self.duct_diameter_dropdown.selected_value = "100"
    for name, label, integer, maximum in INPUT_FIELDS:
      getattr(self, name).text = "0"
      getattr(self, name).set_event_handler("change", self._input_changed)
    self.installation_flow_box.text = "500"
    self.installation_count_box.text = "1"
    self.air_change_box.text = "1"
    for name in (
      "installation_type_dropdown", "fan_installation_dropdown",
      "duct_type_dropdown", "duct_diameter_dropdown",
      "recovery_checkbox", "cooling_checkbox"
    ):
      getattr(self, name).set_event_handler("change", self._input_changed)
    self.calculate_button.set_event_handler("click", self._calculate_click)
    self.reset_button.set_event_handler("click", self._reset_inputs)
    self._load_rates()

  def _load_rates(self):
    result = anvil.server.call("get_ventilation_estimator_rates")
    self._rates = result.get("rates", {})
    self.estimate_notice.text = result.get("notice", "")
    self._ready = True
    self._recalculate()

  def _input_changed(self, **event_args):
    if self._ready:
      self._recalculate()

  def _calculate_click(self, **event_args):
    self._recalculate()

  def _reset_inputs(self, **event_args):
    self.installation_type_dropdown.selected_value = "supply"
    self.fan_installation_dropdown.selected_value = "fan_round_100"
    self.duct_type_dropdown.selected_value = "none"
    self.duct_diameter_dropdown.selected_value = "100"
    self.recovery_checkbox.checked = False
    self.cooling_checkbox.checked = False
    self.extra_work_description_box.text = ""
    for name, label, integer, maximum in INPUT_FIELDS:
      getattr(self, name).text = "0"
    self.installation_flow_box.text = "500"
    self.installation_count_box.text = "1"
    self.air_change_box.text = "1"
    self._recalculate()

  def _read_values(self):
    values = {}
    for name, label, integer, maximum in INPUT_FIELDS:
      raw = (getattr(self, name).text or "").strip().replace(",", ".")
      if not raw:
        value = 0.0
      else:
        try:
          value = float(raw)
        except (TypeError, ValueError, OverflowError):
          return None, "В поле «{}» укажите число.".format(label)
      if value != value or value < 0 or value > maximum:
        return None, "Поле «{}» должно быть от 0 до {}.".format(label, maximum)
      if integer and value != int(value):
        return None, "В поле «{}» укажите целое количество.".format(label)
      values[name] = int(value) if integer else value
    if values["installation_count_box"] and values["installation_flow_box"] <= 0:
      return None, "Укажите производительность установки в м³/ч."
    if values["room_area_box"] and values["room_height_box"] and not values["air_change_box"]:
      return None, "Для расчёта по объёму задайте кратность воздухообмена больше нуля."
    if values["duct_type_dropdown"] if "duct_type_dropdown" in values else False:
      pass
    if values["rigid_duct_area_box"] and self.duct_type_dropdown.selected_value != "rigid":
      return None, "Выберите жёсткие воздуховоды для расчёта площади каналов."
    if values["duct_length_box"] and self.duct_type_dropdown.selected_value == "none":
      return None, "Выберите тип воздуховода, чтобы учесть его длину в смете."
    return values, None

  def _rate(self, key):
    value = self._rates.get(key, 0)
    try:
      value = float(value)
    except (TypeError, ValueError, OverflowError):
      return 0.0
    if value != value or value < 0 or value > 100000000:
      return 0.0
    return value

  def _installation_rate_key(self, system, flow):
    if system == "supply":
      tiers = ((500, "install_supply_500"), (1000, "install_supply_1000"),
               (3000, "install_supply_3000"), (float("inf"), "install_supply_5500"))
    elif system == "exhaust":
      tiers = ((1000, "install_exhaust_1000"), (3000, "install_exhaust_3000"),
               (5000, "install_exhaust_5000"), (float("inf"), "install_exhaust_5500"))
    else:
      tiers = ((1000, "install_supply_exhaust_1000"),
               (3000, "install_supply_exhaust_3000"),
               (5000, "install_supply_exhaust_5000"),
               (float("inf"), "install_supply_exhaust_5500"))
    return next(key for limit, key in tiers if flow <= limit)

  def _room_airflow(self, values):
    area = values["room_area_box"]
    height = values["room_height_box"]
    volume = area * height if area and height else 0
    people_flow = values["occupants_box"] * self._rate("air_per_person_m3h")
    air_change_flow = volume * values["air_change_box"]
    required_flow = max(people_flow, air_change_flow)
    return volume, required_flow

  @staticmethod
  def _money(value):
    return "{:,.0f} ₽".format(value).replace(",", " ")

  @staticmethod
  def _number(value):
    return "{:,.2f}".format(value).replace(",", " ").rstrip("0").rstrip(".")

  def _line(self, lines, category, title, quantity, unit, unit_price):
    amount = quantity * unit_price
    if quantity <= 0 or unit_price <= 0:
      return 0
    lines.append({
      "category": category,
      "title": title,
      "quantity": "{} {}".format(self._number(quantity), unit),
      "unit_price": self._money(unit_price),
      "total": self._money(amount),
    })
    return amount

  def _recalculate(self):
    values, error = self._read_values()
    if error:
      self.estimate_message.text = error
      self.airflow_summary.text = "Проверьте исходные данные расчёта."
      self.breakdown_rows.items = []
      self.estimate_total.text = "—"
      self.equipment_total.text = "—"
      self.installation_total.text = "—"
      self.materials_total.text = "—"
      self.additional_total.text = "—"
      return

    lines = []
    equipment_total = 0.0
    installation_total = 0.0
    materials_total = 0.0
    extra_total = values["extra_work_price_box"]
    count = values["installation_count_box"]
    flow = values["installation_flow_box"]
    system = self.installation_type_dropdown.selected_value or "supply"
    system_labels = dict((code, title) for title, code in INSTALLATION_TYPES)
    room_volume, required_flow = self._room_airflow(values)
    installed_flow = count * flow
    self.airflow_summary.text = (
      "Объём помещения: {} м³ · расчётный расход: {} м³/ч · "
      "выбранная мощность: {} м³/ч".format(
        self._number(room_volume), self._number(required_flow),
        self._number(installed_flow)
      )
    )
    if required_flow and installed_flow < required_flow:
      self.airflow_message.text = "Мощности недостаточно примерно на {} м³/ч. Увеличьте производительность или количество установок.".format(
        self._number(required_flow - installed_flow)
      )
    elif required_flow:
      self.airflow_message.text = "Выбранная производительность покрывает расчётный расход воздуха. Это предварительный подбор, не замена проекту." 
    else:
      self.airflow_message.text = "Укажите площадь, высоту или число людей, чтобы сравнить установку с расчётным воздухообменом."

    if count:
      rate_key = self._installation_rate_key(system, flow)
      unit_rate = self._rate(rate_key)
      installation_total += self._line(
        lines, "Монтаж", system_labels.get(system, "Монтаж установки"),
        count, "шт.", unit_rate
      )
      equipment_rate_key = "equipment_{}".format(rate_key.replace("install_", "", 1))
      equipment_unit_price = values["equipment_unit_price_box"] or self._rate(equipment_rate_key)
      equipment_total += self._line(
        lines, "Оборудование", "{} · {} м³/ч".format(
          system_labels.get(system, "Вентиляционная установка"), self._number(flow)
        ), count, "шт.", equipment_unit_price
      )
      for checked, code, title in (
        (self.recovery_checkbox.checked, "recovery", "Рекуперация"),
        (self.cooling_checkbox.checked, "cooling", "Охлаждение воздуха"),
      ):
        if checked:
          installation_total += self._line(
            lines, "Монтаж", "Монтаж: {}".format(title), count, "шт.",
            self._rate("install_addon_{}".format(code))
          )
          equipment_total += self._line(
            lines, "Оборудование", "Оборудование: {}".format(title), count,
            "шт.", self._rate("equipment_addon_{}".format(code))
          )

    fan_count = values["fan_count_box"]
    if fan_count:
      fan_code = self.fan_installation_dropdown.selected_value or "fan_round_100"
      installation_total += self._line(
        lines, "Монтаж", "Монтаж вентилятора", fan_count, "шт.",
        self._rate(fan_code)
      )
      equipment_total += self._line(
        lines, "Оборудование", "Вентиляторы", fan_count, "шт.",
        values["fan_equipment_price_box"] or self._rate("material_fan")
      )

    duct_type = self.duct_type_dropdown.selected_value or "none"
    duct_length = values["duct_length_box"]
    diameter = self.duct_diameter_dropdown.selected_value or "100"
    if duct_type == "rigid":
      area = values["rigid_duct_area_box"]
      if not area and duct_length:
        area = duct_length * 3.14159265359 * float(diameter) / 1000
      if area:
        tiers = ((50, "duct_rigid_50"), (100, "duct_rigid_100"),
                 (500, "duct_rigid_500"), (1000, "duct_rigid_1000"),
                 (float("inf"), "duct_rigid_over_1000"))
        duct_rate = next(self._rate(key) for limit, key in tiers if area <= limit)
        installation_total += self._line(
          lines, "Монтаж", "Жёсткие воздуховоды", area, "м²", duct_rate
        )
        materials_total += self._line(
          lines, "Материалы", "Материал жёстких воздуховодов", area, "м²",
          self._rate("material_rigid_duct_m2")
        )
    elif duct_type == "flexible" and duct_length:
      installation_total += self._line(
        lines, "Монтаж", "Гибкие воздуховоды · D{}".format(diameter),
        duct_length, "м", self._rate("duct_flexible_{}".format(diameter))
      )
      materials_total += self._line(
        lines, "Материалы", "Гибкий воздуховод · D{}".format(diameter),
        duct_length, "м", self._rate("material_flexible_{}".format(diameter))
      )

    pipe_length = values["pipe_length_box"]
    installation_total += self._line(
      lines, "Монтаж", "Прокладка инженерных труб", pipe_length, "м",
      self._rate("labor_pipe_m")
    )
    materials_total += self._line(
      lines, "Материалы", "Труба и изоляция", pipe_length, "м",
      self._rate("material_pipe_m")
    )

    branches = values["branch_count_box"]
    installation_total += self._line(
      lines, "Монтаж", "Устройство ответвлений", branches, "шт.",
      self._rate("install_branch")
    )
    materials_total += self._line(
      lines, "Материалы", "Фасонные части", branches, "шт.",
      self._rate("material_branch_fitting")
    )

    for field, install_code, material_code, title, unit in COMPONENT_RATES:
      quantity = values[field]
      installation_total += self._line(
        lines, "Монтаж", title, quantity, unit, self._rate(install_code)
      )
      materials_total += self._line(
        lines, "Материалы", title, quantity, unit, self._rate(material_code)
      )

    if duct_type != "none" and duct_length:
      materials_total += self._line(
        lines, "Расходники", "Подвесы и крепёж", duct_length, "м",
        self._rate("material_support_m")
      )
      materials_total += self._line(
        lines, "Расходники", "Лента, герметик и расходники", duct_length, "м",
        self._rate("material_consumables_m")
      )

    extra_description = (self.extra_work_description_box.text or "").strip()
    if extra_total:
      lines.append({
        "category": "Дополнительно",
        "title": extra_description or "Дополнительные работы и материалы",
        "quantity": "1",
        "unit_price": self._money(extra_total),
        "total": self._money(extra_total),
      })

    total = equipment_total + installation_total + materials_total + extra_total
    self.equipment_total.text = self._money(equipment_total)
    self.installation_total.text = self._money(installation_total)
    self.materials_total.text = self._money(materials_total)
    self.additional_total.text = self._money(extra_total)
    self.estimate_total.text = self._money(total)
    self.breakdown_rows.items = lines
    self.estimate_message.text = "Смета пересчитывается автоматически. Это предварительная оценка."

