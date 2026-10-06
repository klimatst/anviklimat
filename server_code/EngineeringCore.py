import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by
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


def _count(table, **filters):
  try:
    return len(list(table.search(**filters)[:5000]))
  except Exception:
    return 0


def _stage(snapshot):
  if snapshot["service_count"] > 0:
    return 7
  if snapshot["project_status"] in ("installation", "commissioning", "active"):
    return 6
  if snapshot["estimate_count"] > 0:
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
  component_count = 0
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
    "service_count": len(services),
    "system_family_counts": system_family_counts,
  }
  index = _stage(snapshot)
  key, title, description = STAGES[index]
  snapshot.update({
    "stage_key": key,
    "stage_title": title,
    "stage_description": description,
    "stage_index": index,
    "progress": round(index / float(len(STAGES) - 1) * 100),
    "engineering_score": min(
      100,
      (12 if object_ready else 0) +
      (8 if engineering_brief_ready else 0) +
      (20 if snapshot["room_count"] else 0) +
      (20 if snapshot["system_count"] else 0) +
      (15 if snapshot["calculation_count"] else 0) +
      (10 if snapshot["system_component_count"] else 0) +
      (10 if snapshot["estimate_count"] else 0) +
      (5 if snapshot["quote_count"] else 0) +
      (5 if snapshot["service_count"] else 0)
    ),
  })
  return {"ok": True, "snapshot": snapshot}


@anvil.server.callable(require_user=True)
def get_engineering_control_room():
  user = anvil.users.get_user()
  if user is None:
    return {"ok": False, "message": "Требуется вход."}
  context = Core.get_access_context()
  if context["role_code"] != "admin" and "projects.manage" not in context["permissions"]:
    return {"ok": False, "message": "Недостаточно прав."}

  projects = list(app_tables.projects.search(order_by("updated_at", ascending=False))[:500])
  systems = _count(app_tables.systems)
  calculations = _count(app_tables.calculations)
  estimates = _count(app_tables.estimates)
  services = _count(app_tables.service)
  active = sum(1 for row in projects if (row["status"] or "draft") not in ("completed", "archived"))
  needs_attention = sum(1 for row in projects if (row["status"] or "draft") in ("draft", "blocked", "on_hold"))

  return {
    "ok": True,
    "metrics": {
      "projects": len(projects),
      "active_projects": active,
      "needs_attention": needs_attention,
      "systems": systems,
      "calculations": calculations,
      "estimates": estimates,
      "services": services,
    },
    "recent_projects": [
      {
        "id": row.get_id(),
        "code": row["code"] or "",
        "title": row["title"] or row["code"] or "Без названия",
        "status": row["status"] or "draft",
        "updated_at": row["updated_at"],
      }
      for row in projects[:12]
    ],
    "generated_at": datetime.now(timezone.utc),
  }
