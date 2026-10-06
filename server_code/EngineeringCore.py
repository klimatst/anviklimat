import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
from datetime import datetime, timezone
import Core


STAGES = (
  ("brief", "Новый проект", "Создайте объект и зафиксируйте исходные данные."),
  ("object", "Объект", "Объект и исходные параметры определены."),
  ("rooms", "Помещения", "Помещения и нагрузки готовы к расчёту."),
  ("calculation", "Расчёт", "Есть инженерные расчёты и выбранные сценарии."),
  ("selection", "Подбор", "Системы и оборудование собраны в проект."),
  ("estimate", "Смета", "Стоимость и спецификация сформированы."),
  ("installation", "Монтаж", "Проект передан в монтаж и пусконаладку."),
  ("service", "Сервис", "Объект переведён в жизненный цикл обслуживания."),
)




def _project(project_id):
  if not project_id:
    return None
  project = app_tables.projects.get_by_id(project_id)
  user = anvil.users.get_user()
  if project is None or user is None or not Core.can_access_project(project, user):
    return None
  return project


def _stage(snapshot):
  if snapshot["service_completed_count"] > 0 and snapshot["project_status"] in ("active", "completed", "service"):
    return 7
  if snapshot["commissioning_completed_count"] > 0 or snapshot["project_status"] in ("commissioning", "active"):
    return 6
  if snapshot["approved_quote_count"] > 0 or snapshot["project_status"] in ("approved", "installation"):
    return 5
  if snapshot["estimate_count"] > 0 and snapshot["bom_line_count"] > 0:
    return 5
  if snapshot["system_component_count"] > 0 or snapshot["system_count"] > 0:
    return 4
  if snapshot["calculation_count"] > 0:
    return 3
  if snapshot["room_count"] > 0:
    return 2
  if snapshot["object_ready"]:
    return 1
  return 0


def _product_label(product):
  if product is None:
    return "Товар не указан"
  brand = product["brand"]
  return "{} {}".format(brand["name"] if brand is not None else "", product["model"] or "").strip()


def _products_for_system(system):
  products = {}
  for row in app_tables.system_components.search(q.fetch_only("product"), system=system)[:200]:
    product = row["product"]
    if product is not None:
      products[product.get_id()] = product
  return products


def _candidate_compatibility_issues(product, existing_products):
  issues = []
  for existing in existing_products.values():
    if existing is None or existing.get_id() == product.get_id():
      continue
    rules = list(app_tables.compatibility.search(
      q.fetch_only("product", "compatible_product", "type", "rule"),
      q.any_of(q.all_of(product=product, compatible_product=existing), q.all_of(product=existing, compatible_product=product)),
      enabled=True
    )[:20])
    for rule in rules:
      first, second = rule["product"], rule["compatible_product"]
      if first is None or second is None:
        continue
      if rule["type"] == "incompatible":
        issues.append("{} несовместимо с {}.".format(_product_label(product), _product_label(second if first.get_id() == product.get_id() else first)))
      elif rule["type"] == "required":
        required = second if first.get_id() == product.get_id() else first
        if required.get_id() not in existing_products:
          issues.append("{} требует {}.".format(_product_label(product), _product_label(required)))
  return issues[:5]




@anvil.server.callable(require_user=True)
def get_project_engineering_snapshot(project_id):
  project = _project(project_id)
  if project is None:
    return {"ok": False, "message": "Проект недоступен."}

  obj = project["object"]
  rooms = list(app_tables.rooms.search(object=obj)[:500]) if obj is not None else []
  systems = list(app_tables.systems.search(project=project)[:200])
  calculations = list(app_tables.calculations.search(project=project)[:500])
  estimates = list(app_tables.estimates.search(project=project)[:50])
  quotes = list(app_tables.quotes.search(project=project)[:50])
  services = list(app_tables.service.search(project=project)[:200])
  approved_quote_count = sum(1 for quote in quotes if quote["status"] == "approved")
  commissioning_completed_count = sum(1 for row in services if row["service_type"] == "commissioning" and row["status"] == "completed")
  service_completed_count = sum(1 for row in services if row["status"] == "completed" and row["service_type"] in ("maintenance", "repair", "diagnosis", "measurement", "humidification_maintenance"))
  installation_count = sum(1 for row in services if row["service_type"] == "installation" and row["status"] != "cancelled")
  component_count = 0
  bom_line_count = 0
  system_family_counts = {"VRV / VRF": 0, "Вентиляция": 0, "Кондиционирование": 0, "Другое": 0}
  for system in systems:
    system_type = str(system["type"] or "").lower()
    if "vrf" in system_type or "vrv" in system_type:
      system_family_counts["VRV / VRF"] += 1
    elif "vent" in system_type or "air" in system_type and "condition" not in system_type:
      system_family_counts["Вентиляция"] += 1
    elif any(token in system_type for token in ("condition", "split", "multi")):
      system_family_counts["Кондиционирование"] += 1
    else:
      system_family_counts["Другое"] += 1
  for system in systems:
    component_count += len(list(app_tables.system_components.search(system=system)[:500]))
    bom_line_count += len(list(app_tables.bom_lines.search(q.fetch_only("line_key"), system=system)[:600]))

  object_parameters = (obj["parameters"] or {}) if obj is not None else {}
  engineering_profile = object_parameters.get("engineering_profile", "combined")
  engineering_goal = object_parameters.get("engineering_goal", "design")
  project_priority = object_parameters.get("project_priority", "standard")
  constraints = str(object_parameters.get("constraints", "") or "").strip()
  object_ready = bool(
    obj is not None and
    str(obj["name"] or "").strip()
  )
  engineering_brief_ready = bool(object_ready and engineering_profile and engineering_goal and project_priority)
  snapshot = {
    "project_id": project.get_id(),
    "project_code": project["code"] or "",
    "project_title": project["title"] or "",
    "project_status": project["status"] or "draft",
    "object_ready": object_ready,
    "object_name": (obj["name"] if obj is not None else "") or "",
    "engineering_profile": engineering_profile,
    "engineering_goal": engineering_goal,
    "project_priority": project_priority,
    "constraints": constraints,
    "engineering_brief_ready": engineering_brief_ready,
    "room_count": len(rooms),
    "system_count": len(systems),
    "system_component_count": component_count,
    "calculation_count": len(calculations),
    "estimate_count": len(estimates),
    "quote_count": len(quotes),
    "approved_quote_count": approved_quote_count,
    "service_count": len(services),
    "installation_count": installation_count,
    "commissioning_completed_count": commissioning_completed_count,
    "service_completed_count": service_completed_count,
    "bom_line_count": bom_line_count,
    "system_family_counts": system_family_counts,
    "lifecycle_ready": bool(approved_quote_count and installation_count and commissioning_completed_count),
  }
  index = _stage(snapshot)
  key, title, description = STAGES[index]
  next_actions = {
    0: "Заполнить инженерный бриф и зафиксировать объект.",
    1: "Добавить помещения и основные исходные нагрузки.",
    2: "Запустить независимые расчёты и проверить исходные допущения.",
    3: "Выбрать системы и связать оборудование с расчётами.",
    4: "Сформировать BOM, проверить совместимость и закрыть инженерные пробелы.",
    5: "Согласовать КП и подготовить пакет передачи в монтаж.",
    6: "Зафиксировать пусконаладку и актировать готовность объекта.",
    7: "Поддерживать сервисную историю, регламент и жизненный цикл оборудования."
  }
  risk_flags = []
  if not object_ready:
    risk_flags.append("Не задан объект")
  if object_ready and not snapshot["room_count"]:
    risk_flags.append("Нет помещений")
  if snapshot["room_count"] and not snapshot["calculation_count"]:
    risk_flags.append("Нет расчётов")
  if snapshot["calculation_count"] and not snapshot["system_count"]:
    risk_flags.append("Нет инженерных систем")
  if snapshot["system_count"] and not snapshot["system_component_count"]:
    risk_flags.append("Нет компонентов систем")
  if snapshot["system_component_count"] and not snapshot["bom_line_count"]:
    risk_flags.append("BOM ещё не сформирован")
  if snapshot["estimate_count"] and not snapshot["quote_count"]:
    risk_flags.append("Смета есть, КП не создано")
  if snapshot["quote_count"] and not snapshot["approved_quote_count"]:
    risk_flags.append("КП ещё не согласовано")
  if snapshot["approved_quote_count"] and not snapshot["installation_count"]:
    risk_flags.append("Нет монтажной записи")
  if snapshot["installation_count"] and not snapshot["commissioning_completed_count"]:
    risk_flags.append("Пусконаладка не закрыта")
  snapshot.update({
    "stage_key": key, "stage_title": title, "stage_description": description,
    "stage_index": index,
    "progress": round(index / float(len(STAGES) - 1) * 100),
    "next_action": next_actions[index],
    "risk_flags": risk_flags[:8],
    "engineering_score": min(100,
      (10 if object_ready else 0) + (8 if engineering_brief_ready else 0) +
      (12 if snapshot["room_count"] else 0) + (14 if snapshot["calculation_count"] else 0) +
      (14 if snapshot["system_count"] else 0) + (10 if snapshot["system_component_count"] else 0) +
      (10 if snapshot["bom_line_count"] else 0) + (8 if snapshot["estimate_count"] else 0) +
      (5 if snapshot["quote_count"] else 0) + (4 if snapshot["approved_quote_count"] else 0) +
      (5 if snapshot["installation_count"] else 0) + (5 if snapshot["commissioning_completed_count"] else 0) +
      (5 if snapshot["service_completed_count"] else 0)
    ),
  })
  return {"ok": True, "snapshot": snapshot}

@anvil.server.callable(require_user=True)
def get_engineering_quality_gate(project_limit=250):
  user = anvil.users.get_user()
  if user is None:
    return {"ok": False, "message": "Требуется вход."}
  context = Core.get_access_context()
  if context["role_code"] != "admin" and "projects.manage" not in context["permissions"]:
    return {"ok": False, "message": "Недостаточно прав."}

  if isinstance(project_limit, bool) or not isinstance(project_limit, int) or not 1 <= project_limit <= 250:
    return {"ok": False, "message": "Некорректный лимит Quality Gate."}
  projects = list(app_tables.projects.search(order_by("updated_at", ascending=False))[:project_limit]
  counts = {
    "projects_without_object": 0, "projects_without_rooms": 0,
    "rooms_without_calculations": 0, "calculations_without_system": 0,
    "systems_without_components": 0, "systems_without_bom": 0,
    "estimates_without_quote": 0, "approved_quotes_without_installation": 0,
    "installations_without_commissioning": 0,
  }
  issues = []
  for project in projects:
    obj = project["object"]
    code = project["code"] or project.get_id()
    if obj is None or not str(obj["name"] or "").strip():
      counts["projects_without_object"] += 1
      issues.append({"severity": "high", "project": code, "message": "Проект без полноценного объекта."})
      continue
    parameters = obj["parameters"] or {}
    if not parameters.get("engineering_profile"):
      issues.append({"severity": "medium", "project": code, "message": "Не задан инженерный профиль."})
    rooms = list(app_tables.rooms.search(object=obj)[:200])
    calculations = list(app_tables.calculations.search(project=project)[:500])
    systems = list(app_tables.systems.search(project=project)[:100])
    estimates = list(app_tables.estimates.search(project=project)[:20])
    quotes = list(app_tables.quotes.search(project=project)[:20])
    services = list(app_tables.service.search(project=project)[:100])
    if not rooms:
      counts["projects_without_rooms"] += 1
      issues.append({"severity": "medium", "project": code, "message": "Нет помещений для инженерного расчёта."})
    if rooms and not calculations:
      counts["rooms_without_calculations"] += len(rooms)
      issues.append({"severity": "medium", "project": code, "message": "Есть помещения, но нет расчётов."})
    if calculations and not systems:
      counts["calculations_without_system"] += len(calculations)
      issues.append({"severity": "high", "project": code, "message": "Есть расчёты, но нет инженерной системы."})
    for system in systems:
      component_count = len(list(app_tables.system_components.search(system=system)[:200]))
      if component_count == 0:
        counts["systems_without_components"] += 1
        issues.append({"severity": "high", "project": code, "message": "Система без компонентов."})
      bom_count = len(list(app_tables.bom_lines.search(system=system)[:600]))
      if component_count and bom_count == 0:
        counts["systems_without_bom"] += 1
        issues.append({"severity": "medium", "project": code, "message": "Система собрана, но BOM не сформирован."})
    if estimates and not quotes:
      counts["estimates_without_quote"] += 1
      issues.append({"severity": "medium", "project": code, "message": "Смета есть, но коммерческое предложение не создано."})
    approved = any(row["status"] == "approved" for row in quotes)
    installation = any(row["service_type"] == "installation" and row["status"] != "cancelled" for row in services)
    commissioning = any(row["service_type"] == "commissioning" and row["status"] == "completed" for row in services)
    if approved and not installation:
      counts["approved_quotes_without_installation"] += 1
      issues.append({"severity": "high", "project": code, "message": "Согласованное КП не связано с монтажной записью."})
    if installation and not commissioning:
      counts["installations_without_commissioning"] += 1
      issues.append({"severity": "medium", "project": code, "message": "Монтаж есть, но пусконаладка не закрыта."})
    if len(issues) >= 60:
      break
  high_count = sum(1 for item in issues if item["severity"] == "high")
  issue_count = sum(counts.values())
  return {
    "ok": True, "healthy": issue_count == 0, "issue_count": issue_count,
    "high_count": high_count, "counts": counts, "issues": issues[:60],
    "checked_projects": len(projects), "generated_at": datetime.now(timezone.utc)
  }


@anvil.server.callable(require_user=True)
def get_project_action_center(project_id):
  """Return prioritized actions for the current engineering lifecycle."""
  snapshot_result = get_project_engineering_snapshot(project_id)
  if not snapshot_result.get("ok"):
    return snapshot_result
  snapshot = snapshot_result["snapshot"]
  actions = []

  def add(key, priority, title, description):
    actions.append({
      "key": key,
      "priority": priority,
      "title": title,
      "description": description,
    })

  if not snapshot["object_ready"]:
    add("object", "critical", "Заполнить объект",
        "Зафиксируйте объект и исходные ограничения до инженерного расчёта.")
  if snapshot["object_ready"] and not snapshot["room_count"]:
    add("rooms", "high", "Добавить помещения",
        "Без помещений расчётная модель объекта неполная.")
  if snapshot["room_count"] and not snapshot["calculation_count"]:
    add("calculations", "high", "Запустить расчёты",
        "Выполните независимые расчёты для выбранного инженерного профиля.")
  if snapshot["calculation_count"] and not snapshot["system_count"]:
    add("systems", "high", "Собрать инженерные системы",
        "Свяжите расчёты с реальными системами объекта.")
  if snapshot["system_count"] and not snapshot["system_component_count"]:
    add("components", "high", "Собрать состав систем",
        "Добавьте оборудование и компоненты в конструктор.")
  if snapshot["system_component_count"] and not snapshot["bom_line_count"]:
    add("bom", "high", "Сформировать BOM",
        "Переведите состав систем в проверяемую спецификацию.")
  if snapshot["bom_line_count"] and not snapshot["estimate_count"]:
    add("estimate", "high", "Рассчитать смету",
        "Оцените материалы, работы и расходные материалы по актуальному BOM.")
  if snapshot["estimate_count"] and not snapshot["quote_count"]:
    add("quote", "high", "Создать КП",
        "Сформируйте коммерческое предложение из последней версии сметы.")
  if snapshot["quote_count"] and not snapshot["approved_quote_count"]:
    add("approval", "medium", "Согласовать КП",
        "Переведите предложение из черновика/отправки в согласованный статус.")
  if snapshot["approved_quote_count"] and not snapshot["installation_count"]:
    add("installation", "high", "Передать в монтаж",
        "Создайте монтажную запись и зафиксируйте фактический состав работ.")
  if snapshot["installation_count"] and not snapshot["commissioning_completed_count"]:
    add("commissioning", "high", "Закрыть ПНР",
        "Зафиксируйте завершённую пусконаладку перед передачей объекта в эксплуатацию.")
  if snapshot["commissioning_completed_count"] and not snapshot["service_completed_count"]:
    add("service", "medium", "Запланировать сервис",
        "Переведите объект в управляемый жизненный цикл обслуживания.")
  if not actions:
    add("lifecycle", "info", "Контур проекта собран",
        "Поддерживайте расчёты, спецификацию, документы и сервисную историю в актуальном состоянии.")

  priority_rank = {"critical": 0, "high": 1, "medium": 2, "info": 3}
  actions.sort(key=lambda item: priority_rank[item["priority"]])
  return {
    "ok": True,
    "stage_key": snapshot["stage_key"],
    "engineering_score": snapshot["engineering_score"],
    "lifecycle_ready": snapshot["lifecycle_ready"],
    "actions": actions[:8],
  }


DECISION_ENGINE_VERSION = "1.0"
SELECTION_LIMIT = 12


def _product_specs_map(product):
  values = {}
  try:
    rows = app_tables.product_specs.search(product=product, visible=True)[:120]
  except Exception:
    rows = []
  for row in rows:
    key = (row["key"] or "").strip().casefold()
    raw = str(row["value"] or "").strip().replace(",", ".")
    if not key or not raw:
      continue
    first_token = raw.replace("×", " ").replace("x", " ").split()[0]
    try:
      values[key] = float(first_token)
    except (TypeError, ValueError, IndexError):
      continue
  return values


def _system_family(system_type):
  value = str(system_type or "").casefold()
  if "vrf" in value or "vrv" in value:
    return "vrv_vrf"
  if "vent" in value or "ahu" in value or "recovery" in value:
    return "ventilation"
  if "split" in value or "commercial_ac" in value or "air" in value:
    return "conditioning"
  return "other"


def _selection_candidates(project_id, system_id):
  project = app_tables.projects.get_by_id(project_id)
  system = app_tables.systems.get_by_id(system_id)
  if project is None or system is None:
    return None, None, "Проект или система не найдены."
  user = anvil.users.get_user()
  if user is None or not Core.can_access_project(project, user):
    return None, None, "Проект недоступен этой учётной записи."

  snapshot_result = get_project_engineering_snapshot(project_id)
  if not snapshot_result.get("ok"):
    return None, None, snapshot_result.get("message", "Не удалось получить контекст проекта.")
  snapshot = snapshot_result["snapshot"]

  # Selection is intentionally derived only from structured catalog fields.
  # Never invent missing technical values.
  calculation_rows = list(app_tables.calculations.search(project=project)[:500])
  target_kw = 0.0
  target_airflow = 0.0
  for row in calculation_rows:
    payload = row["result"] if "result" in row else {}
    payload = payload if isinstance(payload, dict) else {}
    parameters = row["parameters"] if "parameters" in row else {}
    parameters = parameters if isinstance(parameters, dict) else {}
    merged = dict(parameters)
    merged.update(payload)
    for key in ("required_kw", "cooling_kw", "cooling_capacity_kw", "load_kw", "capacity_kw"):
      value = merged.get(key)
      if isinstance(value, (int, float)) and not isinstance(value, bool) and value > target_kw:
        target_kw = float(value)
    for key in ("airflow_m3h", "airflow", "required_airflow_m3h", "supply_airflow_m3h", "exhaust_airflow_m3h"):
      value = merged.get(key)
      if isinstance(value, (int, float)) and not isinstance(value, bool) and value > target_airflow:
        target_airflow = float(value)

  family = _system_family(system["type"])
  categories = []
  category_codes = {
    "conditioning": ("air-conditioning", "multi-split-systems", "semi-industrial"),
    "vrv_vrf": ("vrf-vrv",),
    "ventilation": ("ventilation",),
    "other": ()
  }[family]
  for code in category_codes:
    category = app_tables.catalog_categories.get(code=code)
    if category is not None:
      categories.append(category)

  products = []
  if categories:
    for product in app_tables.products.search(active=True)[:3000]:
      if product["category"] not in categories and product["subcategory"] not in categories:
        continue
      products.append(product)
      if len(products) >= 600:
        break

  return system, snapshot, {
    "family": family,
    "target_kw": target_kw,
    "target_airflow": target_airflow,
    "products": products
  }


@anvil.server.callable(require_user=True)
def get_engineering_decision(project_id, system_id):
  if not isinstance(project_id, str) or not isinstance(system_id, str):
    return {"ok": False, "message": "Некорректный проект или система."}
  system, snapshot, context = _selection_candidates(project_id, system_id)
  if isinstance(context, str):
    return {"ok": False, "message": context}

  family = context["family"]
  target_kw = context["target_kw"]
  target_airflow = context["target_airflow"]
  ranked = []
  existing_products = _products_for_system(system)
  for product in context["products"]:
    specs = _product_specs_map(product)
    cooling = next((specs[k] for k in (
      "мощность охлаждения", "охлаждение, квт", "холодопроизводительность",
      "номинальная мощность охлаждения"
    ) if k in specs), None)
    heating = next((specs[k] for k in (
      "мощность обогрева", "обогрев, квт", "теплопроизводительность",
      "номинальная мощность обогрева"
    ) if k in specs), None)
    airflow = next((specs[k] for k in (
      "производительность", "производительность, м³/ч", "расход воздуха",
      "воздушный расход"
    ) if k in specs), None)

    target = target_kw if family in ("conditioning", "vrv_vrf") else target_airflow
    capacity = cooling if family in ("conditioning", "vrv_vrf") else airflow
    score = 0.0
    reasons = []
    warnings = []
    hard_fail = False

    if family in ("conditioning", "vrv_vrf"):
      if target > 0 and capacity is not None:
        ratio = capacity / target
        if ratio < 1.0:
          score += 8
          warnings.append("Мощность ниже расчётной потребности.")
          hard_fail = True
        elif ratio <= 1.35:
          score += 70
          reasons.append("Расчётная потребность закрывается с инженерным запасом.")
        else:
          score += 48
          warnings.append("Есть заметное превышение расчётной мощности.")
        score += max(0.0, 15.0 - abs(ratio - 1.15) * 15.0)
      elif target == 0:
        score += 15
        warnings.append("Нет числовой расчётной потребности — требуется ручная проверка.")
      else:
        warnings.append("В каталоге нет структурированной мощности для ранжирования.")
        hard_fail = True
    elif family == "ventilation":
      if target > 0 and airflow is not None:
        ratio = airflow / target
        if ratio < 1.0:
          score += 8
          warnings.append("Производительность ниже расчётного расхода воздуха.")
          hard_fail = True
        elif ratio <= 1.30:
          score += 70
          reasons.append("Производительность закрывает расчётный расход с запасом.")
        else:
          score += 48
          warnings.append("Производительность существенно выше расчётной.")
        score += max(0.0, 15.0 - abs(ratio - 1.12) * 15.0)
      elif target == 0:
        score += 15
        warnings.append("Нет целевого расхода воздуха — подбор носит предварительный характер.")
      else:
        warnings.append("Нет структурированной производительности в каталоге.")
        hard_fail = True
    else:
      score += 10
      warnings.append("Для этого типа системы пока нет специализированной модели подбора.")

    if heating is not None and family in ("conditioning", "vrv_vrf"):
      reasons.append("Есть отдельная характеристика мощности обогрева.")

    price = app_tables.product_prices.get(product=product)
    if price is not None and price["sale_price"] is not None:
      score += 5
      reasons.append("Есть цена продажи для сметы.")
    else:
      warnings.append("Цена отсутствует — позиция не готова для полного коммерческого цикла.")

    if product.get_id() in existing_products:
      score += 5
      reasons.append("Модель уже находится в составе текущей системы.")

    compatibility_issues = _candidate_compatibility_issues(product, existing_products)
    if compatibility_issues:
      score -= min(30, 10 * len(compatibility_issues))
      warnings.extend(compatibility_issues[:3])

    price_ready = price is not None and price["sale_price"] is not None
    compatible = not compatibility_issues
    decision = "recommended" if not hard_fail and compatible and score >= 75 else "candidate"
    ranked.append({
      "product_id": product.get_id(),
      "label": _product_label(product),
      "model": product["model"] or "",
      "sku": product["sku"] or "",
      "score": round(max(0.0, min(100.0, score)), 1),
      "capacity": capacity,
      "target": target or None,
      "capacity_unit": "кВт" if family in ("conditioning", "vrv_vrf") else "м³/ч",
      "price_ready": price_ready,
      "compatible": compatible,
      "reasons": reasons[:5],
      "warnings": warnings[:5],
      "decision": decision,
      "existing": product.get_id() in existing_products
    })

  ranked.sort(key=lambda row: (-row["score"], row["label"].casefold()))
  selected = ranked[:SELECTION_LIMIT]
  return {
    "ok": True,
    "version": DECISION_ENGINE_VERSION,
    "project_id": project_id,
    "system_id": system_id,
    "family": family,
    "target_capacity_kw": target_kw or None,
    "target_airflow_m3h": target_airflow or None,
    "selection_ready": bool(selected),
    "top_candidate": selected[0] if selected else None,
    "candidates": selected,
    "message": "Подбор построен только на фактических характеристиках каталога и доступных расчётных данных. Неполные данные понижает confidence и требуют инженерной проверки."
  }


@anvil.server.callable(require_user=True)
def get_project_engineering_decisions(project_id):
  """Return explainable Smart Selection candidates for every system in a project."""
  project = _project(project_id)
  if project is None:
    return {"ok": False, "message": "Проект недоступен.", "systems": []}
  systems = list(app_tables.systems.search(order_by("title"), project=project)[:20])
  result = []
  for system in systems:
    decision = get_engineering_decision(project_id, system.get_id())
    if not decision.get("ok"):
      result.append({
        "system_id": system.get_id(), "system_title": system["title"] or "Система",
        "system_type": system["type"] or "other", "ok": False,
        "message": decision.get("message", "Подбор недоступен."), "candidates": []
      })
      continue
    candidates = []
    for candidate in decision.get("candidates", [])[:4]:
      item = dict(candidate)
      item["system_id"] = system.get_id()
      item["system_title"] = system["title"] or "Система"
      item["system_type"] = system["type"] or "other"
      candidates.append(item)
    result.append({
      "system_id": system.get_id(), "system_title": system["title"] or "Система",
      "system_type": system["type"] or "other", "ok": True,
      "family": decision.get("family"),
      "target_capacity_kw": decision.get("target_capacity_kw"),
      "target_airflow_m3h": decision.get("target_airflow_m3h"),
      "candidates": candidates,
      "top_candidate": candidates[0] if candidates else None
    })
  return {
    "ok": True,
    "project_id": project_id,
    "system_count": len(systems),
    "systems": result,
    "message": "Smart Selection построен отдельно для каждой инженерной системы проекта; результаты не смешиваются между контурами."
  }


@anvil.server.callable(require_user=True)
def get_engineering_control_room():
  user = anvil.users.get_user()
  if user is None:
    return {"ok": False, "message": "Требуется вход."}
  context = Core.get_access_context()
  if context["role_code"] != "admin" and "projects.manage" not in context["permissions"]:
    return {"ok": False, "message": "Недостаточно прав."}
  projects = list(app_tables.projects.search(order_by("updated_at", ascending=False))[:250])
  active_statuses = {"calculation", "review", "ready", "quoted", "approved", "installation", "commissioning"}
  active_projects = sum(1 for p in projects if p["status"] in active_statuses)
  systems = list(app_tables.systems.search()[:500])
  calculations = list(app_tables.calculations.search()[:1000])
  estimates = list(app_tables.estimates.search()[:300])
  needs_attention = 0
  recent = []
  for project in projects[:12]:
    snapshot_result = get_project_engineering_snapshot(project.get_id())
    if snapshot_result.get("ok"):
      snapshot = snapshot_result["snapshot"]
      if snapshot.get("risk_flags"):
        needs_attention += 1
      recent.append({
        "id": project.get_id(), "code": project["code"] or "",
        "title": project["title"] or "Без названия",
        "status": project["status"] or "draft",
        "stage_title": snapshot["stage_title"],
        "progress": snapshot["progress"],
        "engineering_score": snapshot["engineering_score"],
        "risk_count": len(snapshot.get("risk_flags") or [])
      })
  quality = get_engineering_quality_gate(80)
  quality_ok = quality.get("ok") and quality.get("healthy")
  return {
    "ok": True,
    "metrics": {
      "projects": len(projects), "active_projects": active_projects,
      "needs_attention": needs_attention, "systems": len(systems),
      "calculations": len(calculations), "estimates": len(estimates),
      "quality_gate_ok": bool(quality_ok), "quality_issue_count": quality.get("issue_count", 0),
      "quality_high_count": quality.get("high_count", 0)
    },
    "recent_projects": recent,
    "quality_gate": {
      "healthy": bool(quality_ok), "issue_count": quality.get("issue_count", 0),
      "high_count": quality.get("high_count", 0), "issues": quality.get("issues", [])[:12]
    },
    "generated_at": datetime.now(timezone.utc)
  }
