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
  "ventilation.price_cooling": 45000,
  "ventilation.cooling_capacity_per_unit": 8,
  "ventilation.heat_capacity": 0.335,
  "ventilation.price_materials_percent": 15,
  "ventilation.installation_percent": 50,
  "ventilation.duct_installation_percent": 80,
  "ventilation.commissioning_percent": 10,
  "ventilation.additional_percent": 3,
  "ventilation.recovery_default": 70
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
  {"code": "supply_exhaust", "name": "Приточно-вытяжная", "description": "Одновременно подаёт и удаляет воздух, поддерживая баланс потоков.", "mode": "balanced", "share": 1.0, "enabled": True, "features": []},
  {"code": "supply", "name": "Приточная", "description": "Подаёт наружный воздух с фильтрацией и подготовкой по проекту.", "mode": "supply", "share": 0.6, "enabled": True, "features": []},
  {"code": "exhaust", "name": "Вытяжная", "description": "Удаляет загрязнённый воздух, запахи и избыток влаги.", "mode": "exhaust", "share": 0.4, "enabled": True, "features": []},
  {"code": "recovery", "name": "С рекуперацией", "description": "Передаёт тепло удаляемого воздуха приточному потоку.", "mode": "balanced", "share": 1.0, "enabled": True, "features": ["recovery"]},
  {"code": "cooling", "name": "С охлаждением", "description": "Добавляет охлаждающий блок в предварительную смету системы.", "mode": "balanced", "share": 1.0, "enabled": True, "features": ["cooling"]}
]

_EQUIPMENT_SEED = [
  {"code": "fan", "name": "Вентилятор", "price_key": "ventilation.price_fan", "enabled": True},
  {"code": "recovery", "name": "Рекуператор", "price_key": "ventilation.price_recovery", "enabled": True},
  {"code": "cooling", "name": "Охлаждающий блок", "price_key": "ventilation.price_cooling", "enabled": True},
  {"code": "filter", "name": "Фильтр", "price_key": "ventilation.price_filter", "enabled": True},
  {"code": "silencer", "name": "Шумоглушитель", "price_key": "ventilation.price_silencer", "enabled": True},
  {"code": "valve", "name": "Клапан", "price_key": "ventilation.price_valve", "enabled": True},
  {"code": "grille", "name": "Решётка", "price_key": "ventilation.price_grille", "enabled": True},
  {"code": "diffuser", "name": "Диффузор", "price_key": "ventilation.price_diffuser", "enabled": True},
  {"code": "automation", "name": "Автоматика", "price_key": "ventilation.price_automation", "enabled": True}
]

_RESULT_SEED = [
  {"key": "volume", "label": "Объём помещения", "unit": "м³", "visible": True, "order": 10},
  {"key": "air_exchange", "label": "Необходимый воздухообмен", "unit": "м³/ч", "visible": True, "order": 20},
  {"key": "supply", "label": "Приточный расход", "unit": "м³/ч", "visible": True, "order": 30},
  {"key": "exhaust", "label": "Вытяжной расход", "unit": "м³/ч", "visible": True, "order": 40},
  {"key": "fan", "label": "Производительность установки", "unit": "м³/ч", "visible": True, "order": 50},
  {"key": "cooling_capacity", "label": "Расчётная холодопроизводительность", "unit": "кВт", "visible": True, "order": 55},
  {"key": "recovery_power", "label": "Тепловая мощность рекуперации", "unit": "кВт", "visible": True, "order": 57},
  {"key": "duct", "label": "Сечение воздуховода", "unit": "мм", "visible": True, "order": 60},
  {"key": "equipment_cost", "label": "Оборудование", "unit": "₽", "visible": True, "order": 70},
  {"key": "installation_cost", "label": "Монтаж", "unit": "₽", "visible": True, "order": 80},
  {"key": "additional_cost", "label": "Дополнительные расходы", "unit": "₽", "visible": True, "order": 85},
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


def _json_list(key, fallback=None):
  value = _json_setting(key, fallback or [])
  return value if isinstance(value, list) else (fallback or [])


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


def _equipment_types():
  rows = _json_list("ventilation.equipment_json", _EQUIPMENT_SEED)
  result = {row["code"]: dict(row) for row in _EQUIPMENT_SEED}
  allowed = set(result)
  for row in rows:
    if not isinstance(row, dict) or row.get("code") not in allowed:
      continue
    code = row["code"]
    price_key = row.get("price_key")
    if price_key not in _SEED or not price_key.startswith("ventilation.price_"):
      continue
    enabled = row.get("enabled", True)
    if not isinstance(enabled, bool):
      continue
    name = row.get("name", result[code]["name"])
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
      continue
    result[code] = {
      "code": code, "name": name.strip(), "price_key": price_key,
      "enabled": enabled
    }
  return result


def _system_types(equipment=None):
  rows = _json_setting("ventilation.system_types_json", _SYSTEM_SEED)
  result = {}
  equipment = equipment or _equipment_types()
  if isinstance(rows, list):
    for row in rows:
      if not isinstance(row, dict) or not row.get("code") or not row.get("name"):
        continue
      if row.get("enabled", True) is False:
        continue
      try:
        features = row.get("features", [])
        if not isinstance(features, list):
          features = []
        features = [feature for feature in features if feature in ("recovery", "cooling")]
        if any(not equipment.get(feature, {}).get("enabled", True) for feature in features):
          continue
        mode = row.get("mode")
        if mode is None:
          mode = {"supply": "supply", "exhaust": "exhaust"}.get(row["code"], "balanced")
        if mode not in ("balanced", "supply", "exhaust"):
          continue
        result[str(row["code"])] = {
          "name": str(row["name"]),
          "description": str(row.get("description", ""))[:500],
          "mode": mode,
          "share": _number(row.get("share"), "Доля системы", 0, 10),
          "features": features
        }
      except ValueError:
        continue
  if result:
    return result
  return {
    row["code"]: row for row in _SYSTEM_SEED
    if row.get("enabled", True)
    and not any(not equipment.get(feature, {}).get("enabled", True)
                for feature in row.get("features", []))
  }


def _safe_setup():
  rooms = _room_types()
  equipment = _equipment_types()
  systems = _system_types(equipment)
  custom_fields = _json_list("ventilation.custom_fields_json")
  custom_fields = [field for field in custom_fields
                   if isinstance(field, dict) and field.get("code") and field.get("visible", True) is not False]
  custom_fields.sort(key=lambda field: (
    field.get("order", 0) if isinstance(field.get("order", 0), int)
    and not isinstance(field.get("order", 0), bool) else 0
  ))
  raw_result_schema = _json_setting("ventilation.result_schema_json", _RESULT_SEED)
  if not isinstance(raw_result_schema, list):
    raw_result_schema = _RESULT_SEED
  allowed_result_keys = {item["key"] for item in _RESULT_SEED}
  result_schema = []
  for item in raw_result_schema:
    if not isinstance(item, dict) or item.get("key") not in allowed_result_keys:
      continue
    label = item.get("label")
    unit = item.get("unit", "")
    order = item.get("order", 0)
    if (not isinstance(label, str) or not label.strip() or len(label) > 160
        or not isinstance(unit, str) or len(unit) > 30
        or not isinstance(item.get("visible", True), bool)
        or isinstance(order, bool) or not isinstance(order, int) or order < 0):
      continue
    result_schema.append(dict(item))
  if raw_result_schema and not result_schema:
    result_schema = [dict(item) for item in _RESULT_SEED]
  area_min = _number(_setting("ventilation.area_min"), "Минимальная площадь", 0.1)
  area_max = _number(_setting("ventilation.area_max"), "Максимальная площадь", 1)
  height_min = _number(_setting("ventilation.height_min"), "Минимальная высота", 0.5)
  height_max = _number(_setting("ventilation.height_max"), "Максимальная высота", 1)
  people_min = _number(_setting("ventilation.people_min"), "Минимум людей", 0, integer=True)
  people_max = _number(_setting("ventilation.people_max"), "Максимум людей", 1, integer=True)
  if area_min > area_max or height_min > height_max or people_min > people_max:
    raise ValueError("В настройках вентиляции минимум не может превышать максимум.")
  default_area = _number(_setting("ventilation.default_area"), "Площадь по умолчанию", area_min, area_max)
  default_height = _number(_setting("ventilation.default_height"), "Высота по умолчанию", height_min, height_max)
  default_people = _number(_setting("ventilation.default_people"), "Людей по умолчанию", people_min, people_max, integer=True)
  content = {
    "page_title": AdminStudio.get_admin_studio_setting("ventilation.page_title", "Расчёт вентиляции"),
    "seo_title": AdminStudio.get_admin_studio_setting("ventilation.seo_title", "Расчёт вентиляции · оборудование и монтаж"),
    "seo_description": AdminStudio.get_admin_studio_setting(
      "ventilation.seo_description", "Рассчитайте воздухообмен, оборудование и ориентировочную стоимость монтажа вентиляции."
    ),
    "seo_keywords": AdminStudio.get_admin_studio_setting(
      "ventilation.seo_keywords", "вентиляция, расчёт вентиляции, монтаж вентиляции, воздуховоды"
    ),
    "page_description": AdminStudio.get_admin_studio_setting(
      "ventilation.page_description", "Предварительный расчёт стоимости оборудования и монтажа вентиляции."
    ),
    "primary_button": AdminStudio.get_admin_studio_setting("ventilation.primary_button", "Рассчитать стоимость"),
    "formula_notes": AdminStudio.get_admin_studio_setting(
      "ventilation.formula_notes", "V = S × H; Q = max(V × n, N × q); сечение = Q / (3600 × v)."
    ),
    "system_cards": [
      {"title": row["name"], "text": row.get("description", ""), "index": "{:02d}".format(index + 1)}
      for index, row in enumerate(systems.values())
    ],
    "advantages": _json_list("ventilation.advantages_json"),
    "process": _json_list("ventilation.process_json"),
    "faq": _json_list("ventilation.faq_json"),
    "images": _json_list("ventilation.images_json"),
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
      "area": default_area,
      "length": 10,
      "width": 12,
      "height": default_height,
      "people": default_people,
      "air_changes": _number(_setting("ventilation.default_air_changes"), "Кратность по умолчанию", 0),
      "temperature_delta": 10,
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
      "area": [area_min, area_max],
      "height": [height_min, height_max],
      "people": [people_min, people_max]
    },
    "rooms": [(code, row["name"]) for code, row in rooms.items()],
    "systems": [(code, row["name"]) for code, row in systems.items()],
    "equipment": equipment,
    "custom_fields": custom_fields,
    "result_schema": result_schema,
    "content": content,
    "result_options": {
      "show_breakdown": AdminStudio.get_admin_studio_setting("ventilation.show_breakdown", True) is not False,
      "show_prices": AdminStudio.get_admin_studio_setting("ventilation.show_prices", True) is not False,
      "show_units": AdminStudio.get_admin_studio_setting("ventilation.show_units", True) is not False
    },
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
    area_input = 0 if area_raw in (None, "", 0, "0", "0.0") else _number(
      area_raw, "Площадь", setup["limits"]["area"][0], setup["limits"]["area"][1]
    )
    length = _number(inputs.get("length", 0), "Длина", 0, 10000)
    width = _number(inputs.get("width", 0), "Ширина", 0, 10000)
    height = _number(inputs.get("height"), "Высота", setup["limits"]["height"][0], setup["limits"]["height"][1])
    people = _number(inputs.get("people"), "Количество людей", setup["limits"]["people"][0], setup["limits"]["people"][1], integer=True)
    air_changes = _number(inputs.get("air_changes"), "Кратность воздухообмена", 0, 100)
    required_flow = _number(inputs.get("required_flow", 0), "Требуемый расход воздуха", 0, 10000000)
    equipment_capacity = _number(inputs.get("equipment_capacity", 0), "Производительность оборудования", 0, 10000000)
    temperature_delta = _number(inputs.get("temperature_delta", 10), "Перепад температуры воздуха", 0, 60)
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
    if raw_value in (None, ""):
      continue
    field_type = field.get("type", "text")
    if field_type == "number":
      try:
        number = float(str(raw_value).replace(",", "."))
      except (TypeError, ValueError):
        return {"ok": False, "message": "Поле «{}» должно быть числом.".format(field.get("label", code))}
      if not math.isfinite(number):
        return {"ok": False, "message": "Поле «{}» содержит некорректное число.".format(field.get("label", code))}
      if field.get("minimum") is not None and number < float(field["minimum"]):
        return {"ok": False, "message": "Поле «{}»: минимум {}.".format(field.get("label", code), field["minimum"])}
      if field.get("maximum") is not None and number > float(field["maximum"]):
        return {"ok": False, "message": "Поле «{}»: максимум {}.".format(field.get("label", code), field["maximum"])}
    elif field_type == "select" and raw_value not in field.get("choices", []):
      return {"ok": False, "message": "Выберите значение для поля «{}».".format(field.get("label", code))}
    elif field_type == "bool" and not isinstance(raw_value, bool):
      return {"ok": False, "message": "Поле «{}» должно иметь значение Да или Нет.".format(field.get("label", code))}
    elif field_type == "text" and (not isinstance(raw_value, str) or len(raw_value) > 500):
      return {"ok": False, "message": "Текст поля «{}» превышает 500 символов.".format(field.get("label", code))}

  rooms = _room_types()
  equipment = _equipment_types()
  systems = _system_types(equipment)
  room = rooms.get(inputs.get("room_type"))
  if room is None:
    return {"ok": False, "message": "Выберите доступное назначение помещения."}
  system_code = inputs.get("ventilation_type")
  system = systems.get(system_code)
  if system is None:
    return {"ok": False, "message": "Выберите доступный тип вентиляции."}
  features = system.get("features", [])
  area_unit = setup["units"]["area"]
  area_to_m2 = 0.09290304 if area_unit == "ft²" else 1.0
  flow_to_m3h = 3.6 if setup["units"]["flow"] == "л/с" else 1.0
  required_flow *= flow_to_m3h
  equipment_capacity *= flow_to_m3h
  area = area_input * area_to_m2
  effective_area = area if area > 0 else length * width
  if effective_area <= 0:
    return {"ok": False, "message": "Укажите площадь или одновременно длину и ширину помещения."}
  minimum_area_m2 = setup["limits"]["area"][0] * area_to_m2
  maximum_area_m2 = setup["limits"]["area"][1] * area_to_m2
  if effective_area < minimum_area_m2 or effective_area > maximum_area_m2:
    return {"ok": False, "message": "Расчётная площадь должна быть от {} до {} {}.".format(
      setup["limits"]["area"][0], setup["limits"]["area"][1], area_unit
    )}
  volume = effective_area * height
  configured_changes = air_changes if air_changes > 0 else room["air_changes"]
  exchange_flow = max(volume * configured_changes, people * _number(_setting("ventilation.people_airflow"), "Расход на человека", 0), required_flow)
  supply_enabled = system["mode"] != "exhaust"
  exhaust_enabled = system["mode"] != "supply"
  supply_flow = exchange_flow * _number(_setting("ventilation.supply_factor"), "Поправка притока", 0) if supply_enabled else 0
  exhaust_flow = exchange_flow * _number(_setting("ventilation.exhaust_factor"), "Поправка вытяжки", 0) if exhaust_enabled else 0
  design_flow = max(supply_flow, exhaust_flow, equipment_capacity)
  heat_capacity = _number(_setting("ventilation.heat_capacity"), "Коэффициент тепла", 0, 10)
  thermal_power_kw = design_flow * temperature_delta * heat_capacity / 1000
  recovery_efficiency = _number(_setting("ventilation.recovery_default"), "Эффективность рекуперации", 0, 100)
  recovery_power_kw = thermal_power_kw * recovery_efficiency / 100 if "recovery" in features else 0
  cooling_capacity_per_unit = _number(
    _setting("ventilation.cooling_capacity_per_unit"), "Холодопроизводительность блока", 0.1, 1000
  )
  fan_flow = design_flow * (1 + _number(_setting("ventilation.fan_reserve_percent"), "Резерв вентилятора", 0) / 100)
  velocity = _number(_setting("ventilation.duct_velocity"), "Скорость в воздуховоде", 0.1)
  duct_area = fan_flow / 3600 / velocity if fan_flow else 0
  diameter = duct_diameter or math.sqrt(4 * duct_area / math.pi) * 1000 if duct_area else 0
  duct_step = max(_number(_setting("ventilation.duct_rounding_step"), "Шаг размеров", 1), 1)
  recommended_diameter = int(math.ceil(diameter / duct_step) * duct_step) if diameter else 0
  recommended_side = int(math.ceil(math.sqrt(duct_area) * 1000 / duct_step) * duct_step) if duct_area else 0
  estimated_grilles = (
    (grilles or max(1, int(math.ceil(supply_flow / 150))))
    if supply_enabled and equipment.get("grille", {}).get("enabled", True) else 0
  )
  estimated_diffusers = (
    (diffusers or max(1, int(math.ceil(supply_flow / 120))))
    if supply_enabled and equipment.get("diffuser", {}).get("enabled", True) else 0
  )
  estimated_fans = (fans or (1 if design_flow else 0)) if equipment.get("fan", {}).get("enabled", True) else 0
  estimated_branches = (branches or max(1, int(math.ceil(design_flow / 500)))) if design_flow else 0
  estimated_recuperators = max(recuperators, 1) if "recovery" in features else recuperators
  estimated_cooling_units = (
    int(math.ceil(thermal_power_kw / cooling_capacity_per_unit))
    if "cooling" in features and thermal_power_kw > 0 else 0
  )

  def price(key):
    return _number(_setting(key), key, 0, 100000000)

  def equipment_price(code, default_key):
    item = equipment.get(code, {})
    if item.get("enabled", True) is False:
      return 0
    return price(item.get("price_key", default_key))

  equipment_cost = price("ventilation.price_equipment_base") * room["factor"] * system["share"]
  equipment_cost += estimated_fans * equipment_price("fan", "ventilation.price_fan")
  equipment_cost += estimated_recuperators * equipment_price("recovery", "ventilation.price_recovery")
  equipment_cost += estimated_cooling_units * equipment_price("cooling", "ventilation.price_cooling")
  filters = filters if equipment.get("filter", {}).get("enabled", True) else 0
  silencers = silencers if equipment.get("silencer", {}).get("enabled", True) else 0
  valves = valves if equipment.get("valve", {}).get("enabled", True) else 0
  automation = automation if equipment.get("automation", {}).get("enabled", True) else 0
  equipment_cost += filters * equipment_price("filter", "ventilation.price_filter")
  equipment_cost += silencers * equipment_price("silencer", "ventilation.price_silencer")
  equipment_cost += valves * equipment_price("valve", "ventilation.price_valve")
  ducts_cost = duct_length * price("ventilation.price_ducts_m2")
  distribution_cost = estimated_grilles * equipment_price("grille", "ventilation.price_grille") + estimated_diffusers * equipment_price("diffuser", "ventilation.price_diffuser")
  automation_cost = automation * equipment_price("automation", "ventilation.price_automation")
  materials_cost = (equipment_cost + ducts_cost + distribution_cost + automation_cost) * price("ventilation.price_materials_percent") / 100
  installation_cost = (equipment_cost * price("ventilation.installation_percent") / 100 + ducts_cost * price("ventilation.duct_installation_percent") / 100) * mounting
  commissioning_cost = installation_cost * price("ventilation.commissioning_percent") / 100
  additional_cost = additional_work + (equipment_cost + ducts_cost) * price("ventilation.additional_percent") / 100
  rounded_equipment = _round(equipment_cost)
  rounded_ducts = _round(ducts_cost)
  rounded_distribution = _round(distribution_cost)
  rounded_automation = _round(automation_cost)
  rounded_materials = _round(materials_cost)
  rounded_installation = _round(installation_cost)
  rounded_commissioning = _round(commissioning_cost)
  rounded_additional = _round(additional_cost)

  breakdown = [
    {"key": "equipment", "label": "Оборудование", "value": rounded_equipment, "unit": "₽"},
    {"key": "ducts", "label": "Воздуховоды", "value": rounded_ducts, "unit": "₽"},
    {"key": "distribution", "label": "Решётки и диффузоры", "value": rounded_distribution, "unit": "₽"},
    {"key": "automation", "label": "Автоматика", "value": rounded_automation, "unit": "₽"},
    {"key": "materials", "label": "Расходные материалы", "value": rounded_materials, "unit": "₽"},
    {"key": "installation", "label": "Монтаж", "value": rounded_installation, "unit": "₽"},
    {"key": "commissioning", "label": "Пусконаладка", "value": rounded_commissioning, "unit": "₽"},
    {"key": "additional", "label": "Дополнительные расходы", "value": rounded_additional, "unit": "₽"}
  ]
  total = sum(row["value"] for row in breakdown)
  return {
    "ok": True,
    "volume": volume,
    "air_exchange": exchange_flow,
    "supply": supply_flow,
    "exhaust": exhaust_flow,
    "fan": fan_flow,
    "cooling_capacity_kw": thermal_power_kw if "cooling" in features else 0,
    "recovery_power_kw": recovery_power_kw,
    "duct_area": duct_area * 10000,
    "duct_diameter": recommended_diameter,
    "duct_rect": "{} × {} мм".format(recommended_side * 2, recommended_side) if recommended_side else "—",
    "counts": {
      "branches": estimated_branches,
      "grilles": estimated_grilles,
      "diffusers": estimated_diffusers,
      "fans": estimated_fans,
      "recuperators": estimated_recuperators,
      "cooling_units": estimated_cooling_units,
      "filters": filters,
      "silencers": silencers,
      "valves": valves,
      "automation": automation
    },
    "equipment_cost": rounded_equipment + rounded_distribution + rounded_automation,
    "installation_cost": rounded_installation + rounded_commissioning,
    "additional_cost": rounded_additional + rounded_materials,
    "total": _round(total),
    "breakdown": breakdown,
    "context": {
      "room": room["name"], "system": system["name"],
      "air_changes": configured_changes,
      "recovery_efficiency": recovery_efficiency if "recovery" in features else 0
    }
  }
