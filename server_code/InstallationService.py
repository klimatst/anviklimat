import math
from datetime import datetime, timezone

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
from typing import Any, cast

import CalculationsService as Calculations
import CatalogService as Catalog
import Core
import EstimateEngine as Estimates
import AdminStudio


INSTALLATION_PROFILES = [
  {"code": "ac", "title": "Кондиционеры", "calculation_profile": "ac"},
  {"code": "vrf_vrv", "title": "VRV / VRF", "calculation_profile": "vrf_vrv"},
  {"code": "ventilation", "title": "Вентиляция", "calculation_profile": "ventilation"}
]
MATERIAL_CATEGORIES = [
  {"code": "materials-copper-tube", "title": "Медная труба", "group": "refrigerant", "group_title": "Трассы и изоляция", "unit": "м", "quantity_key": "route"},
  {"code": "materials-insulation", "title": "Изоляция", "group": "refrigerant", "group_title": "Трассы и изоляция", "unit": "м", "quantity_key": "route"},
  {"code": "materials-cable", "title": "Кабель", "group": "refrigerant", "group_title": "Трассы и изоляция", "unit": "м", "quantity_key": "cable"},
  {"code": "materials-drainage", "title": "Дренаж", "group": "refrigerant", "group_title": "Трассы и изоляция", "unit": "м", "quantity_key": "drain"},
  {"code": "materials-fasteners", "title": "Крепёж", "group": "mounting", "group_title": "Крепёж и расходники", "unit": "шт", "quantity_key": "fasteners"},
  {"code": "materials-brackets", "title": "Кронштейны", "group": "mounting", "group_title": "Крепёж и расходники", "unit": "шт", "quantity_key": "brackets"},
  {"code": "materials-sleeves", "title": "Гильзы", "group": "mounting", "group_title": "Крепёж и расходники", "unit": "шт", "quantity_key": "sleeves"},
  {"code": "materials-sealant", "title": "Герметик", "group": "mounting", "group_title": "Крепёж и расходники", "unit": "шт", "quantity_key": "sealant"},
  {"code": "materials-corrugated", "title": "Гофра", "group": "mounting", "group_title": "Крепёж и расходники", "unit": "м", "quantity_key": "cable"},
  {"code": "materials-ducts", "title": "Воздуховоды", "group": "air_distribution", "group_title": "Воздухораспределение", "unit": "м", "quantity_key": "duct"},
  {"code": "materials-fittings", "title": "Фасонные элементы", "group": "air_distribution", "group_title": "Воздухораспределение", "unit": "шт", "quantity_key": "fittings"},
  {"code": "materials-grilles", "title": "Решётки / диффузоры", "group": "air_distribution", "group_title": "Воздухораспределение", "unit": "шт", "quantity_key": "outlets"},
  {"code": "materials-valves", "title": "Клапаны", "group": "air_distribution", "group_title": "Воздухораспределение", "unit": "шт", "quantity_key": "valves"},
  {"code": "materials-consumables", "title": "Расходники для монтажа", "group": "mounting", "group_title": "Крепёж и расходники", "unit": "компл.", "quantity_key": "consumables"}
]
MATERIAL_BY_CODE = {row["code"]: row for row in MATERIAL_CATEGORIES}
COMPLEXITY_CHOICES = [
  ("Стандартный доступ", "standard"),
  ("Ограниченный доступ", "limited_access"),
  ("Высотные работы", "height_work")
]


def _ensure_material_categories():
  Catalog.ensure_catalog_categories()
  existing = {
    row["code"]: row
    for row in app_tables.catalog_categories.search()
  }
  parent = existing.get("materials")
  if parent is None:
    raise RuntimeError("Категория материалов каталога отсутствует.")
  missing = [
    {
      "code": item["code"],
      "title": item["title"],
      "parent": parent,
      "active": True,
      "sort_order": 700 + order
    }
    for order, item in enumerate(MATERIAL_CATEGORIES)
    if item["code"] not in existing
  ]
  if missing:
    cast(Any, app_tables.catalog_categories).add_rows(missing)


def _catalog_materials():
  _ensure_material_categories()
  categories = {
    row["code"]: row
    for row in app_tables.catalog_categories.search(active=True)
    if row["code"] in MATERIAL_BY_CODE
  }
  if not categories:
    return []
  product_match = q.any_of(*[
    q.all_of(category=category) for category in categories.values()
  ])
  products = list(app_tables.products.search(
    q.fetch_only("model", "sku", "brand", "category",
                 brand=q.fetch_only("name"), category=q.fetch_only("code")),
    order_by("identity_key"), product_match, active=True
  )[:301])
  products = products[:300]
  if products:
    match = q.any_of(*[q.all_of(product=product) for product in products])
    prices = {
      row["product"].get_id(): row
      for row in app_tables.product_prices.search(
        q.fetch_only("product", "sale_price", "currency"), match
      )
    }
    specs: dict[str, dict[str, dict[str, str]]] = {}
    for spec_row in app_tables.product_specs.search(
      q.fetch_only("product", "key", "value", "unit"), match
    )[:5001]:
      specs.setdefault(spec_row["product"].get_id(), {})[
        (spec_row["key"] or "").strip().casefold()
      ] = {"value": (spec_row["value"] or "").strip(), "unit": spec_row["unit"] or ""}
  else:
    prices, specs = {}, {}

  products_by_category = {code: [] for code in categories}
  for product in products:
    category = product["category"]
    if category is None or category["code"] not in products_by_category:
      continue
    price = prices.get(product.get_id())
    spec_values = specs.get(product.get_id(), {})
    unit = next((
      item["value"] or item["unit"]
      for key, item in spec_values.items()
      if key in ("unit", "sale_unit", "measurement_unit", "единица", "единица измерения")
    ), "")
    brand = product["brand"]
    label = "{} {}".format(
      brand["name"] if brand is not None else "",
      product["model"] or product["sku"] or "Модель не указана"
    ).strip()
    sale_price = (
      float(price["sale_price"])
      if price is not None and price["sale_price"] is not None else None
    )
    has_price = sale_price is not None
    price_label = "Цена не задана"
    if price is not None and sale_price is not None:
      price_label = "{} {}".format(
        "{:.2f}".format(sale_price).replace(".", ","),
        price["currency"] or ""
      ).strip()
    products_by_category[category["code"]].append({
      "id": product.get_id(),
      "label": "{} · {}".format(label, price_label),
      "title": label,
      "unit": unit,
      "price": sale_price,
      "currency": price["currency"] if price is not None else "",
      "has_price": has_price
    })
  result = []
  for item in MATERIAL_CATEGORIES:
    row: dict[str, Any] = dict(item)
    row["products"] = products_by_category.get(item["code"], [])
    result.append(row)
  return result


@anvil.server.callable
def get_installation_options():
  user = anvil.users.get_user()
  role = user["role"] if user is not None else None
  role_code = role["code"].casefold() if role is not None else "user"
  can_view_installer = role_code == "admin" or (
    role_code == "moderator" and Core.has_permission(user, "dashboard.view")
  )
  return {
    "ok": True,
    "profiles": INSTALLATION_PROFILES,
    "complexities": COMPLEXITY_CHOICES,
    "materials": _catalog_materials() if can_view_installer else [],
    "signed_in": user is not None,
    "can_view_installer": can_view_installer
  }


def _number(raw, label, minimum, maximum, integer=False):
  return Calculations.engine_number(raw, label, minimum, maximum, integer)


def _normalise_installation_inputs(profile, raw):
  if profile not in {row["code"] for row in INSTALLATION_PROFILES}:
    return None, "Выберите категорию монтажа."
  if not isinstance(raw, dict) or len(raw) > 40:
    return None, "Проверьте параметры объекта и монтажа."
  raw_values = dict(raw)
  assumptions = []

  def missing(value):
    return value is None or (isinstance(value, str) and not value.strip())

  area, error = _number(raw_values.get("area_m2"), "Площадь", 0.1, 1000000)
  if error:
    return None, error
  if area is None:
    return None, "Укажите площадь объекта."
  raw_values["area_m2"] = area
  estimated_count = min(500, max(1, int(math.ceil(area / 25.0)))) if profile == "vrf_vrv" else 1
  equipment_count_for_estimate = estimated_count
  if not missing(raw_values.get("equipment_count")):
    try:
      equipment_count_for_estimate = max(
        1, int(float(str(raw_values["equipment_count"]).replace(",", ".")))
      )
    except (TypeError, ValueError, OverflowError):
      pass
  estimate_route = round(
    max(5.0, math.sqrt(area / equipment_count_for_estimate) * 1.5)
    * equipment_count_for_estimate, 1
  )
  estimate_duct = round(max(6.0, math.sqrt(area) * 3.0), 1)
  def estimate_from_input(key, fallback):
    if missing(raw_values.get(key)):
      return fallback
    try:
      value = float(str(raw_values[key]).replace(",", "."))
    except (TypeError, ValueError, OverflowError):
      return fallback
    return value if math.isfinite(value) and value >= 0 else fallback

  route_basis = estimate_from_input("route_length_m", estimate_route)
  duct_basis = estimate_from_input("duct_length_m", estimate_duct)
  estimated_defaults = {
    "height_m": (2.7, "высота помещения принята равной 2,7 м"),
    "people_count": (int(math.ceil(area / 20.0)), "число людей оценено как 1 человек на 20 м²"),
    "equipment_kw": (0.0, "тепловыделение оборудования принято равным 0 кВт"),
    "equipment_count": (estimated_count, "количество оборудования оценено по площади"),
    "route_length_m": (0.0 if profile == "ventilation" else estimate_route, "длина холодильной трассы оценена по площади"),
    "duct_length_m": (estimate_duct if profile == "ventilation" else 0.0, "длина воздуховодов оценена по площади"),
    "drain_length_m": (0.0 if profile == "ventilation" else route_basis, "длина дренажа принята равной длине холодильной трассы"),
    "cable_length_m": (duct_basis + 3.0 if profile == "ventilation" else route_basis + 3.0, "длина кабеля оценена по длине инженерной трассы с запасом 3 м"),
    "height_difference_m": (3.0 if profile == "vrf_vrv" else 0.0, "перепад высот оценён в 3 м"),
    "floor_count": (1, "этажность принята равной одному этажу"),
    "wall_crossings": (equipment_count_for_estimate * 2 if profile != "ventilation" else 0, "число проходов оценено как два на единицу оборудования"),
    "bracket_count": (equipment_count_for_estimate * 2 if profile != "ventilation" else 0, "приняты два кронштейна на наружный блок"),
    "fastener_points": (int(math.ceil((duct_basis if profile == "ventilation" else route_basis) / 0.5)), "точки крепления оценены с шагом 0,5 м"),
    "sealant_units": (equipment_count_for_estimate if profile != "ventilation" else 0, "герметик оценён по числу единиц оборудования"),
    "duct_fittings_count": (int(math.ceil(duct_basis / 3.0)) if profile == "ventilation" else 0, "фасонные элементы оценены по одному на 3 м воздуховода"),
    "outlet_count": (int(math.ceil(area / 25.0)) if profile == "ventilation" else 0, "воздухораспределители оценены по одному на 25 м²"),
    "valve_count": (int(math.ceil(area / 100.0)) if profile == "ventilation" else 0, "клапаны оценены по одному на 100 м²"),
    "consumables_units": (equipment_count_for_estimate, "комплект расходников оценён по количеству оборудования"),
    "air_changes_per_hour": (1.5, "кратность воздухообмена принята равной 1,5 ч⁻¹"),
    "fresh_air_m3_h_person": (30.0, "наружный воздух принят равным 30 м³/ч на человека"),
    "air_velocity_m_s": (4.0, "скорость в воздуховоде принята равной 4 м/с"),
    "supply_balance_pct": (100.0, "баланс притока принят равным 100%"),
    "exhaust_balance_pct": (100.0, "баланс вытяжки принят равным 100%")
  }
  not_applicable = set()
  if profile == "ventilation":
    not_applicable.update((
      "route_length_m", "drain_length_m", "height_difference_m",
      "bracket_count", "sealant_units"
    ))
  else:
    not_applicable.update((
      "duct_length_m", "duct_fittings_count", "outlet_count", "valve_count",
      "air_changes_per_hour", "fresh_air_m3_h_person", "air_velocity_m_s",
      "supply_balance_pct", "exhaust_balance_pct"
    ))
  if profile != "vrf_vrv":
    not_applicable.add("height_difference_m")
  for key, (value, reason) in estimated_defaults.items():
    if missing(raw_values.get(key)):
      raw_values[key] = value
      if key not in not_applicable:
        assumptions.append("Допущение: {}.".format(reason))
  definitions = [
    ("area_m2", "Площадь", 0.1, 1000000, False),
    ("height_m", "Высота", 1, 30, False),
    ("people_count", "Количество людей", 0, 100000, True),
    ("equipment_kw", "Тепловыделение оборудования", 0, 1000000, False),
    ("equipment_count", "Количество оборудования", 1, 500, True),
    ("route_length_m", "Длина холодильной трассы", 0, 100000, False),
    ("duct_length_m", "Длина воздуховодов", 0, 100000, False),
    ("drain_length_m", "Длина дренажа", 0, 100000, False),
    ("cable_length_m", "Длина кабельной трассы", 0, 100000, False),
    ("height_difference_m", "Перепад высот", 0, 10000, False),
    ("floor_count", "Этажность", 1, 500, True),
    ("wall_crossings", "Проходы через стены", 0, 100000, True),
    ("bracket_count", "Кронштейны по проекту", 0, 100000, True),
    ("fastener_points", "Точки крепления по проекту", 0, 1000000, True),
    ("sealant_units", "Количество упаковок герметика", 0, 100000, False),
    ("duct_fittings_count", "Фасонные элементы по проекту", 0, 100000, True),
    ("outlet_count", "Решётки / диффузоры по проекту", 0, 100000, True),
    ("valve_count", "Клапаны по проекту", 0, 100000, True),
    ("consumables_units", "Комплекты расходников", 0, 100000, False),
    ("air_changes_per_hour", "Кратность воздухообмена", 0, 1000, False),
    ("fresh_air_m3_h_person", "Наружный воздух на человека", 0, 10000, False),
    ("air_velocity_m_s", "Скорость в воздуховоде", 0.1, 40, False),
    ("supply_balance_pct", "Баланс притока", 0, 200, False),
    ("exhaust_balance_pct", "Баланс вытяжки", 0, 200, False)
  ]
  values: dict[str, Any] = {}
  for key, label, minimum, maximum, integer in definitions:
    value, error = _number(raw_values.get(key), label, minimum, maximum, integer)
    if error:
      return None, error
    if value is None:
      return None, "Проверьте поле «{}».".format(label)
    values[key] = value
  choice_fields = {
    "room_type": set(Calculations.ROOM_TYPE_FACTORS),
    "floor_type": {"regular", "top"},
    "exposure": {"shade", "normal", "high"},
    "complexity": {value for _, value in COMPLEXITY_CHOICES}
  }
  defaults = {
    "room_type": "apartment", "floor_type": "regular",
    "exposure": "normal", "complexity": "standard"
  }
  for key, allowed in choice_fields.items():
    value = raw_values.get(key, defaults[key])
    if not isinstance(value, str) or value not in allowed:
      return None, "Выберите корректное значение поля «{}».".format(key)
    values[key] = value
  for key in ("site_name", "room_name"):
    value = raw_values.get(key, "")
    if not isinstance(value, str) or len(value.strip()) > 120:
      return None, "Название объекта или помещения должно быть короче 120 символов."
    values[key] = value.strip()
  values["_assumptions"] = assumptions
  return values, None


def _calculation_inputs(profile, values):
  calculation = {
    key: values[key] for key in (
      "area_m2", "height_m", "people_count", "equipment_kw",
      "room_type", "floor_type", "exposure", "room_name"
    )
  }
  if profile == "vrf_vrv":
    calculation.update({
      "indoor_unit_count": values["equipment_count"],
      "route_length_m": values["route_length_m"],
      "height_difference_m": values["height_difference_m"]
    })
  if profile == "ventilation":
    calculation.update({
      key: values[key] for key in (
        "air_changes_per_hour", "fresh_air_m3_h_person", "air_velocity_m_s",
        "supply_balance_pct", "exhaust_balance_pct"
      )
    })
  return calculation


def _material_suggestion(item, values, route_length, profile):
  key = item["quantity_key"]
  if key == "route":
    return 0 if profile == "ventilation" else route_length
  if key == "drain":
    return values["drain_length_m"]
  if key == "duct":
    return values["duct_length_m"]
  mapped = {
    "cable": "cable_length_m",
    "fasteners": "fastener_points", "brackets": "bracket_count",
    "sleeves": "wall_crossings", "sealant": "sealant_units",
    "fittings": "duct_fittings_count", "outlets": "outlet_count",
    "valves": "valve_count", "consumables": "consumables_units"
  }
  return values[mapped[key]]


def _material_selections(raw, material_catalog, values, route_length, profile):
  if raw is None:
    raw = []
  if not isinstance(raw, list) or len(raw) > len(MATERIAL_CATEGORIES):
    return None, "Проверьте выбранные материалы."
  category_codes = {item["code"] for item in MATERIAL_CATEGORIES}
  category_rows = {
    row["code"]: row for row in app_tables.catalog_categories.search(active=True)
    if row["code"] in category_codes
  }
  product_by_id = {}
  products = []
  result_lines = []
  normalized = []
  seen_categories = set()
  for row in raw:
    if not isinstance(row, dict):
      return None, "Проверьте выбранные материалы."
    code = row.get("category_code")
    if code not in category_codes or code in seen_categories:
      return None, "Категория материала указана повторно или недоступна."
    seen_categories.add(code)
    definition = MATERIAL_BY_CODE[code]
    raw_quantity = row.get("quantity")
    if raw_quantity is None or raw_quantity == "":
      raw_quantity = _material_suggestion(definition, values, route_length, profile)
    quantity, error = _number(raw_quantity, definition["title"], 0, 1000000, False)
    if error:
      return None, error
    if quantity is None:
      return None, "Проверьте количество материала «{}».".format(definition["title"])
    product_id = row.get("product_id")
    product = None
    if product_id:
      if not isinstance(product_id, str) or len(product_id) > 100:
        return None, "Выберите материал из каталога."
      product = app_tables.products.get_by_id(product_id)
      if (
        product is None or not product["active"] or
        product["category"] is None or product["category"]["code"] != code
      ):
        return None, "Выбранный товар не относится к категории «{}».".format(definition["title"])
      if quantity <= 0:
        return None, "Укажите количество для «{}».".format(definition["title"])
      product_by_id[product_id] = product
      products.append(product)
      normalized.append({"category_code": code, "product_id": product_id, "quantity": quantity})
    result_lines.append({
      "category_code": code,
      "category_title": definition["title"],
      "description": definition["title"],
      "group": definition["group"],
      "group_title": definition["group_title"],
      "product_id": product_id or None,
      "quantity": quantity,
      "unit": definition["unit"],
      "unit_price": None,
      "line_total": None,
      "price_known": False
    })
  return {
    "normalized": normalized,
    "lines": result_lines,
    "products_by_id": product_by_id
  }, None


def _clean_price_line(row):
  product = row.get("product")
  category = product["category"] if product is not None else None
  return {
    "description": row["description"],
    "group": row.get("group", "materials"),
    "category_code": category["code"] if category is not None else "",
    "quantity": row["quantity"],
    "unit": row["unit"],
    "unit_price": row["unit_price"],
    "base_unit_price": row.get("base_unit_price", row["unit_price"]),
    "discount_percent": row.get("discount_percent", 0.0),
    "discount_amount": row.get("discount_amount", 0.0),
    "currency": row["currency"],
    "line_total": row["line_total"],
    "price_known": row["line_total"] is not None
  }


def _calculate_installation(profile, raw_inputs, raw_materials=None,
                             selected_equipment_id=None, include_materials=True):
  values, error = _normalise_installation_inputs(profile, raw_inputs)
  if error:
    return {"ok": False, "message": error}
  if values is None:
    return {"ok": False, "message": "Проверьте параметры монтажа."}
  assumptions = values.pop("_assumptions", [])
  calc_profile = next(
    item["calculation_profile"] for item in INSTALLATION_PROFILES
    if item["code"] == profile
  )
  calculation = Calculations.calculate_hvac_profile(
    calc_profile,
    _calculation_inputs(profile, values),
    selected_equipment_id
  )
  if not calculation["ok"]:
    return calculation
  route_length = (
    values["duct_length_m"] if profile == "ventilation"
    else values["route_length_m"]
  )
  material_catalog = _catalog_materials()
  provided = list(raw_materials or []) if isinstance(raw_materials, list) else raw_materials
  if include_materials and isinstance(provided, list):
    provided_codes = {
      row.get("category_code") for row in provided if isinstance(row, dict)
    }
    for definition in MATERIAL_CATEGORIES:
      if definition["code"] in provided_codes:
        continue
      quantity = _material_suggestion(definition, values, route_length, profile)
      category = next((row for row in material_catalog if row["code"] == definition["code"]), None)
      if quantity <= 0:
        continue
      product_id = None
      products = category["products"] if category is not None else []
      if len(products) == 1:
        product_id = products[0]["id"]
      provided.append({
        "category_code": definition["code"],
        "product_id": product_id,
        "quantity": quantity
      })
  material_data, error = _material_selections(
    provided if include_materials else [], material_catalog, values,
    route_length, profile
  )
  if error:
    return {"ok": False, "message": error}
  if material_data is None:
    return {"ok": False, "message": "Проверьте выбранные материалы."}

  install_formula = app_tables.formulas.get(code="installation_work_cost")
  if install_formula is None or not install_formula["enabled"]:
    return {"ok": False, "message": "Формула стоимости работ выключена или отсутствует."}
  coefficients = install_formula["coefficients"] or {}
  rate_per_unit = coefficients.get("rate_per_unit", 0)
  rate_per_m = coefficients.get("route_rate_per_m", 0)
  rate_per_floor = coefficients.get("rate_per_floor", 0)
  # Mirror the Lovable-style installation pricing controls into the real
  # Anvil installation calculator for the core AC/VRF rates.
  if profile == "ac":
    price_key = (
      "installation.pricing.acStandard"
      if values["complexity"] == "standard"
      else "installation.pricing.acPremium"
    )
    configured_rate = AdminStudio.get_admin_studio_setting(price_key, None)
    if Calculations.is_finite_number(configured_rate) and configured_rate >= 0:
      rate_per_unit = configured_rate
      complexity_factor = 1.0
  elif profile == "vrf_vrv":
    configured_unit = AdminStudio.get_admin_studio_setting(
      "installation.pricing.indoorUnit", None
    )
    configured_route = AdminStudio.get_admin_studio_setting(
      "installation.pricing.vrfMainRoute", None
    )
    if Calculations.is_finite_number(configured_unit) and configured_unit >= 0:
      rate_per_unit = configured_unit
    if Calculations.is_finite_number(configured_route) and configured_route >= 0:
      rate_per_m = configured_route
  for value, label in (
    (rate_per_unit, "работа за единицу"),
    (rate_per_m, "работа за метр"),
    (rate_per_floor, "работа за этаж")
  ):
    if not Calculations.is_finite_number(value) or not isinstance(value, (int, float)) or value < 0:
      return {"ok": False, "message": "Проверьте коэффициент «{}» формулы монтажа.".format(label)}
  complexity_key = "difficulty_" + values["complexity"]
  complexity_factor = coefficients.get(complexity_key)
  if not Calculations.is_finite_number(complexity_factor) or not isinstance(complexity_factor, (int, float)) or complexity_factor <= 0:
    return {"ok": False, "message": "Проверьте коэффициент сложности в формуле монтажа."}
  work_inputs = {
    "equipment_count": values["equipment_count"],
    "route_length_m": route_length,
    "complexity_factor": complexity_factor,
    "floor_count": values["floor_count"]
  }
  work_result = Calculations.compute_formula(install_formula, work_inputs)
  if not work_result["ok"]:
    return work_result
  formula_work_lines = []
  formula_work_lines.append({
    "description": "Монтаж и подключение оборудования",
    "quantity": values["equipment_count"],
    "unit": "шт",
    "unit_price": rate_per_unit * complexity_factor,
    "source": "installation_work_cost",
    "snapshot": {
      "formula": "installation_work_cost", "version": install_formula["version"],
      "base_rate": rate_per_unit, "complexity_factor": complexity_factor
    }
  })
  effective_route_rate = rate_per_m * complexity_factor
  if route_length > 0:
    formula_work_lines.append({
      "description": "Прокладка трассы / воздуховодов",
      "quantity": route_length,
      "unit": "м",
      "unit_price": effective_route_rate,
      "source": "installation_work_cost",
      "snapshot": {"formula": "installation_work_cost", "version": install_formula["version"]}
    })
  formula_work_lines.append({
    "description": "Работы с учётом этажности",
    "quantity": values["floor_count"],
    "unit": "этаж",
    "unit_price": rate_per_floor,
    "source": "installation_work_cost",
    "snapshot": {"formula": "installation_work_cost", "version": install_formula["version"]}
  })

  selections = []
  if selected_equipment_id:
    selections.append({
      "product_id": selected_equipment_id,
      "quantity": values["equipment_count"]
    })
  selections.extend(material_data["normalized"])
  pricing = Estimates.price_catalog_selections(
    selections, allow_missing=True, allow_empty=True
  )
  if not pricing["ok"]:
    return pricing
  priced_lines = [_clean_price_line(row) for row in pricing["lines"]]
  for line in material_data["lines"]:
    selected_line = next((
      item for item in priced_lines
      if item["category_code"] == line["category_code"]
      and item["group"] == "materials"
    ), None)
    if selected_line is not None:
      line.update({
        "description": selected_line["description"],
        "quantity": selected_line["quantity"],
        "unit": selected_line["unit"] or line["unit"],
        "unit_price": selected_line["unit_price"],
        "currency": selected_line["currency"],
        "line_total": selected_line["line_total"],
        "price_known": selected_line["price_known"]
      })
  work_lines = [line for line in priced_lines if line["group"] == "works"]
  work_lines.extend([
    {
      "description": row["description"],
      "group": "works",
      "category_code": "",
      "quantity": row["quantity"],
      "unit": row["unit"],
      "unit_price": row["unit_price"],
      "currency": pricing["currency"],
      "line_total": round(row["quantity"] * row["unit_price"], 2),
      "price_known": True
    }
    for row in formula_work_lines
  ])
  selected_equipment = calculation.get("selected_product")
  equipment_lines = [line for line in priced_lines if line["group"] == "equipment"]
  material_lines = material_data["lines"]

  required_material_codes = {
    line["category_code"] for line in material_data["lines"]
    if line["quantity"] > 0
  }
  selected_material_codes = {
    item["category_code"] for item in material_data["normalized"]
  }
  missing_materials = sorted(required_material_codes - selected_material_codes)
  missing_prices = pricing["missing_pricing"]
  material_sum_known = bool(selected_equipment) and not missing_prices and not missing_materials
  material_and_equipment_cost = pricing["materials_cost"] if material_sum_known else None
  work_total = round(
    pricing["labor_cost"] + work_result["result"], 2
  ) if not missing_prices else None
  total = (
    round(material_and_equipment_cost + work_total, 2)
    if material_and_equipment_cost is not None and work_total is not None else None
  )
  warnings = list(calculation["warnings"]) + assumptions
  if not selected_equipment:
    warnings.append("Выберите оборудование из каталога, чтобы получить его цену и монтажную стоимость.")
  if missing_materials:
    titles = [MATERIAL_BY_CODE[code]["title"] for code in missing_materials]
    warnings.append("Добавьте эти материалы из каталога: {}.".format(", ".join(titles[:6])))
  if missing_prices:
    warnings.append("В каталоге не хватает цены, валюты или единицы для выбранных позиций.")
  if rate_per_unit == 0 and rate_per_m == 0 and rate_per_floor == 0 and pricing["labor_cost"] == 0:
    warnings.append("Расценки работ не заданы. ADMIN может внести их в формулу «Работы по монтажу» или в цену монтажа оборудования каталога.")
  unit = "кВт" if profile in ("ac", "vrf_vrv") else "м³/ч"
  design_value = calculation["result"]
  return {
    "ok": True,
    "profile": profile,
    "profile_title": next(row["title"] for row in INSTALLATION_PROFILES if row["code"] == profile),
    "site_name": values["site_name"],
    "inputs": values,
    "design_value": design_value,
    "design_unit": unit,
    "components": calculation["components"],
    "extra": dict(calculation["extra"], installation_work_cost=work_result["result"]),
    "equipment": selected_equipment,
    "equipment_recommendations": calculation["recommendations"],
    "equipment_lines": equipment_lines,
    "work_lines": work_lines,
    "material_lines": material_lines,
    "materials": material_catalog,
    "currency": pricing["currency"],
    "materials_cost": material_and_equipment_cost,
    "materials_base_cost": pricing.get("materials_base_cost"),
    "catalog_discount_amount": pricing.get("discount_total", 0.0),
    "catalog_discount_percent": pricing.get("discount_percent", 0.0),
    "undiscounted_total": (
      round(pricing.get("materials_base_cost", 0.0) + work_total, 2)
      if work_total is not None and not missing_prices else None
    ),
    "labor_cost": work_total,
    "total": total,
    "total_known": total is not None,
    "can_quote": bool(
      selected_equipment and not missing_materials and not missing_prices
      and work_total is not None and work_total > 0 and material_and_equipment_cost is not None
    ),
    "missing_materials": missing_materials,
    "missing_prices": missing_prices,
    "warnings": warnings,
    "assumptions": assumptions,
    "source": calculation["source"] + "\n" + install_formula["source"],
    "version": calculation["version"] + " / " + install_formula["version"],
    "formula": install_formula,
    "formula_work_lines": formula_work_lines,
    "selections": selections,
    "calculation_id": None
  }


def _save_installation(user, result, project_id=None):
  formula = result["formula"]
  details = {
    "profile": "installation_" + result["profile"],
    "components": result["components"],
    "extra": result["extra"],
    "materials": result["material_lines"],
    "works": result["work_lines"],
    "warnings": result["warnings"],
    "undiscounted_total": result.get("undiscounted_total"),
    "catalog_discount_amount": result.get("catalog_discount_amount", 0.0),
    "catalog_discount_percent": result.get("catalog_discount_percent", 0.0),
    "additional_discount_type": result.get("additional_discount_type", "percent"),
    "additional_discount_value": result.get("additional_discount_value", 0.0),
    "additional_discount_amount": result.get("additional_discount_amount", 0.0),
    "total": result["total"],
    "currency": result["currency"]
  }
  saved = Calculations.save_structured_calculation(
    user,
    formula,
    result["inputs"],
    {formula["code"]: formula["coefficients"] or {}},
    result["extra"].get("installation_work_cost", 0.0),
    result["currency"],
    result["source"],
    result["version"],
    details,
    project_id
  )
  if saved["ok"]:
    result["calculation_id"] = saved["calculation_id"]
  return saved


def _validate_installation_save(user, save_result, project_id):
  if not isinstance(save_result, bool):
    return "Некорректная команда сохранения."
  if save_result and user is None:
    return "Войдите в профиль, чтобы сохранить смету монтажа."
  if project_id is not None and (not isinstance(project_id, str) or not project_id):
    return "Некорректный проект."
  if project_id is not None:
    project = app_tables.projects.get_by_id(project_id)
    if project is None or not Core.can_access_project(project, user):
      return "Выберите доступный вам проект."
  return None


def _apply_additional_discount(result, discount_type="percent", discount_value=0):
  if discount_type not in ("percent", "amount"):
    return "Выберите скидку в процентах или денежной сумме."
  maximum = 100 if discount_type == "percent" else 1000000000
  value, error = _number(discount_value, "Скидка", 0, maximum, False)
  if error:
    return error
  if value is None:
    value = 0.0
  subtotal = result.get("total")
  if subtotal is None:
    if discount_type == "amount" and value > 0:
      return "Денежную скидку нельзя посчитать, пока не заданы цены каталога."
    discount_amount = None
    final_total = None
    percent = value if discount_type == "percent" else None
  else:
    discount_amount = (
      round(subtotal * value / 100.0, 2)
      if discount_type == "percent" else round(value, 2)
    )
    if discount_amount > subtotal:
      return "Скидка не может быть больше суммы сметы."
    final_total = round(subtotal - discount_amount, 2)
    percent = round(discount_amount / subtotal * 100, 3) if subtotal else 0.0
  result["subtotal"] = subtotal
  result["additional_discount_type"] = discount_type
  result["additional_discount_value"] = round(float(value), 3)
  result["additional_discount_amount"] = discount_amount
  result["additional_discount_percent"] = percent
  result["total"] = final_total
  result["total_known"] = final_total is not None
  result["can_quote"] = bool(result.get("can_quote") and final_total is not None)
  return None


def _clean_installation_result(result, include_materials):
  result["formula"] = result["formula"]["code"]
  result.pop("formula_work_lines", None)
  result.pop("selections", None)
  if include_materials:
    return result
  equipment_cost = sum(
    line["line_total"] for line in result.get("equipment_lines", [])
    if line.get("line_total") is not None
  )
  equipment_base_cost = sum(
    line.get("base_unit_price", line.get("unit_price")) * line["quantity"]
    for line in result.get("equipment_lines", [])
    if line.get("line_total") is not None
    and line.get("base_unit_price", line.get("unit_price")) is not None
  )
  customer_result = {
    key: result[key] for key in (
      "ok", "profile", "profile_title", "site_name", "inputs", "design_value",
      "design_unit", "components", "equipment", "equipment_recommendations",
      "currency", "labor_cost", "catalog_discount_amount",
      "catalog_discount_percent", "undiscounted_total", "subtotal",
      "additional_discount_type", "additional_discount_value",
      "additional_discount_amount", "additional_discount_percent", "total",
      "total_known", "can_quote", "missing_prices", "warnings", "assumptions",
      "source", "version", "formula", "calculation_id"
    ) if key in result
  }
  customer_result["equipment_cost"] = round(equipment_cost, 2)
  customer_result["equipment_base_cost"] = round(equipment_base_cost, 2)
  customer_result["materials_cost"] = None
  customer_result["customer_lines"] = [
    {"description": "Оборудование · базовая цена", "amount": round(equipment_base_cost, 2)},
    {"description": "Монтажные работы", "amount": result.get("labor_cost")},
    {
      "description": "Скидка каталога · {}%".format(
        result.get("catalog_discount_percent", 0.0)
      ),
      "amount": -result.get("catalog_discount_amount", 0.0)
    },
    {
      "description": "Дополнительная скидка",
      "amount": -result.get("additional_discount_amount", 0.0)
      if result.get("additional_discount_amount") is not None else None
    }
  ]
  return customer_result


def _calculate_installation_response(user, profile, inputs, material_selections,
                                     save_result, project_id, selected_equipment_id,
                                     include_materials, discount_type="percent",
                                     discount_value=0):
  error = _validate_installation_save(user, save_result, project_id)
  if error:
    return {"ok": False, "message": error}
  result = _calculate_installation(
    profile, inputs, material_selections, selected_equipment_id,
    include_materials=include_materials
  )
  if not result["ok"]:
    return result
  error = _apply_additional_discount(result, discount_type, discount_value)
  if error:
    return {"ok": False, "message": error}
  if save_result:
    saved = _save_installation(user, result, project_id)
    if not saved["ok"]:
      return saved
  return _clean_installation_result(result, include_materials)


@anvil.server.callable
def calculate_installation(profile, inputs, material_selections=None,
                           save_result=False, project_id=None,
                           selected_equipment_id=None):
  """Return the customer estimate without internal material or labour lines."""
  user = anvil.users.get_user()
  return _calculate_installation_response(
    user, profile, inputs, [], save_result, project_id, selected_equipment_id,
    False, "percent", 0
  )


@anvil.server.callable
@Core.staff_guard
def calculate_staff_installation(profile, inputs, material_selections=None,
                                 save_result=False, project_id=None,
                                 selected_equipment_id=None,
                                 discount_type="percent", discount_value=0):
  """Return the detailed installer estimate only to ADMIN and MODERATOR."""
  user = anvil.users.get_user()
  return _calculate_installation_response(
    user, profile, inputs, material_selections, save_result, project_id,
    selected_equipment_id, True, discount_type, discount_value
  )


@anvil.server.callable(require_user=True)
def create_installation_quote(profile, inputs, material_selections,
                              project_id, selected_equipment_id, terms=""):
  user = anvil.users.get_user()
  if user is None:
    return {"ok": False, "message": "Для создания КП войдите в профиль."}
  project = app_tables.projects.get_by_id(project_id) if isinstance(project_id, str) else None
  if project is None or not Core.can_access_project(project, user):
    return {"ok": False, "message": "Выберите или создайте свой проект."}
  if not selected_equipment_id:
    return {"ok": False, "message": "Выберите оборудование из каталога."}
  result = _calculate_installation(
    profile, inputs, [], selected_equipment_id, include_materials=False
  )
  if not result["ok"]:
    return result
  saved = _save_installation(user, result, project_id)
  if not saved["ok"]:
    return saved
  quote = Estimates.create_catalog_quote(
    project,
    user,
    result["selections"],
    terms,
    {
      "source": "installation_calculation",
      "profile": profile,
      "inputs": result["inputs"],
      "components": result["components"],
      "warnings": result["warnings"]
    },
    require_installation=False,
    require_work=True,
    extra_work_lines=result["formula_work_lines"]
  )
  if not quote["ok"]:
    quote["calculation_saved"] = bool(result.get("calculation_id"))
    quote["calculation_id"] = result.get("calculation_id")
    return quote
  quote["calculation_id"] = result.get("calculation_id")
  quote["message"] = "Расчёт монтажа сохранён; КП №{} создано.".format(quote["quote_number"])
  return quote
