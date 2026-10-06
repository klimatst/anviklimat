import anvil
import anvil.email
import anvil.secrets
import ast
from datetime import datetime, timezone
import json
import math
import re
import uuid
from typing import Any, cast

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import EstimateEngine as Estimates


MODULES = [
  ("Кондиционирование", "ac"),
  ("Монтаж", "installation"),
  ("VRF/VRV", "vrf_vrv"),
  ("Вентиляция", "ventilation"),
  ("Увлажнение", "humidification"),
  ("Осушение", "dehumidification"),
  ("Качество воздуха", "iaq"),
  ("Отопление", "heating"),
  ("Тепловые насосы", "heat_pump"),
  ("Гидравлика", "hydronics"),
  ("Холодоснабжение", "refrigeration"),
  ("Дренаж", "drainage"),
  ("Электрика", "electrical"),
  ("Энергия", "energy")
]
MODULE_NAMES = {code: title for title, code in MODULES}
FUNCTIONS = {
  "abs": abs,
  "min": min,
  "max": max,
  "round": round,
  "sqrt": math.sqrt,
  "log": math.log,
  "log10": math.log10,
  "exp": math.exp,
  "sin": math.sin,
  "cos": math.cos,
  "tan": math.tan
}
CONSTANTS = {"pi": math.pi, "e": math.e}
BIN_OPS = {
  ast.Add: lambda left, right: left + right,
  ast.Sub: lambda left, right: left - right,
  ast.Mult: lambda left, right: left * right,
  ast.Div: lambda left, right: left / right,
  ast.Pow: lambda left, right: left ** right,
  ast.Mod: lambda left, right: left % right
}
UNARY_OPS = {
  ast.UAdd: lambda value: value,
  ast.USub: lambda value: -value
}
ALLOWED_NODES = (
  ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
  ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
  ast.UAdd, ast.USub
)
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
MAX_INPUT_FIELDS = 32
MAX_COEFFICIENTS = 64
MAX_FORMULA_DATA_BYTES = 12000


class FormulaError(Exception):
  pass


SEED_FORMULAS = [
  {
    "code": "ac_room_load_kw",
    "module": "ac",
    "title": "Предварительная нагрузка помещения",
    "expression": "area_m2 * area_kw_per_m2 * height_factor * room_factor * solar_factor * floor_factor + people_count * person_kw + equipment_kw",
    "input_schema": {
      "area_m2": {"label": "Площадь", "unit": "м²", "minimum": 0.1},
      "height_factor": {"label": "Отношение высоты к расчётной", "unit": "—", "minimum": 0.2, "maximum": 4},
      "people_count": {"label": "Люди", "unit": "чел.", "minimum": 0},
      "equipment_kw": {"label": "Тепловыделение оборудования", "unit": "кВт", "minimum": 0},
      "room_factor": {"label": "Коэффициент помещения", "unit": "—", "minimum": 0.1},
      "solar_factor": {"label": "Коэффициент инсоляции", "unit": "—", "minimum": 0.1},
      "floor_factor": {"label": "Коэффициент этажа", "unit": "—", "minimum": 0.1}
    },
    "coefficients": {
      "area_kw_per_m2": 0.1, "design_height_m": 2.7, "person_kw": 0.075,
      "room_apartment": 1.0, "room_house": 1.0, "room_office": 1.05,
      "room_kitchen": 1.1, "room_shop": 1.05, "room_restaurant": 1.1,
      "room_server_room": 1.25, "room_other": 1.0,
      "solar_shade": 1.0, "solar_normal": 1.1, "solar_high": 1.2,
      "floor_regular": 1.0, "floor_top": 1.15
    },
    "output_unit": "кВт",
    "source": "Предварительная оценка по правилу 100 Вт/м² с явным учётом высоты, назначения помещения, инсоляции, этажа, людей и заданного тепловыделения. Это эскизный подбор; проектную нагрузку определяют по расчёту теплопритоков и местным нормам.",
    "version": "HVAC Studio 1.1"
  },
  {
    "code": "ventilation_design_flow",
    "module": "ventilation",
    "title": "Расчётный расход вентиляции",
    "expression": "max(volume_m3 * air_changes_per_hour, people_count * fresh_air_m3_h_person)",
    "input_schema": {
      "volume_m3": {"label": "Объём помещения", "unit": "м³", "minimum": 0},
      "air_changes_per_hour": {"label": "Кратность воздухообмена", "unit": "ч⁻¹", "minimum": 0},
      "people_count": {"label": "Люди", "unit": "чел.", "minimum": 0},
      "fresh_air_m3_h_person": {"label": "Наружный воздух на человека", "unit": "м³/ч·чел.", "minimum": 0}
    },
    "coefficients": {"default_air_changes_per_hour": 1.5, "default_fresh_air_m3_h_person": 30.0},
    "output_unit": "м³/ч",
    "source": "Расход принимается как максимум из объёма × заданная кратность и числа людей × заданный расход на человека. Проектные значения задаются применимыми местными нормами и заданием.",
    "version": "HVAC Studio 1.1"
  },
  {
    "code": "ventilation_duct_area",
    "module": "ventilation",
    "title": "Площадь сечения воздуховода",
    "expression": "airflow_m3_h / (3600 * air_velocity_m_s)",
    "input_schema": {
      "airflow_m3_h": {"label": "Расход воздуха", "unit": "м³/ч", "minimum": 0},
      "air_velocity_m_s": {"label": "Расчётная скорость", "unit": "м/с", "minimum": 0.1, "maximum": 40}
    },
    "coefficients": {"default_air_velocity_m_s": 4.0},
    "output_unit": "м²",
    "source": "Уравнение неразрывности: площадь сечения = объёмный расход / скорость воздуха. Скорость задаёт инженер по акустике и потерям давления.",
    "version": "HVAC Studio 1.1"
  },
  {
    "code": "humidification_saturation_pressure",
    "module": "humidification",
    "title": "Давление насыщенного водяного пара",
    "expression": "saturation_base_kpa * exp(saturation_slope * temperature_c / (temperature_c + saturation_offset_c))",
    "input_schema": {
      "temperature_c": {"label": "Температура воздуха", "unit": "°C", "minimum": -40, "maximum": 80}
    },
    "coefficients": {
      "saturation_base_kpa": 0.61094,
      "saturation_slope": 17.625,
      "saturation_offset_c": 243.04
    },
    "output_unit": "кПа",
    "source": "Приближение Magnus–Tetens для давления насыщенного водяного пара над жидкой водой; не заменяет расчёт по точным психрометрическим данным.",
    "version": "HVAC Studio 1.1"
  },
  {
    "code": "humidification_humidity_ratio",
    "module": "humidification",
    "title": "Влагосодержание воздуха",
    "expression": "molecular_ratio * vapor_pressure_kpa / (barometric_pressure_kpa - vapor_pressure_kpa)",
    "input_schema": {
      "vapor_pressure_kpa": {"label": "Парциальное давление пара", "unit": "кПа", "minimum": 0}
    },
    "coefficients": {"molecular_ratio": 0.62198, "barometric_pressure_kpa": 101.325},
    "output_unit": "кг/кг сухого воздуха",
    "source": "Психрометрическое соотношение для влагосодержания влажного воздуха; давление принято 101,325 кПа и должно быть скорректировано для высоты над уровнем моря.",
    "version": "HVAC Studio 1.1"
  },
  {
    "code": "installation_work_cost",
    "module": "installation",
    "title": "Работы по монтажу",
    "expression": "equipment_count * rate_per_unit * complexity_factor + route_length_m * route_rate_per_m * complexity_factor + floor_count * rate_per_floor",
    "input_schema": {
      "equipment_count": {"label": "Количество оборудования", "unit": "шт.", "minimum": 0},
      "route_length_m": {"label": "Длина трассы или воздуховода", "unit": "м", "minimum": 0},
      "complexity_factor": {"label": "Коэффициент сложности", "unit": "—", "minimum": 0.1, "maximum": 10},
      "floor_count": {"label": "Этажность", "unit": "этажей", "minimum": 1}
    },
    "coefficients": {
      "rate_per_unit": 0.0, "route_rate_per_m": 0.0, "rate_per_floor": 0.0,
      "difficulty_standard": 1.0, "difficulty_limited_access": 1.25,
      "difficulty_height_work": 1.5
    },
    "output_unit": "вал. ед.",
    "source": "Предварительная смета по локальным тарифам в коэффициентах формулы ADMIN. Переменные расчёта отделены от расценок и коэффициентов.",
    "version": "HVAC Studio 1.2"
  },
  {
    "code": "air_sensible_load_kw",
    "module": "ac",
    "title": "Явная тепловая нагрузка воздуха",
    "expression": "air_density * air_heat_capacity * airflow_m3_s * delta_t_k",
    "input_schema": {
      "airflow_m3_s": {"label": "Расход воздуха", "unit": "м³/с", "minimum": 0},
      "delta_t_k": {"label": "Разность температур", "unit": "K", "minimum": 0}
    },
    "coefficients": {"air_density": 1.2, "air_heat_capacity": 1.006},
    "output_unit": "кВт",
    "source": "ASHRAE Handbook—Fundamentals (2021), Psychrometrics: Q = ρ·cp·V̇·ΔT; dry-air design approximation ρ=1.2 kg/m³, cp=1.006 kJ/(kg·K).",
    "version": "ASHRAE 2021 / HVAC Studio 1.0"
  },
  {
    "code": "ventilation_airflow_ach",
    "module": "ventilation",
    "title": "Расход воздуха по кратности",
    "expression": "room_volume_m3 * air_changes_per_hour",
    "input_schema": {
      "room_volume_m3": {"label": "Объём помещения", "unit": "м³", "minimum": 0},
      "air_changes_per_hour": {"label": "Расчётная кратность", "unit": "ч⁻¹", "minimum": 0}
    },
    "coefficients": {},
    "output_unit": "м³/ч",
    "source": "Air-change definition: volumetric airflow = room volume × specified air changes per hour. Set the design rate from applicable local code and project requirements.",
    "version": "HVAC Studio 1.0"
  },
  {
    "code": "humidification_water_flow",
    "module": "humidification",
    "title": "Производительность увлажнения",
    "expression": "air_density * airflow_m3_s * humidity_ratio_delta * 3600",
    "input_schema": {
      "airflow_m3_s": {"label": "Расход воздуха", "unit": "м³/с", "minimum": 0},
      "humidity_ratio_delta": {"label": "Прирост влагосодержания", "unit": "кг/кг", "minimum": 0}
    },
    "coefficients": {"air_density": 1.2},
    "output_unit": "кг/ч",
    "source": "Moist-air mass balance: water rate = dry-air mass flow × humidity-ratio increase. Air density 1.2 kg/m³ is an explicit design approximation.",
    "version": "HVAC Studio 1.0"
  },
  {
    "code": "electrical_input_from_cop",
    "module": "energy",
    "title": "Электрическая мощность по COP",
    "expression": "thermal_capacity_kw / cop",
    "input_schema": {
      "thermal_capacity_kw": {"label": "Тепловая мощность", "unit": "кВт", "minimum": 0},
      "cop": {"label": "COP при расчётных условиях", "unit": "—", "minimum": 0.000001}
    },
    "coefficients": {},
    "output_unit": "кВт",
    "source": "Coefficient of performance definition: COP = delivered thermal power / electrical input power. Use manufacturer COP at the design point.",
    "version": "HVAC Studio 1.0"
  },
  {
    "code": "installation_cost_estimate",
    "module": "installation",
    "title": "Предварительная стоимость монтажа",
    "expression": "equipment_cost + piping_length_m * piping_rate + labor_hours * hourly_rate + consumables_cost",
    "input_schema": {
      "equipment_cost": {"label": "Оборудование по смете", "unit": "вал. ед.", "minimum": 0},
      "piping_length_m": {"label": "Длина трассы", "unit": "м", "minimum": 0},
      "piping_rate": {"label": "Монтаж трассы за метр", "unit": "вал. ед./м", "minimum": 0},
      "labor_hours": {"label": "Трудоёмкость", "unit": "ч", "minimum": 0},
      "hourly_rate": {"label": "Ставка работ за час", "unit": "вал. ед./ч", "minimum": 0},
      "consumables_cost": {"label": "Расходные материалы", "unit": "вал. ед.", "minimum": 0}
    },
    "coefficients": {},
    "output_unit": "вал. ед.",
    "source": "Parametric estimate using user-supplied equipment amount, installed length, labor hours, rates, and consumables; taxes, access equipment, and contingencies are excluded.",
    "version": "HVAC Studio 1.0"
  }
]


def _ensure_seed_formulas():
  now = datetime.now(timezone.utc)
  created = []
  for values in SEED_FORMULAS:
    existing = app_tables.formulas.get(code=values["code"])
    if existing is not None:
      if (
        values["code"] == "installation_work_cost"
        and existing["version"] == "HVAC Studio 1.1"
        and existing["expression"] == values["expression"]
        and existing["source"] == "Предварительная смета по локальным тарифам, которые задаёт ADMIN в коэффициентах формулы. Уровни сложности — начальные коэффициенты сметы и должны быть откалиброваны под регламент и расценки организации."
      ):
        existing.update(
          input_schema=values["input_schema"],
          source=values["source"],
          version=values["version"],
          updated_at=now
        )
      continue
    row_values = dict(values)
    row_values.update(enabled=True, updated_at=now)
    app_tables.formulas.add_row(**row_values)
    created.append(values["code"])
  if created:
    Core.log_audit(
      actor=None,
      action="calculation.seed_formulas_created",
      entity_type="formula",
      entity_id="",
      details={"codes": created},
      created_at=now
    )


def _current_user():
  user = anvil.users.get_user()
  if user is not None:
    Core._ensure_core_data(user)
  return user


def _admin_user():
  return Core.get_admin_user()


def _decode_mapping(raw, label):
  if isinstance(raw, dict):
    return raw, None
  if not isinstance(raw, str):
    return None, "Поле «{}» должно быть JSON-объектом.".format(label)
  if len(raw.encode("utf-8")) > MAX_FORMULA_DATA_BYTES:
    return None, "JSON в поле «{}» превышает допустимый размер.".format(label)
  try:
    decoded = json.loads(raw)
  except json.JSONDecodeError:
    return None, "Проверьте JSON в поле «{}».".format(label)
  if not isinstance(decoded, dict):
    return None, "Поле «{}» должно быть JSON-объектом.".format(label)
  return decoded, None


def _finite_number(value):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return False
  try:
    return math.isfinite(float(value))
  except (OverflowError, TypeError, ValueError):
    return False


def _validate_input_schema(input_schema):
  if not isinstance(input_schema, dict):
    return "Схема входных данных должна быть JSON-объектом."
  if len(input_schema) > MAX_INPUT_FIELDS:
    return "Формула может содержать не более {} входных параметров.".format(MAX_INPUT_FIELDS)
  reserved = set(FUNCTIONS) | set(CONSTANTS)
  for key, definition in input_schema.items():
    if (
      not isinstance(key, str) or not IDENTIFIER.fullmatch(key)
      or key.startswith("_") or key in reserved
    ):
      return "Названия входных параметров должны быть незарезервированными латинскими идентификаторами."
    if not isinstance(definition, dict):
      return "Описание входного параметра «{}» должно быть объектом.".format(key)
    if set(definition) - {"label", "unit", "required", "minimum", "maximum"}:
      return "Описание параметра «{}» содержит неподдерживаемые поля.".format(key)
    label = definition.get("label")
    unit = definition.get("unit", "")
    required = definition.get("required", True)
    if not isinstance(label, str) or not label.strip() or len(label) > 80:
      return "Укажите короткое название для параметра «{}».".format(key)
    if not isinstance(unit, str) or len(unit) > 32 or not isinstance(required, bool):
      return "Проверьте единицу измерения и обязательность «{}».".format(key)
    for bound in ("minimum", "maximum"):
      if bound in definition and not _finite_number(definition[bound]):
        return "Предел «{}» для параметра «{}» должен быть числом.".format(bound, key)
    if (
      "minimum" in definition and "maximum" in definition
      and definition["minimum"] > definition["maximum"]
    ):
      return "Минимум не может быть больше максимума для «{}».".format(key)
  return None


def _validate_coefficients(coefficients):
  if not isinstance(coefficients, dict):
    return "Коэффициенты должны быть JSON-объектом."
  if len(coefficients) > MAX_COEFFICIENTS:
    return "Формула может содержать не более {} коэффициентов.".format(MAX_COEFFICIENTS)
  reserved = set(FUNCTIONS) | set(CONSTANTS)
  for key, value in coefficients.items():
    if (
      not isinstance(key, str) or not IDENTIFIER.fullmatch(key)
      or key.startswith("_") or key in reserved
    ):
      return "Названия коэффициентов должны быть уникальными латинскими идентификаторами."
    if not _finite_number(value):
      return "Коэффициент «{}» должен быть конечным числом.".format(key)
  return None


def _parse_expression(expression, input_schema, coefficients):
  if not isinstance(expression, str) or not expression.strip() or len(expression) > 2000:
    raise FormulaError("Укажите формулу длиной не более 2000 символов.")
  try:
    tree = ast.parse(expression, mode="eval")
  except (SyntaxError, ValueError):
    raise FormulaError("В формуле есть синтаксическая ошибка.")
  nodes = list(ast.walk(tree))
  if len(nodes) > 120:
    raise FormulaError("Формула слишком сложная.")

  known_names = set(input_schema) | set(coefficients) | set(CONSTANTS)
  for node in nodes:
    if not isinstance(node, ALLOWED_NODES):
      raise FormulaError("Формула использует неподдерживаемую операцию.")
    if isinstance(node, ast.Name):
      if node.id not in known_names and node.id not in FUNCTIONS:
        raise FormulaError("Неизвестный параметр «{}» в формуле.".format(node.id))
    elif isinstance(node, ast.Constant):
      if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
        raise FormulaError("В формуле разрешены только числовые константы.")
      if not _finite_number(node.value):
        raise FormulaError("Числовая константа в формуле должна быть конечной.")
    elif isinstance(node, ast.Call):
      if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
        raise FormulaError("В формуле вызвана неподдерживаемая функция.")
      argument_count = len(node.args)
      if node.func.id in ("min", "max") and argument_count < 1:
        raise FormulaError("Функция «{}» требует хотя бы один параметр.".format(node.func.id))
      if node.func.id == "round" and argument_count not in (1, 2):
        raise FormulaError("Функция «round» принимает один или два параметра.")
      if node.func.id == "log" and argument_count not in (1, 2):
        raise FormulaError("Функция «log» принимает один или два параметра.")
      if node.func.id not in ("min", "max", "round", "log") and argument_count != 1:
        raise FormulaError("Функция «{}» принимает один параметр.".format(node.func.id))
  return tree


def _evaluate(node, values):
  if isinstance(node, ast.Expression):
    return _evaluate(node.body, values)
  if isinstance(node, ast.Constant):
    return float(node.value)
  if isinstance(node, ast.Name):
    if node.id in values:
      return values[node.id]
    if node.id in CONSTANTS:
      return CONSTANTS[node.id]
    raise FormulaError("Не задан параметр «{}».".format(node.id))
  if isinstance(node, ast.BinOp):
    left = _evaluate(node.left, values)
    right = _evaluate(node.right, values)
    if isinstance(node.op, ast.Pow) and abs(right) > 24:
      raise FormulaError("Степень формулы не должна превышать 24.")
    operation = BIN_OPS.get(type(node.op))
    if operation is None:
      raise FormulaError("Формула использует неподдерживаемую операцию.")
    result = operation(left, right)
    if isinstance(result, bool) or not isinstance(result, (int, float)) or not math.isfinite(float(result)):
      raise FormulaError("Формула должна возвращать конечное вещественное число.")
    return result
  if isinstance(node, ast.UnaryOp):
    operation = UNARY_OPS.get(type(node.op))
    if operation is None:
      raise FormulaError("Формула использует неподдерживаемую операцию.")
    return operation(_evaluate(node.operand, values))
  if isinstance(node, ast.Call):
    if not isinstance(node.func, ast.Name):
      raise FormulaError("В формуле вызвана неподдерживаемая функция.")
    function = FUNCTIONS[node.func.id]
    return function(*[_evaluate(arg, values) for arg in node.args])
  raise FormulaError("Формула содержит неподдерживаемый элемент.")


def _validate_formula_content(expression, input_schema, coefficients):
  error = _validate_input_schema(input_schema)
  if error:
    return error
  error = _validate_coefficients(coefficients)
  if error:
    return error
  if set(input_schema) & set(coefficients):
    return "Названия входных параметров и коэффициентов должны различаться."
  try:
    encoded_data = json.dumps(
      {"input_schema": input_schema, "coefficients": coefficients},
      ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
  except (TypeError, ValueError):
    return "Схема и коэффициенты должны содержать только данные JSON."
  if len(encoded_data) > MAX_FORMULA_DATA_BYTES:
    return "Объём схемы и коэффициентов превышает допустимый размер."
  try:
    _parse_expression(expression, input_schema, coefficients)
  except FormulaError as error:
    return str(error)
  return None


def _compute(formula, raw_inputs):
  input_schema = formula["input_schema"] or {}
  coefficients = formula["coefficients"] or {}
  error = _validate_formula_content(formula["expression"], input_schema, coefficients)
  if error:
    return {"ok": False, "message": "Формула не прошла проверку: " + error}
  if not isinstance(raw_inputs, dict):
    return {"ok": False, "message": "Входные данные должны быть объектом."}
  unknown = set(raw_inputs) - set(input_schema)
  if unknown:
    return {"ok": False, "message": "Получен неизвестный входной параметр."}

  values = dict(coefficients)
  normalized_inputs = {}
  units = {}
  for key, definition in input_schema.items():
    raw = raw_inputs.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
      if definition.get("required", True):
        return {"ok": False, "message": "Заполните параметр «{}».".format(definition["label"])}
      continue
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
      return {"ok": False, "message": "Проверьте значение параметра «{}».".format(definition["label"])}
    try:
      number = float(str(raw).replace(" ", "").replace(",", "."))
    except ValueError:
      return {"ok": False, "message": "Проверьте значение параметра «{}».".format(definition["label"])}
    if not math.isfinite(number):
      return {"ok": False, "message": "Значение «{}» должно быть конечным числом.".format(definition["label"])}
    if "minimum" in definition and number < definition["minimum"]:
      return {"ok": False, "message": "Значение «{}» ниже допустимого минимума.".format(definition["label"])}
    if "maximum" in definition and number > definition["maximum"]:
      return {"ok": False, "message": "Значение «{}» выше допустимого максимума.".format(definition["label"])}
    normalized_inputs[key] = number
    values[key] = number
    units[key] = definition.get("unit", "")

  try:
    tree = _parse_expression(formula["expression"], input_schema, coefficients)
    result = float(_evaluate(tree, values))
  except FormulaError as error:
    return {"ok": False, "message": str(error)}
  except (ArithmeticError, TypeError, ValueError):
    return {"ok": False, "message": "Формула не определена для этих входных данных."}
  if not math.isfinite(result):
    return {"ok": False, "message": "Расчёт дал не конечный результат."}
  units["result"] = formula["output_unit"] or ""
  return {
    "ok": True,
    "result": result,
    "inputs": normalized_inputs,
    "coefficients": dict(coefficients),
    "units": units,
    "source": formula["source"],
    "version": formula["version"],
    "output_unit": formula["output_unit"] or ""
  }


@anvil.server.callable
def get_calculation_catalog(include_disabled=False):
  _ensure_seed_formulas()
  user = _current_user()
  can_edit = Core.has_permission(user, "calculations.manage")
  show_disabled = bool(include_disabled) and can_edit
  filters = {} if show_disabled else {"enabled": True}
  formulas = [
    {
      "code": row["code"],
      "module": row["module"],
      "module_title": MODULE_NAMES.get(row["module"], row["module"]),
      "title": row["title"],
      "input_schema": row["input_schema"] or {},
      "output_unit": row["output_unit"] or "",
      "source": row["source"],
      "version": row["version"],
      "enabled": row["enabled"]
    }
    for row in app_tables.formulas.search(
      q.fetch_only(
        "code", "module", "title", "input_schema", "output_unit",
        "source", "version", "enabled"
      ),
      order_by("module"),
      **filters
    )[:100]
  ]
  return {"ok": True, "modules": MODULES, "formulas": formulas, "can_edit": can_edit}


@anvil.server.callable(require_user=True)
@Core.permission_guard("calculations.manage")
def get_formula_details(code):
  if not isinstance(code, str) or not code:
    return {"ok": False, "message": "Некорректный код формулы."}
  row = app_tables.formulas.get(code=code)
  if row is None:
    return {"ok": False, "message": "Формула не найдена."}
  return {
    "ok": True,
    "code": row["code"],
    "module": row["module"],
    "title": row["title"],
    "expression": row["expression"],
    "input_schema": json.dumps(row["input_schema"] or {}, ensure_ascii=False, sort_keys=True),
    "coefficients": json.dumps(row["coefficients"] or {}, ensure_ascii=False, sort_keys=True),
    "output_unit": row["output_unit"] or "",
    "source": row["source"],
    "version": row["version"],
    "enabled": row["enabled"]
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("calculations.manage")
def save_formula(code, module, title, expression, input_schema_raw, coefficients_raw,
                 output_unit, source, version, enabled):
  user = Core.require_permission("calculations.manage")
  if not isinstance(code, str) or not IDENTIFIER.fullmatch(code):
    return {"ok": False, "message": "Код формулы должен быть латинским идентификатором."}
  if not isinstance(module, str) or module not in MODULE_NAMES:
    return {"ok": False, "message": "Выберите доступный модуль расчёта."}
  for value, label, maximum in (
    (title, "Название", 120),
    (output_unit, "Выходная единица измерения", 32),
    (source, "Источник", 300),
    (version, "Версия источника", 80)
  ):
    if not isinstance(value, str) or len(value.strip()) > maximum:
      return {"ok": False, "message": "Проверьте поле «{}».".format(label)}
  title = title.strip()
  source = source.strip()
  version = version.strip()
  output_unit = output_unit.strip()
  if not title or not source or not version:
    return {"ok": False, "message": "Укажите название, проверяемый источник и его версию."}
  if not isinstance(enabled, bool):
    return {"ok": False, "message": "Некорректное состояние формулы."}

  input_schema, error = _decode_mapping(input_schema_raw, "Входные данные")
  if error:
    return {"ok": False, "message": error}
  coefficients, error = _decode_mapping(coefficients_raw, "Коэффициенты")
  if error:
    return {"ok": False, "message": error}
  error = _validate_formula_content(expression, input_schema, coefficients)
  if error:
    return {"ok": False, "message": error}

  now = datetime.now(timezone.utc)
  row = app_tables.formulas.get(code=code)
  values = {
    "module": module,
    "title": title,
    "expression": expression.strip(),
    "input_schema": input_schema,
    "coefficients": coefficients,
    "output_unit": output_unit,
    "source": source,
    "version": version,
    "enabled": enabled,
    "updated_at": now,
    "updated_by": user
  }
  if row is None:
    row = app_tables.formulas.add_row(code=code, **values)
    action = "calculation.formula_created"
  else:
    row.update(**values)
    action = "calculation.formula_updated"
  Core.log_audit(
    actor=user,
    action=action,
    entity_type="formula",
    entity_id=row.get_id(),
    details={"code": code, "module": module, "version": version, "enabled": enabled},
    created_at=now
  )
  return {"ok": True, "message": "Формула сохранена.", "code": code}


@anvil.server.callable
def run_calculation(code, inputs, save_result=False, expected_version=None,
                    project_id=None, system_id=None):
  user = _current_user()
  if not isinstance(code, str) or not code:
    return {"ok": False, "message": "Выберите формулу."}
  if not isinstance(save_result, bool):
    return {"ok": False, "message": "Некорректная команда сохранения."}
  formula = app_tables.formulas.get(code=code)
  if formula is None or not formula["enabled"]:
    return {"ok": False, "message": "Формула недоступна."}
  if expected_version is not None and formula["version"] != expected_version:
    return {"ok": False, "message": "Версия формулы изменилась. Выполните расчёт заново."}
  if project_id is not None and (
    not isinstance(project_id, str) or not project_id
  ):
    return {"ok": False, "message": "Некорректный идентификатор проекта."}
  if system_id is not None and (
    not isinstance(system_id, str) or not system_id
  ):
    return {"ok": False, "message": "Некорректный идентификатор системы."}
  project = app_tables.projects.get_by_id(project_id) if project_id else None
  if project_id and project is None:
    return {"ok": False, "message": "Проект не найден."}
  if project is not None and not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проектные расчёты доступны только владельцу проекта."}
  system = app_tables.systems.get_by_id(system_id) if system_id else None
  if system_id and system is None:
    return {"ok": False, "message": "Система не найдена."}
  if system is not None:
    system_project = system["project"]
    if system_project is None:
      return {"ok": False, "message": "Система не связана с проектом."}
    if not Core.can_access_project(system_project, user):
      return {"ok": False, "message": "Система недоступна этой учётной записи."}
    if project is not None and project.get_id() != system_project.get_id():
      return {"ok": False, "message": "Система не принадлежит выбранному проекту."}
    project = system_project
  computed = _compute(formula, inputs)
  if not computed["ok"]:
    return computed
  calculation_id = None
  if save_result:
    if user is None:
      return {"ok": False, "message": "Для сохранения результата войдите в систему."}
    row = app_tables.calculations.add_row(
      formula=formula,
      inputs=computed["inputs"],
      coefficients=computed["coefficients"],
      units=computed["units"],
      result=computed["result"],
      source=computed["source"],
      version=computed["version"],
      created_by=user,
      created_at=datetime.now(timezone.utc)
    )
    if project is not None:
      row["project"] = project
    if system is not None:
      row["system"] = system
    calculation_id = row.get_id()
  computed["calculation_id"] = calculation_id
  return computed


@anvil.server.callable(require_user=True)
def get_project_calculation_context(project_id):
  user = _current_user()
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None or not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  obj = project["object"]
  parameters = (obj["parameters"] or {}) if obj is not None else {}
  rooms = []
  if obj is not None:
    for room in app_tables.rooms.search(
      q.fetch_only("name", "area", "height", "parameters"),
      order_by("name"), object=obj
    )[:20]:
      room_parameters = room["parameters"] or {}
      rooms.append({
        "id": room.get_id(),
        "name": room["name"] or "",
        "area": room["area"],
        "height": room["height"],
        "parameters": room_parameters
      })
  profile = parameters.get("engineering_profile") or "combined"
  profile_to_calculation = {
    "combined": "ac",
    "vrv_vrf": "vrf_vrv",
    "ventilation": None,
    "split_multi": "ac"
  }
  return {
    "ok": True,
    "project": {
      "id": project.get_id(),
      "code": project["code"],
      "title": project["title"],
      "status": project["status"],
      "object_name": obj["name"] if obj is not None else "",
      "engineering_profile": profile,
      "calculation_profile": profile_to_calculation.get(profile, "ac"),
      "engineering_goal": parameters.get("engineering_goal") or "design",
      "project_priority": parameters.get("project_priority") or "standard",
      "constraints": parameters.get("constraints") or "",
      "rooms": rooms
    }
  }


HVAC_PROFILES = [
  {"code": "ac", "title": "Кондиционеры", "formula": "ac_room_load_kw"},
  {"code": "vrf_vrv", "title": "VRV / VRF", "formula": "ac_room_load_kw"},
  {"code": "ventilation", "title": "Вентиляция", "formula": "ventilation_design_flow"}
]
ROOM_TYPE_FACTORS = {
  "apartment": "room_apartment", "house": "room_house",
  "office": "room_office", "kitchen": "room_kitchen",
  "shop": "room_shop", "restaurant": "room_restaurant",
  "server_room": "room_server_room", "other": "room_other"
}
ROOM_TYPE_TITLES = [
  ("Квартира", "apartment"), ("Дом", "house"), ("Офис", "office"),
  ("Кухня", "kitchen"), ("Магазин", "shop"),
  ("Ресторан", "restaurant"), ("Серверная", "server_room"),
  ("Другое", "other")
]
PRODUCT_CAPACITY_SPECS = {
  "ac": (
    "cooling_capacity_kw", "cooling capacity", "мощность охлаждения",
    "холодопроизводительность"
  ),
  "vrf_vrv": (
    "cooling_capacity_kw", "cooling capacity", "мощность охлаждения",
    "холодопроизводительность"
  ),
  "ventilation": (
    "airflow_m3_h", "air_flow_m3_h", "airflow", "расход воздуха"
  ),
  "humidification": (
    "humidification_capacity_kg_h", "production_kg_h", "capacity_kg_h",
    "производительность увлажнения", "паропроизводительность"
  ),
  "engineering": (
    "cooling_capacity_kw", "cooling capacity", "мощность охлаждения",
    "холодопроизводительность"
  )
}
PRODUCT_SPEC_ALIASES = {
  "factory_pipe_length_m": (
    "factory_pipe_length_m", "included_pipe_length_m", "предзаправленная длина"
  ),
  "additional_refrigerant_g_per_m": (
    "additional_refrigerant_g_per_m", "refrigerant_charge_g_m",
    "дозаправка г/м", "дозаправка г/м трассы"
  ),
  "max_pipe_length_m": (
    "max_pipe_length_m", "maximum_pipe_length_m", "максимальная длина трассы"
  ),
  "max_height_difference_m": (
    "max_height_difference_m", "max_vertical_difference_m", "максимальный перепад высот"
  ),
  "liquid_pipe_diameter": (
    "liquid_pipe_diameter", "liquid_pipe_size", "диаметр жидкостной трубы",
    "диаметр жидкостной линии"
  ),
  "gas_pipe_diameter": (
    "gas_pipe_diameter", "gas_pipe_size", "диаметр газовой трубы",
    "диаметр газовой линии"
  )
}
PRODUCT_CATEGORY_CODES = {
  "ac": ("air-conditioning",),
  "vrf_vrv": ("vrf-vrv",),
  "ventilation": ("ventilation",),
  "humidification": ("humidification",),
  "engineering": ("air-conditioning", "vrf-vrv")
}


def _engine_number(raw, label, minimum, maximum, integer=False):
  if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
    return None, "Проверьте поле «{}».".format(label)
  try:
    value = float(str(raw).replace(" ", "").replace(",", "."))
  except ValueError:
    return None, "Проверьте поле «{}».".format(label)
  if not math.isfinite(value) or value < minimum or value > maximum:
    return None, "Поле «{}» вне допустимого диапазона.".format(label)
  if integer and not value.is_integer():
    return None, "Поле «{}» должно быть целым числом.".format(label)
  return int(value) if integer else value, None


def _formula_row(code):
  row = app_tables.formulas.get(code=code)
  if row is None or not row["enabled"]:
    return None
  return row


def _engine_input(formula, key, value):
  return _compute(formula, {key: value})


def _normalize_engine_inputs(profile, raw):
  if not isinstance(raw, dict) or len(raw) > 32:
    return None, "Параметры расчёта должны быть небольшим объектом."
  raw_values = dict(raw)
  assumptions = []

  def missing(value):
    return value is None or (isinstance(value, str) and not value.strip())

  area, error = _engine_number(raw_values.get("area_m2"), "Площадь", 0.1, 1000000)
  if error:
    return None, error
  if area is None:
    return None, "Укажите площадь помещения."
  raw_values["area_m2"] = area

  formula = _formula_row("ac_room_load_kw")
  coefficients = formula["coefficients"] if formula is not None else {}
  defaults = {
    "height_m": (coefficients or {}).get("design_height_m", 2.7),
    "people_count": int(math.ceil(area / 20.0)),
    "equipment_kw": 0.0
  }
  for key, value in defaults.items():
    if missing(raw_values.get(key)):
      raw_values[key] = value
      labels = {
        "height_m": "высота помещения",
        "people_count": "число людей оценено как 1 человек на 20 м²",
        "equipment_kw": "тепловыделение оборудования принято равным 0 кВт"
      }
      assumptions.append("Допущение: {} — {}.".format(labels[key], value))

  if profile == "vrf_vrv":
    estimated_units = min(500, max(1, int(math.ceil(area / 25.0))))
    if missing(raw_values.get("indoor_unit_count")):
      raw_values["indoor_unit_count"] = estimated_units
      assumptions.append("Допущение: количество внутренних блоков оценено по одному блоку на 25 м².")
    units = raw_values["indoor_unit_count"]
    try:
      units = max(1, int(float(str(units).replace(",", "."))))
    except (TypeError, ValueError, OverflowError):
      units = estimated_units
    route_estimate = round(max(5.0, math.sqrt(area / units) * 1.5) * units, 1)
    for key, value, label in (
      ("route_length_m", route_estimate, "суммарная длина трасс оценена по площади и числу блоков"),
      ("height_difference_m", 3.0, "перепад высот принят равным 3 м")
    ):
      if missing(raw_values.get(key)):
        raw_values[key] = value
        assumptions.append("Допущение: {}.".format(label))

  if profile == "ventilation":
    for key, value, label in (
      ("air_changes_per_hour", 1.5, "кратность воздухообмена принята равной 1,5 ч⁻¹"),
      ("fresh_air_m3_h_person", 30.0, "наружный воздух принят равным 30 м³/ч на человека"),
      ("air_velocity_m_s", 4.0, "скорость в воздуховоде принята равной 4 м/с"),
      ("supply_balance_pct", 100.0, "баланс притока принят равным 100%"),
      ("exhaust_balance_pct", 100.0, "баланс вытяжки принят равным 100%")
    ):
      if missing(raw_values.get(key)):
        raw_values[key] = value
        assumptions.append("Допущение: {}.".format(label))

  result = {}
  number_fields = [
    ("area_m2", "Площадь", 0.1, 1000000, False),
    ("height_m", "Высота", 1, 30, False),
    ("people_count", "Количество людей", 0, 100000, True),
    ("equipment_kw", "Тепловыделение оборудования", 0, 1000000, False)
  ]
  if profile in ("vrf_vrv",):
    number_fields.extend([
      ("indoor_unit_count", "Количество внутренних блоков", 1, 500, True),
      ("route_length_m", "Длина трасс", 0, 100000, False),
      ("height_difference_m", "Перепад высот", 0, 10000, False)
    ])
  if profile in ("ventilation", "engineering", "humidification"):
    number_fields.extend([
      ("air_changes_per_hour", "Кратность воздухообмена", 0, 1000, False),
      ("fresh_air_m3_h_person", "Наружный воздух на человека", 0, 10000, False),
      ("air_velocity_m_s", "Скорость воздуха в воздуховоде", 0.1, 40, False),
      ("supply_balance_pct", "Баланс притока", 0, 200, False),
      ("exhaust_balance_pct", "Баланс вытяжки", 0, 200, False)
    ])
  if profile == "humidification":
    number_fields.extend([
      ("supply_temperature_c", "Температура приточного воздуха", -40, 80, False),
      ("supply_relative_humidity_pct", "Влажность приточного воздуха", 0, 100, False),
      ("target_temperature_c", "Целевая температура", -40, 80, False),
      ("target_relative_humidity_pct", "Целевая влажность", 0, 100, False)
    ])

  for key, label, minimum, maximum, integer in number_fields:
    value, error = _engine_number(raw_values.get(key), label, minimum, maximum, integer)
    if error:
      return None, error
    result[key] = value

  choices = {
    "room_type": set(ROOM_TYPE_FACTORS),
    "floor_type": {"regular", "top"},
    "exposure": {"shade", "normal", "high"}
  }
  defaults = {"room_type": "apartment", "floor_type": "regular", "exposure": "normal"}
  for key, allowed in choices.items():
    value = raw_values.get(key, defaults[key])
    if not isinstance(value, str) or value not in allowed:
      return None, "Выберите допустимое значение поля «{}».".format(key)
    result[key] = value
  room_name = raw_values.get("room_name", "")
  if not isinstance(room_name, str) or len(room_name.strip()) > 120:
    return None, "Название помещения должно быть короче 120 символов."
  result["room_name"] = room_name.strip()
  result["_assumptions"] = assumptions
  return result, None


def _cooling_load(common):
  formula = _formula_row("ac_room_load_kw")
  if formula is None:
    return None, {"ok": False, "message": "Формула тепловой нагрузки выключена или отсутствует."}
  coefficients = formula["coefficients"] or {}
  design_height, error = _engine_number(
    coefficients.get("design_height_m"), "Расчётная высота", 0.1, 100
  )
  if error:
    return None, {"ok": False, "message": error}
  factor_key = ROOM_TYPE_FACTORS[common["room_type"]]
  room_factor = coefficients.get(factor_key)
  solar_factor = coefficients.get("solar_" + common["exposure"])
  floor_factor = coefficients.get(
    "floor_top" if common["floor_type"] == "top" else "floor_regular"
  )
  for value, label in (
    (room_factor, "тип помещения"),
    (solar_factor, "инсоляция"),
    (floor_factor, "тип этажа"),
    (coefficients.get("area_kw_per_m2"), "нагрузка на площадь"),
    (coefficients.get("person_kw"), "теплоприток от человека")
  ):
    if not _finite_number(value) or not isinstance(value, (int, float)) or value < 0:
      return None, {"ok": False, "message": "Проверьте коэффициент «{}» формулы.".format(label)}

  values = {
    "area_m2": common["area_m2"],
    "height_factor": common["height_m"] / design_height,
    "people_count": common["people_count"],
    "equipment_kw": common["equipment_kw"],
    "room_factor": room_factor,
    "solar_factor": solar_factor,
    "floor_factor": floor_factor
  }
  computed = _compute(formula, values)
  if not computed["ok"]:
    return None, computed
  area_kw = (
    common["area_m2"] * coefficients["area_kw_per_m2"]
    * values["height_factor"] * room_factor * solar_factor * floor_factor
  )
  people_kw = common["people_count"] * coefficients["person_kw"]
  details = [
    {"label": "Площадь и профиль помещения", "value": round(area_kw, 3), "unit": "кВт"},
    {"label": "Люди", "value": round(people_kw, 3), "unit": "кВт"},
    {"label": "Тепловыделение оборудования", "value": common["equipment_kw"], "unit": "кВт"}
  ]
  return {
    "value": computed["result"],
    "unit": "кВт",
    "formula": formula,
    "inputs": values,
    "coefficients": coefficients,
    "components": details,
    "source": formula["source"],
    "version": formula["version"]
  }, None


def _ventilation_load(common, params):
  formula = _formula_row("ventilation_design_flow")
  if formula is None:
    return None, {"ok": False, "message": "Формула расхода вентиляции выключена или отсутствует."}
  coefficients = formula["coefficients"] or {}
  default_ach = coefficients.get("default_air_changes_per_hour")
  default_per_person = coefficients.get("default_fresh_air_m3_h_person")
  ach = params.get("air_changes_per_hour", default_ach)
  per_person = params.get("fresh_air_m3_h_person", default_per_person)
  velocity_formula = _formula_row("ventilation_duct_area")
  if velocity_formula is None:
    return None, {"ok": False, "message": "Формула воздуховода выключена или отсутствует."}
  default_velocity = (velocity_formula["coefficients"] or {}).get("default_air_velocity_m_s")
  velocity = params.get("air_velocity_m_s", default_velocity)
  for value, label in (
    (ach, "кратность воздухообмена"),
    (per_person, "расход наружного воздуха на человека"),
    (velocity, "скорость в воздуховоде")
  ):
    if not _finite_number(value) or value <= 0:
      return None, {"ok": False, "message": "Задайте коэффициент «{}» больше нуля.".format(label)}
  volume = common["area_m2"] * common["height_m"]
  flow_input = {
    "volume_m3": volume,
    "air_changes_per_hour": ach,
    "people_count": common["people_count"],
    "fresh_air_m3_h_person": per_person
  }
  flow = _compute(formula, flow_input)
  if not flow["ok"]:
    return None, flow
  duct_area_input = {"airflow_m3_h": flow["result"], "air_velocity_m_s": velocity}
  duct_area = _compute(velocity_formula, duct_area_input)
  if not duct_area["ok"]:
    return None, duct_area
  cross_section = duct_area["result"]
  equivalent_diameter = math.sqrt(4 * cross_section / math.pi) if cross_section else 0.0
  ach_flow = volume * ach
  people_flow = common["people_count"] * per_person
  supply_pct = params.get("supply_balance_pct", 100.0)
  exhaust_pct = params.get("exhaust_balance_pct", 100.0)
  for value, label in ((supply_pct, "баланс притока"), (exhaust_pct, "баланс вытяжки")):
    if not _finite_number(value) or value < 0 or value > 200:
      return None, {"ok": False, "message": "Проверьте «{}» (0–200%).".format(label)}
  return {
    "value": flow["result"],
    "unit": "м³/ч",
    "formula": formula,
    "inputs": flow_input,
    "coefficients": coefficients,
    "components": [
      {"label": "Объём × кратность", "value": round(ach_flow, 2), "unit": "м³/ч"},
      {"label": "Люди × наружный воздух на человека", "value": round(people_flow, 2), "unit": "м³/ч"},
      {"label": "Приток по балансу", "value": round(flow["result"] * supply_pct / 100, 2), "unit": "м³/ч"},
      {"label": "Вытяжка по балансу", "value": round(flow["result"] * exhaust_pct / 100, 2), "unit": "м³/ч"},
      {"label": "Сечение воздуховода", "value": round(cross_section, 5), "unit": "м²"},
      {"label": "Эквивалентный круглый диаметр", "value": round(equivalent_diameter * 1000, 1), "unit": "мм"}
    ],
    "duct_area_m2": cross_section,
    "duct_equivalent_diameter_mm": equivalent_diameter * 1000,
    "duct_formula": velocity_formula,
    "source": formula["source"] + " " + velocity_formula["source"],
    "version": formula["version"] + " / " + velocity_formula["version"]
  }, None


def _humidity_ratio(temperature, humidity_pct):
  saturation_formula = _formula_row("humidification_saturation_pressure")
  ratio_formula = _formula_row("humidification_humidity_ratio")
  if saturation_formula is None or ratio_formula is None:
    return None, {"ok": False, "message": "Психрометрические формулы увлажнения выключены или отсутствуют."}
  saturation = _compute(saturation_formula, {"temperature_c": temperature})
  if not saturation["ok"]:
    return None, saturation
  vapor_pressure = saturation["result"] * humidity_pct / 100
  ratio = _compute(ratio_formula, {"vapor_pressure_kpa": vapor_pressure})
  if not ratio["ok"]:
    return None, ratio
  return {
    "ratio": ratio["result"],
    "saturation_kpa": saturation["result"],
    "vapor_pressure_kpa": vapor_pressure,
    "formulas": [saturation_formula, ratio_formula]
  }, None


def _spec_number(specs, aliases):
  normalized = {
    re.sub(r"\s+", " ", key.casefold().strip()): value
    for key, value in specs.items()
  }
  for alias in aliases:
    key = re.sub(r"\s+", " ", alias.casefold().strip())
    raw = normalized.get(key)
    if not raw:
      continue
    match = re.match(r"^\s*([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))", str(raw))
    if match:
      try:
        value = float(match.group(1).replace(",", "."))
        if math.isfinite(value) and value >= 0:
          return value
      except ValueError:
        pass
  return None


def _spec_text(specs, aliases):
  aliases = {re.sub(r"\s+", " ", alias.casefold().strip()) for alias in aliases}
  for key, value in specs.items():
    normalized = re.sub(r"\s+", " ", key.casefold().strip())
    if normalized in aliases and value:
      return str(value).strip()
  return None


def _product_category_map(profile):
  categories = {row["code"]: row for row in app_tables.catalog_categories.search(active=True)}
  roots = [categories.get(code) for code in PRODUCT_CATEGORY_CODES[profile]]
  roots = [row for row in roots if row is not None]
  if not roots:
    return []
  allowed_ids = {row.get_id() for row in roots}
  for row in categories.values():
    parent = row["parent"]
    while parent is not None:
      if parent.get_id() in allowed_ids:
        allowed_ids.add(row.get_id())
        break
      parent = parent["parent"]
  return [row for row in categories.values() if row.get_id() in allowed_ids]


def _engineering_products(profile, required_capacity, selected_product_id=None):
  categories = _product_category_map(profile)
  if not categories:
    return [], None, {"ok": True}
  product_filter = q.any_of(*[
    q.all_of(category=category) for category in categories
  ])
  products = list(app_tables.products.search(
    q.fetch_only("model", "sku", "type", "brand", "category",
                 brand=q.fetch_only("name"), category=q.fetch_only("code", "title")),
    order_by("identity_key"), product_filter, active=True
  )[:201])
  has_more = len(products) > 200
  products = products[:200]
  if not products:
    return [], None, {"ok": True, "has_catalog": False}

  match = q.any_of(*[q.all_of(product=product) for product in products])
  specs_by_id = {}
  for row in app_tables.product_specs.search(
    q.fetch_only("product", "key", "value", "unit", "source"), match
  )[:5001]:
    specs_by_id.setdefault(row["product"].get_id(), {})[
      (row["key"] or "").strip().casefold()
    ] = {
      "value": (row["value"] or "").strip(),
      "unit": row["unit"] or "",
      "source": row["source"] or ""
    }
  prices = {
    row["product"].get_id(): row
    for row in app_tables.product_prices.search(
      q.fetch_only("product", "sale_price", "currency"), match
    )
  }
  required_unit = "м³/ч" if profile == "ventilation" else "кг/ч" if profile == "humidification" else "кВт"
  capacity_aliases = PRODUCT_CAPACITY_SPECS[profile]
  candidates = []
  selected = None
  for product in products:
    product_id = product.get_id()
    raw_specs = specs_by_id.get(product_id, {})
    capacity = _spec_number(
      {key: item["value"] for key, item in raw_specs.items()}, capacity_aliases
    )
    if capacity is None:
      continue
    price = prices.get(product_id)
    brand = product["brand"]
    category = product["category"]
    item = {
      "id": product_id,
      "brand": brand["name"] if brand is not None else "Бренд не указан",
      "model": product["model"] or product["sku"] or "Модель не указана",
      "type": product["type"] or "",
      "category": category["title"] if category is not None else "",
      "capacity": capacity,
      "capacity_unit": required_unit,
      "price": price["sale_price"] if price is not None else None,
      "currency": price["currency"] if price is not None else "",
      "has_price": bool(price is not None and price["sale_price"] is not None),
      "specs": {
        key: "{} {}".format(value["value"], value["unit"]).strip()
        for key, value in raw_specs.items()
      },
      "spec_sources": {key: value["source"] for key, value in raw_specs.items() if value["source"]}
    }
    if product_id == selected_product_id:
      selected = item
    if capacity >= required_capacity:
      candidates.append(item)
  candidates.sort(key=lambda item: item["capacity"])
  return candidates[:6], selected, {
    "ok": True,
    "has_catalog": True,
    "has_capacity_data": bool(candidates),
    "has_more": has_more
  }


def _calculate_hvac(profile, raw_inputs, selected_product_id=None):
  _ensure_seed_formulas()
  if profile not in {row["code"] for row in HVAC_PROFILES}:
    return {"ok": False, "message": "Выберите доступную категорию расчёта."}
  inputs, error = _normalize_engine_inputs(profile, raw_inputs)
  if error:
    return {"ok": False, "message": error}
  if inputs is None:
    return {"ok": False, "message": "Проверьте параметры расчёта."}
  assumptions = inputs.pop("_assumptions", [])
  common = {
    key: inputs[key] for key in (
      "area_m2", "height_m", "people_count", "equipment_kw", "room_type",
      "floor_type", "exposure", "room_name"
    )
  }
  components = []
  formula_records = []
  warnings = list(assumptions)
  extra = {}
  if profile in ("ac", "vrf_vrv", "engineering"):
    cooling, error = _cooling_load(common)
    if error:
      return error
    if cooling is None:
      return {"ok": False, "message": "Не удалось рассчитать тепловую нагрузку."}
    components.extend(cooling["components"])
    components.append({
      "label": "Тепловая нагрузка в BTU/ч",
      "value": round(cooling["value"] * 3412.142, 1), "unit": "BTU/ч"
    })
    formula_records.append(cooling["formula"])
    extra["cooling_kw"] = cooling["value"]
    extra["cooling_btu_h"] = cooling["value"] * 3412.142
    if profile == "vrf_vrv":
      units = inputs["indoor_unit_count"]
      extra.update({
        "indoor_unit_count": units,
        "load_per_indoor_unit_kw": cooling["value"] / units,
        "route_length_m": inputs["route_length_m"],
        "height_difference_m": inputs["height_difference_m"]
      })
      components.extend([
        {"label": "Внутренние блоки", "value": units, "unit": "шт."},
        {"label": "Расчётная нагрузка на внутренний блок", "value": round(cooling["value"] / units, 3), "unit": "кВт"},
        {"label": "Суммарная длина трасс", "value": inputs["route_length_m"], "unit": "м"},
        {"label": "Перепад высот", "value": inputs["height_difference_m"], "unit": "м"}
      ])

  vent = None
  if profile in ("ventilation", "engineering", "humidification"):
    vent, error = _ventilation_load(common, inputs)
    if error:
      return error
    if vent is None:
      return {"ok": False, "message": "Не удалось рассчитать расход вентиляции."}
    components.extend(vent["components"])
    formula_records.extend([vent["formula"], vent["duct_formula"]])
    extra.update({
      "airflow_m3_h": vent["value"],
      "duct_area_m2": vent["duct_area_m2"],
      "duct_equivalent_diameter_mm": vent["duct_equivalent_diameter_mm"]
    })

  if profile == "humidification":
    supply, error = _humidity_ratio(
      inputs["supply_temperature_c"], inputs["supply_relative_humidity_pct"]
    )
    if error:
      return error
    if supply is None or vent is None:
      return {"ok": False, "message": "Не удалось рассчитать влагосодержание притока."}
    target, error = _humidity_ratio(
      inputs["target_temperature_c"], inputs["target_relative_humidity_pct"]
    )
    if error:
      return error
    if target is None:
      return {"ok": False, "message": "Не удалось рассчитать целевое влагосодержание."}
    ratio_delta = max(0.0, target["ratio"] - supply["ratio"])
    water_formula = _formula_row("humidification_water_flow")
    if water_formula is None:
      return {"ok": False, "message": "Формула производительности увлажнения выключена или отсутствует."}
    flow_value = _compute(water_formula, {
      "airflow_m3_s": vent["value"] / 3600,
      "humidity_ratio_delta": ratio_delta
    })
    if not flow_value["ok"]:
      return flow_value
    components.extend([
      {"label": "Влагосодержание притока", "value": round(supply["ratio"] * 1000, 3), "unit": "г/кг"},
      {"label": "Целевое влагосодержание", "value": round(target["ratio"] * 1000, 3), "unit": "г/кг"},
      {"label": "Расчётный прирост влаги", "value": round(ratio_delta * 1000, 3), "unit": "г/кг"},
      {"label": "Расход воды на увлажнение", "value": round(flow_value["result"], 3), "unit": "кг/ч"}
    ])
    formula_records.extend(
      supply["formulas"] + target["formulas"] + [water_formula]
    )
    extra.update({
      "humidification_kg_h": flow_value["result"],
      "supply_humidity_ratio": supply["ratio"],
      "target_humidity_ratio": target["ratio"]
    })
    if ratio_delta <= 0:
      warnings.append("При заданных температурах и влажности увлажнение не требуется.")

  if profile in ("ac", "vrf_vrv", "engineering"):
    required = extra["cooling_kw"]
    recommendation_profile = "vrf_vrv" if profile == "vrf_vrv" else "ac"
    output_value = extra["cooling_kw"]
    output_unit = "кВт"
    if profile == "vrf_vrv":
      selected_product_id = selected_product_id
  elif profile == "ventilation":
    required = extra["airflow_m3_h"]
    recommendation_profile = "ventilation"
    output_value = extra["airflow_m3_h"]
    output_unit = "м³/ч"
  elif profile == "humidification":
    required = extra["humidification_kg_h"]
    recommendation_profile = "humidification"
    output_value = extra["humidification_kg_h"]
    output_unit = "кг/ч"
  else:
    required = extra["cooling_kw"]
    recommendation_profile = "engineering"
    output_value = extra["cooling_kw"]
    output_unit = "кВт"

  recommendations, selected, catalog_state = _engineering_products(
    recommendation_profile, required, selected_product_id
  )
  if not catalog_state.get("has_catalog"):
    warnings.append("В подходящей категории каталога пока нет товаров.")
  elif not catalog_state.get("has_capacity_data"):
    warnings.append("Добавьте характеристики мощности в карточки каталога для автоматического подбора.")

  if profile == "vrf_vrv":
    selected_specs = (selected or {}).get("specs", {})
    route = extra["route_length_m"]
    height = extra["height_difference_m"]
    max_pipe = _spec_number(selected_specs, PRODUCT_SPEC_ALIASES["max_pipe_length_m"])
    max_height = _spec_number(selected_specs, PRODUCT_SPEC_ALIASES["max_height_difference_m"])
    included = _spec_number(selected_specs, PRODUCT_SPEC_ALIASES["factory_pipe_length_m"])
    charge_rate = _spec_number(selected_specs, PRODUCT_SPEC_ALIASES["additional_refrigerant_g_per_m"])
    if max_pipe is not None and route > max_pipe:
      warnings.append("Длина трассы превышает паспортный максимум выбранной модели.")
    elif max_pipe is None:
      warnings.append("Паспортный максимум длины трассы не найден в характеристиках каталога.")
    if max_height is not None and height > max_height:
      warnings.append("Перепад высот превышает паспортный максимум выбранной модели.")
    elif max_height is None:
      warnings.append("Паспортный предел перепада высот не найден в характеристиках каталога.")
    if included is not None and charge_rate is not None:
      extra["additional_refrigerant_kg"] = max(0.0, route - included) * charge_rate / 1000
      components.append({
        "label": "Дозаправка по данным карточки производителя",
        "value": round(extra["additional_refrigerant_kg"], 3), "unit": "кг"
      })
    else:
      warnings.append("Дозаправка не рассчитана: добавьте в выбранную модель заводскую длину и норму дозаправки из паспорта.")
    if selected is not None:
      capacity_sum = selected["capacity"]
      extra["selected_product_capacity_sum_kw"] = capacity_sum
      components.append({
        "label": "Мощность выбранной VRV / VRF системы из каталога",
        "value": round(capacity_sum, 3), "unit": "кВт"
      })
      if capacity_sum < extra["cooling_kw"]:
        warnings.append("Мощность выбранной системы ниже расчётной нагрузки объекта.")

  if profile in ("ac", "vrf_vrv") and selected is not None:
    selected_specs = selected.get("specs", {})
    for key, label in (
      ("liquid_pipe_diameter", "Диаметр жидкостной трубы по карточке оборудования"),
      ("gas_pipe_diameter", "Диаметр газовой трубы по карточке оборудования")
    ):
      value = _spec_text(selected_specs, PRODUCT_SPEC_ALIASES[key])
      if value:
        extra[key] = value
        components.append({"label": label, "value": value, "unit": ""})
      else:
        warnings.append(
          "{} не указан в технических характеристиках выбранной модели; размер не подменён предположением.".format(label)
        )

  primary_formula = _formula_row(
    "ventilation_design_flow" if profile == "ventilation" else
    "humidification_water_flow" if profile == "humidification" else "ac_room_load_kw"
  )
  source = "\n".join(dict.fromkeys(row["source"] for row in formula_records if row is not None))
  version = " / ".join(dict.fromkeys(row["version"] for row in formula_records if row is not None))
  result = {
    "ok": True,
    "profile": profile,
    "profile_title": next(row["title"] for row in HVAC_PROFILES if row["code"] == profile),
    "result": output_value,
    "result_unit": output_unit,
    "cooling_kw": extra.get("cooling_kw"),
    "cooling_btu_h": extra.get("cooling_btu_h"),
    "components": components,
    "extra": extra,
    "inputs": inputs,
    "recommendations": recommendations,
    "selected_product": selected,
    "warnings": warnings,
    "assumptions": assumptions,
    "source": source,
    "version": version,
    "can_quote": bool(
      selected and selected.get("has_price")
      and selected["capacity"] >= required
    ),
    "catalog_state": catalog_state,
    "calculation_id": None
  }
  result["formula"] = primary_formula
  result["coefficients"] = {
    row["code"]: row["coefficients"] or {} for row in formula_records if row is not None
  }
  return result


def _save_structured_calculation(user, formula, inputs, coefficients, result, unit,
                                source, version, details, project_id=None):
  if user is None:
    return {"ok": False, "message": "Для сохранения расчёта войдите в профиль."}
  project = app_tables.projects.get_by_id(project_id) if project_id else None
  if project_id and project is None:
    return {"ok": False, "message": "Проект не найден."}
  if project is not None and not Core.can_access_project(project, user):
    return {"ok": False, "message": "Расчёт можно сохранить только в свой проект."}
  now = datetime.now(timezone.utc)
  row = cast(Any, app_tables.calculations).add_row(
    formula=formula,
    inputs=inputs,
    coefficients=coefficients,
    units={"result": unit},
    result=result,
    source=source,
    version=version,
    created_by=user,
    created_at=now,
    details=details
  )
  if project is not None:
    row["project"] = project
  Core.log_audit(
    actor=user,
    action="calculation.hvac_saved",
    entity_type="calculation",
    entity_id=str(row.get_id()),
    details={"profile": details.get("profile", "engineering"), "result": result, "unit": unit},
    created_at=now
  )
  return {"ok": True, "calculation_id": row.get_id()}


def _save_hvac_result(user, computed, project_id=None):
  details = {
    "profile": computed["profile"],
    "components": computed["components"],
    "extra": computed["extra"],
    "recommendations": computed["recommendations"],
    "warnings": computed["warnings"]
  }
  saved = _save_structured_calculation(
    user,
    computed["formula"],
    computed["inputs"],
    computed["coefficients"],
    computed["result"],
    computed["result_unit"],
    computed["source"],
    computed["version"],
    details,
    project_id
  )
  if saved["ok"]:
    computed["calculation_id"] = saved["calculation_id"]
  return saved


def is_finite_number(value):
  return _finite_number(value)


def engine_number(raw, label, minimum, maximum, integer=False):
  return _engine_number(raw, label, minimum, maximum, integer)


def compute_formula(formula, raw_inputs):
  return _compute(formula, raw_inputs)


def calculate_hvac_profile(profile, raw_inputs, selected_product_id=None):
  return _calculate_hvac(profile, raw_inputs, selected_product_id)


def save_structured_calculation(user, formula, inputs, coefficients, result, unit,
                                source, version, details, project_id=None):
  return _save_structured_calculation(
    user, formula, inputs, coefficients, result, unit,
    source, version, details, project_id
  )


@anvil.server.callable
def get_hvac_calculation_setup():
  # Setup is read-only reference data; seed formulas lazily on first calculation.
  # Avoid a table lookup/write path on every calculator screen open.
  user = anvil.users.get_user()
  return {
    "ok": True,
    "profiles": HVAC_PROFILES,
    "room_types": ROOM_TYPE_TITLES,
    "floor_types": [("Обычный этаж", "regular"), ("Последний этаж / под кровлей", "top")],
    "exposures": [("Тень", "shade"), ("Обычная", "normal"), ("Высокая", "high")],
    "signed_in": user is not None,
    "is_admin": Core._is_admin(user),
    "can_edit_formulas": Core.has_permission(user, "calculations.manage")
  }


@anvil.server.callable
def calculate_hvac_engine(profile, inputs, save_result=False, project_id=None,
                          selected_product_id=None):
  if not isinstance(save_result, bool):
    return {"ok": False, "message": "Некорректная команда сохранения."}
  if project_id is not None and (not isinstance(project_id, str) or not project_id):
    return {"ok": False, "message": "Некорректный проект."}
  user = _current_user()
  computed = _calculate_hvac(profile, inputs, selected_product_id)
  if not computed["ok"]:
    return computed
  if save_result:
    saved = _save_hvac_result(user, computed, project_id)
    if not saved["ok"]:
      return saved
  return computed


@anvil.server.callable(require_user=True)
def email_my_hvac_report(title, report_text, recipient_email=""):
  user = anvil.users.get_user()
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в профиль, чтобы отправить расчёт себе на email.")
  if not isinstance(title, str) or not title.strip() or len(title) > 120:
    return {"ok": False, "message": "Проверьте название отчёта."}
  if not isinstance(report_text, str) or not report_text.strip() or len(report_text) > 100000:
    return {"ok": False, "message": "Отчёт пустой или превышает допустимый размер."}
  if not isinstance(recipient_email, str) or len(recipient_email.strip()) > 254:
    return {"ok": False, "message": "Проверьте адрес электронной почты."}
  recipient = recipient_email.strip() or user["email"]
  if (
    not isinstance(recipient, str) or len(recipient) > 254
    or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", recipient)
  ):
    return {"ok": False, "message": "Укажите рабочий email для доставки отчёта."}
  safe_title = title.strip()
  attachment = anvil.BlobMedia(
    "text/plain; charset=utf-8", report_text.encode("utf-8"),
    name="eko-klimat-report.txt"
  )
  anvil.email.send(
    to=recipient,
    subject="ЭКО-КЛИМАТ · {}".format(safe_title),
    text="Отчёт ЭКО-КЛИМАТ во вложении.\nОн отправлен на email вашей учётной записи.",
    attachments=[attachment]
  )
  Core.log_audit(
    actor=user, action="calculation.report_emailed", entity_type="calculation_report",
    details={"title": safe_title, "recipient": recipient},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Отчёт отправлен на {}.".format(recipient)}


@anvil.server.callable(require_user=True)
def create_hvac_quote(profile, inputs, project_id, selected_product_id, terms=""):
  user = _current_user()
  if user is None:
    return {"ok": False, "message": "Для создания КП войдите в профиль."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Выберите или создайте свой проект."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None or not Core.can_access_project(project, user):
    return {"ok": False, "message": "КП можно создать только для своего проекта."}
  if not isinstance(selected_product_id, str) or not selected_product_id:
    return {"ok": False, "message": "Выберите реальное оборудование из каталога."}
  computed = _calculate_hvac(profile, inputs, selected_product_id)
  if not computed["ok"]:
    return computed
  if not computed["can_quote"]:
    return {"ok": False, "message": "Выберите подходящее оборудование с заданной ценой из каталога."}
  saved = _save_hvac_result(user, computed, project_id)
  if not saved["ok"]:
    return saved
  quote = Estimates.create_catalog_quote(
    project,
    user,
    [{"product_id": selected_product_id, "quantity": 1}],
    terms,
    {
      "source": "calculation",
      "calculation_id": computed["calculation_id"],
      "profile": profile,
      "inputs": computed["inputs"],
      "result": computed["result"],
      "unit": computed["result_unit"]
    }
  )
  if not quote["ok"]:
    quote["calculation_saved"] = True
    quote["calculation_id"] = computed["calculation_id"]
    return quote
  quote["calculation_id"] = computed["calculation_id"]
  quote["message"] = "Расчёт сохранён; {} №{} создано.".format("КП", quote["quote_number"])
  return quote


@anvil.server.callable
def get_recent_calculations():
  user = _current_user()
  if user is None:
    return []
  rows = app_tables.calculations.search(
    q.fetch_only("result", "units", "version", "created_at", "formula",
                 formula=q.fetch_only("title", "code"),
                 project=q.fetch_only("title"), system=q.fetch_only("title")),
    order_by("created_at", ascending=False),
    created_by=user
  )[:25]
  return [
    {
      "title": row["formula"]["title"],
      "code": row["formula"]["code"],
      "result": row["result"],
      "unit": (row["units"] or {}).get("result", ""),
      "display_result": "{} {}".format(
        row["result"], (row["units"] or {}).get("result", "")
      ).strip(),
      "version": row["version"],
      "display_version": "Версия {}".format(row["version"]),
      "display_context": (
        "Система: {}".format(row["system"]["title"])
        if row["system"] is not None else
        "Проект: {}".format(row["project"]["title"])
        if row["project"] is not None else "Без проекта"
      ),
      "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M UTC")
    }
    for row in rows
  ]

