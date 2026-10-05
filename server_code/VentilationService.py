"""Independent ventilation calculator backed by Admin Studio settings."""

import json
import math

import anvil.server

import AdminStudio


_SEED = {
  "ventilation.area_min": 10,
  "ventilation.area_max": 5000,
  "ventilation.height_min": 2,
  "ventilation.height_max": 7,
  "ventilation.people_min": 1,
  "ventilation.people_max": 5000,
  "ventilation.default_area": 120,
  "ventilation.default_height": 2.75,
  "ventilation.default_people": 25,
  "ventilation.people_airflow": 40,
  "ventilation.default_air_changes": 2.5,
  "ventilation.supply_factor": 1.0,
  "ventilation.exhaust_factor": 1.0,
  "ventilation.fan_reserve_percent": 15,
  "ventilation.duct_velocity": 4,
  "ventilation.rounding_step": 10,
  "ventilation.duct_rounding_step": 5,
  "ventilation.price_equipment_base": 20000,
  "ventilation.price_automation": 40000,
  "ventilation.price_ducts_m2": 155,
  "ventilation.price_grille": 480,
  "ventilation.price_diffuser": 650,
  "ventilation.price_fan": 18000,
  "ventilation.price_recovery": 85000,
  "ventilation.price_filter": 6500,
  "ventilation.price_silencer": 8500,
  "ventilation.price_valve": 3200,
  "ventilation.price_materials_percent": 15,
  "ventilation.installation_percent": 50,
  "ventilation.duct_installation_percent": 80,
  "ventilation.commissioning_percent": 10,
  "ventilation.additional_percent": 3,
  "ventilation.recovery_default": 70,
  "ventilation.rounding_step": 10
}

_ROOM_SEED = [
  {"code": "office", "name": "Офисы", "air_changes": 2.5, "factor": 1.5},
  {"code": "shop", "name": "Магазины и ТЦ", "air_changes": 1.5, "factor": 1.2},
  {"code": "cafe", "name": "Кафе и рестораны", "air_changes": 3.0, "factor": 1.8},
  {"code": "production", "name": "Производства и цеха", "air_changes": 2.5, "factor": 1.0},
  {"code": "warehouse", "name": "Склады", "air_changes": 1.0, "factor": 1.2},
  {"code": "fitness", "name": "Фитнес-центры", "air_changes": 5.0, "factor": 1.2},
  {"code": "spa", "name": "Бассейны и СПА", "air_changes": 7.0, "factor": 1.4},
  {"code": "medical", "name": "Медицинские учреждения", "air_changes": 3.0, "factor": 1.5},
  {"code": "residential", "name": "Квартиры и частные дома", "air_changes": 2.0, "factor": 1.5},
  {"code": "school", "name": "Школы и детские учреждения", "air_changes": 2.5, "factor": 1.3},
  {"code": "datacenter", "name": "Серверные и дата-центры", "air_changes": 10.0, "factor": 2.0}
]

_SYSTEM_SEED = [
  {"code": "supply_exhaust", "name": "Приточно-вытяжная", "share": 1.0, "enabled": True},
  {"code": "supply", "name": "Приточная", "share": 0.6, "enabled": True},
  {"code": "exhaust", "name": "Вытяжная", "share": 0.4, "enabled": True},
  {"code": "recovery", "name": "С рекуперацией", "share": 1.0, "enabled": True},
  {"code": "cooling", "name": "С охлаждением", "share": 1.0, "enabled": True}
]

_RESULT_SEED = [
  {"key": "volume", "label": "Объём помещения", "unit": "м³", "visible": True, "order": 10},
  {"key": "air_exchange", "label": "Необходимый воздухообмен", "unit": "м³/ч", "visible": True, "order": 20},
  {"key": "supply", "label": "Приточный расход", "unit": "м³/ч", "visible": True, "order": 30},
  {"key": "exhaust", "label": "Вытяжной расход", "unit": "м³/ч", "visible": True, "order": 40},
  {"key": "fan", "label": "Производительность установки", "unit": "м³/ч", "visible": True, "order": 50},
  {"key": "duct", "label": "Сечение воздуховода", "unit": "мм", "visible": True, "order": 60},
  {"key": "equipment_cost", "label": "Оборудование", "unit": "₽", "visible": True, "order": 70},
  {"key": "installation_cost", "label": "Монтаж", "unit": "₽", "visible": True, "order": 80},
  {"key": "total", "label": "Итого", "unit": "₽", "visible": True, "order": 90}
]


def _setting(key):
  return AdminStudio.get_admin_studio_setting(key, _SEED.get(key))


def _number(value, name, minimum=None, maximum=None, integer=False):
  if isinstance(value, bool):
    raise ValueError("Поле «{}» должно быть числом.".format(name))
  try:
    result = float(value)
  except (TypeError, ValueError):
    raise ValueError("Поле «{}» должно быть числом.".format(name))
  if not math.isfinite(result):
    raise ValueError("Поле «{}» содержит некорректное число.".format(name))
  if minimum is not None and result < float(minimum):
    raise ValueError("Поле «{}»: минимум {}.".format(name, minimum))
  if maximum is not None and result > float(maximum):
    raise ValueError("Поле «{}»: максимум {}.".format(name, maximum))
  if integer and int(result) != result:
    raise ValueError("Поле «{}» должно быть целым.".format(name))
  return int(result) if integer else result


def _json_setting(key, fallback):
  value = AdminStudio.get_admin_studio_setting(key, fallback)
  if not isinstance(value, str):
    return fallback
  try:
    parsed = json.loads(value)
  except (TypeError, ValueError):
    return fallback
  return parsed


def _round(value):
  step = max(_number(_setting("ventilation.rounding_step"), "Шаг округления", 1), 1)
  return int(math.ceil(value / step) * step)


def _room_types():
  rows = _json_setting("ventilation.room_types_json", _ROOM_SEED)
  result = {}
  if isinstance(rows, list):
    for row in rows:
      if not isinstance(row, dict) or not row.get("code") or not row.get("name"):
        continue
      try:
        result[str(row["code"])] = {
          "name": str(row["name"]),
          "air_changes": _number(row.get("air_changes"), "Кратность помещения", 0, 100),
          "factor": _number(row.get("factor"), "Коэффициент помещения", 0, 20)
        }
      except ValueError:
        continue
  return result or {row["code"]: row for row in _ROOM_SEED}


def _system_types():
  rows = _json_setting("ventilation.system_types_json", _SYSTEM_SEED)
  result = {}
  if isinstance(rows, list):
    for row in rows:
      if not isinstance(row, dict) or not row.get("code") or not row.get("name"):
        continue
      if row.get("enabled", True) is False:
        continue
      try:
        result[str(row["code"])] = {
          "name": str(row["name"]),
          "share": _number(row.get("share"), "Доля системы", 0, 10)
        }
      except ValueError:
        continue
  return result or {row["code"]: row for row in _SYSTEM_SEED if row.get("enabled", True)}


def _safe_setup():
  rooms = _room_types()
  systems = _system_types()
  custom_fields = _json_setting("ventilation.custom_fields_json", [])
  if not isinstance(custom_fields, list):
    custom_fields = []
  custom_fields = [field for field in custom_fields
                   if isinstance(field, dict) and field.get("code") and field.get("visible", True) is not False]
  result_schema = _json_setting("ventilation.result_schema_json", _RESULT_SEED)
  if not isinstance(result_schema, list):
    result_schema = _RESULT_SEED
  content = {
    "page_title": AdminStudio.get_admin_studio_setting("ventilation.page_title", "Расчёт вентиляции"),
    "page_description": AdminStudio.get_admin_studio_setting(
      "ventilation.page_description", "Предварительный расчёт стоимости оборудования и монтажа вентиляции."
    ),
    "primary_button": AdminStudio.get_admin_studio_setting("ventilation.primary_button", "Рассчитать стоимость"),
    "show_types": AdminStudio.get_admin_studio_setting("ventilation.show_types", True) is not False,
    "show_process": AdminStudio.get_admin_studio_setting("ventilation.show_process", True) is not False,
    "show_faq": AdminStudio.get_admin_studio_setting("ventilation.show_faq", True) is not False,
    "show_media": AdminStudio.get_admin_studio_setting("ventilation.show_media", True) is not False
  }
  labels = {
    "area": AdminStudio.get_admin_studio_setting("ventilation.label_area", "Площадь помещения"),
    "length": AdminStudio.get_admin_studio_setting("ventilation.label_length", "Длина помещения"),
    "width": AdminStudio.get_admin_studio_setting("ventilation.label_width", "Ширина помещения"),
    "height": AdminStudio.get_admin_studio_setting("ventilation.label_height", "Высота потолка"),
    "people": AdminStudio.get_admin_studio_setting("ventilation.label_people", "Количество людей"),
    "duct_length": AdminStudio.get_admin_studio_setting("ventilation.label_duct_length", "Длина воздуховодов"),
    "branches": AdminStudio.get_admin_studio_setting("ventilation.label_branches", "Количество ответвлений")
  }
  return {
    "ok": True,
    "defaults": {
      "area": _number(_setting("ventilation.default_area"), "Площадь по умолчанию", 0.1),
      "length": 10,
      "width": 12,
      "height": _number(_setting("ventilation.default_height"), "Высота по умолчанию", 0.5),
      "people": _number(_setting("ventilation.default_people"), "Людей по умолчанию", 0, integer=True),
      "air_changes": _number(_setting("ventilation.default_air_changes"), "Кратность по умолчанию", 0),
      "equipment_capacity": 0,
      "duct_length": 20,
      "duct_diameter": 0,
      "branches": 2,
      "grilles": 2,
      "diffusers": 2,
      "fans": 1,
      "recuperators": 0,
      "filters": 1,
      "silencers": 0,
      "valves": 2,
      "automation": 1,
      "mounting": 1,
      "additional_work": 0
    },
    "limits": {
      "area": [_number(_setting("ventilation.area_min"), "Минимальная площадь", 0.1), _number(_setting("ventilation.area_max"), "Максимальная площадь", 1)],
      "height": [_number(_setting("ventilation.height_min"), "Минимальная высота", 0.5), _number(_setting("ventilation.height_max"), "Максимальная высота", 1)],
      "people": [_number(_setting("ventilation.people_min"), "Минимум людей", 0, integer=True), _number(_setting("ventilation.people_max"), "Максимум людей", 1, integer=True)]
    },
    "rooms": [(code, row["name"]) for code, row in rooms.items()],
    "systems": [(code, row["name"]) for code, row in systems.items()],
    "custom_fields": custom_fields,
    "result_schema": result_schema,
    "content": content,
    "labels": labels,
    "units": {
      "area": AdminStudio.get_admin_studio_setting("ventilation.unit_area", "м²"),
      "volume": AdminStudio.get_admin_studio_setting("ventilation.unit_volume", "м³"),
      "flow": AdminStudio.get_admin_studio_setting("ventilation.unit_flow", "м³/ч")
    }
  }


@anvil.server.callable
def get_ventilation_calculator_setup():
  return _safe_setup()


@anvil.server.callable
def calculate_ventilation_estimate(inputs):
  if not isinstance(inputs, dict):
    return {"ok": False, "message": "Передайте параметры помещения."}
  setup = _safe_setup()
  try:
    area_raw = inputs.get("area")
    area = 0 if area_raw in (None, "", 0, "0", "0.0") else _number(
      area_raw, "Площадь", setup["limits"]["area"][0], setup["limits"]["area"][1]
    )
    length = _number(inputs.get("length", 0), "Длина", 0, 10000)
    width = _number(inputs.get("width", 0), "Ширина", 0, 10000)
    height = _number(inputs.get("height"), "Высота", setup["limits"]["height"][0], setup["limits"]["height"][1])
    people = _number(inputs.get("people"), "Количество людей", setup["limits"]["people"][0], setup["limits"]["people"][1], integer=True)
    air_changes = _number(inputs.get("air_changes"), "Кратность воздухообмена", 0, 100)
    required_flow = _number(inputs.get("required_flow", 0), "Требуемый расход воздуха", 0, 10000000)
    equipment_capacity = _number(inputs.get("equipment_capacity", 0), "Производительность оборудования", 0, 10000000)
    duct_length = _number(inputs.get("duct_length", 0), "Длина воздуховодов", 0, 100000)
    duct_diameter = _number(inputs.get("duct_diameter", 0), "Диаметр воздуховода", 0, 5000)
    branches = _number(inputs.get("branches", 0), "Ответвления", 0, 100000, integer=True)
    grilles = _number(inputs.get("grilles", 0), "Решётки", 0, 100000, integer=True)
    diffusers = _number(inputs.get("diffusers", 0), "Диффузоры", 0, 100000, integer=True)
    fans = _number(inputs.get("fans", 0), "Вентиляторы", 0, 10000, integer=True)
    recuperators = _number(inputs.get("recuperators", 0), "Рекуператоры", 0, 10000, integer=True)
    filters = _number(inputs.get("filters", 0), "Фильтры", 0, 100000, integer=True)
    silencers = _number(inputs.get("silencers", 0), "Шумоглушители", 0, 100000, integer=True)
    valves = _number(inputs.get("valves", 0), "Клапаны", 0, 100000, integer=True)
    automation = _number(inputs.get("automation", 0), "Автоматика", 0, 10000, integer=True)
    mounting = _number(inputs.get("mounting", 1), "Монтаж", 0, 100)
    additional_work = _number(inputs.get("additional_work", 0), "Дополнительные работы", 0, 100000000)
  except ValueError as error:
    return {"ok": False, "message": str(error)}

  custom_values = inputs.get("custom_fields", {})
  if not isinstance(custom_values, dict):
    custom_values = {}
  custom_definitions = _json_setting("ventilation.custom_fields_json", [])
  if not isinstance(custom_definitions, list):
    custom_definitions = []
  for field in custom_definitions:
    if not isinstance(field, dict) or not field.get("code") or field.get("visible", True) is False:
      continue
    code = str(field["code"])
    raw_value = custom_values.get(code, field.get("default", ""))
    if field.get("required") and raw_value in (None, ""):
      return {"ok": False, "message": "Заполните обязательное поле «{}».".format(field.get("label", code))}
    if field.get("type") == "number" and raw_value not in (None, ""):
      try:
        number = float(raw_value)
      except (TypeError, ValueError):
        return {"ok": False, "message": "Поле «{}» должно быть числом.".format(field.get("label", code))}
      if not math.isfinite(number):
        return {"ok": False, "message": "Поле «{}» содержит некорректное число.".format(field.get("label", code))}
      if field.get("minimum") is not None and number < float(field["minimum"]):
        return {"ok": False, "message": "Поле «{}»: минимум {}.".format(field.get("label", code), field["minimum"])}
      if field.get("maximum") is not None and number > float(field["maximum"]):
        return {"ok": False, "message": "Поле «{}»: максимум {}.".format(field.get("label", code), field["maximum"])}

  rooms = _room_types()
  systems = _system_types()
  room = rooms.get(inputs.get("room_type")) or next(iter(rooms.values()))
  system_code = inputs.get("ventilation_type")
  system = systems.get(system_code) or next(iter(systems.values()))
  effective_area = area if area > 0 else length * width
  if effective_area <= 0:
    return {"ok": False, "message": "Укажите площадь или одновременно длину и ширину помещения."}
  volume = effective_area * height
  configured_changes = air_changes if air_changes > 0 else room["air_changes"]
  exchange_flow = max(volume * configured_changes, people * _number(_setting("ventilation.people_airflow"), "Расход на человека", 0), required_flow)
  supply_enabled = system_code not in ("exhaust",)
  exhaust_enabled = system_code not in ("supply",)
  supply_flow = exchange_flow * _number(_setting("ventilation.supply_factor"), "Поправка притока", 0) if supply_enabled else 0
  exhaust_flow = exchange_flow * _number(_setting("ventilation.exhaust_factor"), "Поправка вытяжки", 0) if exhaust_enabled else 0
  design_flow = max(supply_flow, exhaust_flow, equipment_capacity)
  fan_flow = design_flow * (1 + _number(_setting("ventilation.fan_reserve_percent"), "Резерв вентилятора", 0) / 100)
  velocity = _number(_setting("ventilation.duct_velocity"), "Скорость в воздуховоде", 0.1)
  duct_area = fan_flow / 3600 / velocity if fan_flow else 0
  diameter = duct_diameter or math.sqrt(4 * duct_area / math.pi) * 1000 if duct_area else 0
  duct_step = max(_number(_setting("ventilation.duct_rounding_step"), "Шаг размеров", 1), 1)
  recommended_diameter = int(math.ceil(diameter / duct_step) * duct_step) if diameter else 0
  recommended_side = int(math.ceil(math.sqrt(duct_area) * 1000 / duct_step) * duct_step) if duct_area else 0
  estimated_grilles = grilles or max(1, int(math.ceil(supply_flow / 150))) if supply_enabled else 0
  estimated_diffusers = diffusers or max(1, int(math.ceil(supply_flow / 120))) if supply_enabled else 0
  estimated_fans = fans or (1 if design_flow else 0)
  estimated_branches = branches or max(1, int(math.ceil(design_flow / 500))) if design_flow else 0

  def price(key):
    return _number(_setting(key), key, 0, 100000000)

  equipment_cost = price("ventilation.price_equipment_base") * room["factor"] * system["share"]
  equipment_cost += estimated_fans * price("ventilation.price_fan")
  equipment_cost += recuperators * price("ventilation.price_recovery")
  equipment_cost += filters * price("ventilation.price_filter")
  equipment_cost += silencers * price("ventilation.price_silencer")
  equipment_cost += valves * price("ventilation.price_valve")
  ducts_cost = duct_length * price("ventilation.price_ducts_m2")
  distribution_cost = estimated_grilles * price("ventilation.price_grille") + estimated_diffusers * price("ventilation.price_diffuser")
  automation_cost = automation * price("ventilation.price_automation")
  materials_cost = (equipment_cost + ducts_cost + distribution_cost + automation_cost) * price("ventilation.price_materials_percent") / 100
  installation_cost = (equipment_cost * price("ventilation.installation_percent") / 100 + ducts_cost * price("ventilation.duct_installation_percent") / 100) * mounting
  commissioning_cost = installation_cost * price("ventilation.commissioning_percent") / 100
  additional_cost = additional_work + (equipment_cost + ducts_cost) * price("ventilation.additional_percent") / 100
  total = sum((equipment_cost, ducts_cost, distribution_cost, automation_cost, materials_cost, installation_cost, commissioning_cost, additional_cost))

  breakdown = [
    {"key": "equipment", "label": "Оборудование", "value": _round(equipment_cost), "unit": "₽"},
    {"key": "ducts", "label": "Воздуховоды", "value": _round(ducts_cost), "unit": "₽"},
    {"key": "distribution", "label": "Решётки и диффузоры", "value": _round(distribution_cost), "unit": "₽"},
    {"key": "automation", "label": "Автоматика", "value": _round(automation_cost), "unit": "₽"},
    {"key": "materials", "label": "Расходные материалы", "value": _round(materials_cost), "unit": "₽"},
    {"key": "installation", "label": "Монтаж", "value": _round(installation_cost), "unit": "₽"},
    {"key": "commissioning", "label": "Пусконаладка", "value": _round(commissioning_cost), "unit": "₽"},
    {"key": "additional", "label": "Дополнительные расходы", "value": _round(additional_cost), "unit": "₽"}
  ]
  return {
    "ok": True,
    "volume": volume,
    "air_exchange": exchange_flow,
    "supply": supply_flow,
    "exhaust": exhaust_flow,
    "fan": fan_flow,
    "duct_area": duct_area * 10000,
    "duct_diameter": recommended_diameter,
    "duct_rect": "{} × {} мм".format(recommended_side * 2, recommended_side) if recommended_side else "—",
    "counts": {
      "branches": estimated_branches,
      "grilles": estimated_grilles,
      "diffusers": estimated_diffusers,
      "fans": estimated_fans,
      "recuperators": recuperators,
      "filters": filters,
      "silencers": silencers,
      "valves": valves,
      "automation": automation
    },
    "equipment_cost": _round(equipment_cost + distribution_cost + automation_cost),
    "installation_cost": _round(installation_cost + commissioning_cost),
    "additional_cost": _round(additional_cost + materials_cost),
    "total": _round(total),
    "breakdown": breakdown,
    "context": {"room": room["name"], "system": system["name"], "air_changes": configured_changes}
  }
