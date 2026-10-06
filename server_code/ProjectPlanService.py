import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by
from datetime import datetime, timezone
import Core


MAX_FILE_BYTES = 25 * 1024 * 1024
ALLOWED_TYPES = {
  "image/png", "image/jpeg", "image/webp",
  "application/pdf", "application/acad", "application/dxf",
  "image/vnd.dwg", "application/octet-stream"
}


def _user():
  return anvil.users.get_user()


def _project(project_id):
  if not isinstance(project_id, str) or not project_id:
    return None, "Некорректный идентификатор проекта."
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return None, "Проект не найден."
  user = _user()
  if user is None or not Core.can_access_project(project, user):
    return None, "Проект недоступен этой учётной записи."
  return project, None


def _safe_settings(value):
  return value if isinstance(value, dict) else {}


@anvil.server.callable(require_user=True)
def get_project_plan(project_id):
  project, error = _project(project_id)
  if error:
    return {"ok": False, "message": error}
  row = app_tables.project_plans.get(project=project)
  if row is None:
    return {
      "ok": True, "plan": None,
      "message": "План ещё не загружен."
    }
  settings = _safe_settings(row["settings"])
  return {
    "ok": True,
    "plan": {
      "id": row.get_id(),
      "title": row["title"] or "План объекта",
      "file_name": row["file_name"] or "",
      "content_type": row["content_type"] or "",
      "scale_m_per_px": settings.get("scale_m_per_px"),
      "settings": settings,
      "file": row["file"]
    },
    "message": "План загружен."
  }


@anvil.server.callable(require_user=True)
def upload_project_plan(project_id, media, title="План объекта"):
  project, error = _project(project_id)
  if error:
    return {"ok": False, "message": error}
  if media is None:
    return {"ok": False, "message": "Выберите файл плана."}
  try:
    length = int(media.length or 0)
  except (TypeError, ValueError):
    length = 0
  if length <= 0 or length > MAX_FILE_BYTES:
    return {"ok": False, "message": "Файл должен быть от 1 байта до 25 МБ."}
  content_type = str(media.content_type or "").lower()
  if content_type not in ALLOWED_TYPES and not content_type.startswith("image/"):
    return {"ok": False, "message": "Поддерживаются изображения, PDF, DWG и DXF."}
  now = datetime.now(timezone.utc)
  row = app_tables.project_plans.get(project=project)
  settings = _safe_settings(row["settings"]) if row is not None else {}
  if row is None:
    row = app_tables.project_plans.add_row(
      project=project,
      title=(title or "План объекта")[:160],
      file_name=(media.name or "plan")[:255],
      content_type=content_type,
      file=media,
      settings=settings,
      created_at=now,
      updated_at=now
    )
    action = "project.plan_uploaded"
  else:
    row.update(
      title=(title or "План объекта")[:160],
      file_name=(media.name or row["file_name"] or "plan")[:255],
      content_type=content_type,
      file=media,
      updated_at=now
    )
    action = "project.plan_replaced"
  Core.log_audit(
    actor=_user(), action=action, entity_type="project_plan",
    entity_id=row.get_id(),
    details={"project": project["code"], "file_name": row["file_name"]},
    created_at=now
  )
  return {
    "ok": True,
    "plan": {
      "id": row.get_id(), "title": row["title"],
      "file_name": row["file_name"], "content_type": row["content_type"],
      "scale_m_per_px": settings.get("scale_m_per_px"),
      "settings": settings, "file": row["file"]
    },
    "message": "План объекта загружен."
  }


def _sync_engineering_objects(project, plan_id, settings, user):
  objects = settings.get("objects") if isinstance(settings, dict) else []
  if not isinstance(objects, list):
    return
  wanted = {}
  for obj in objects:
    if not isinstance(obj, dict):
      continue
    system_id = obj.get("system_id")
    obj_id = obj.get("id")
    if not isinstance(system_id, str) or not system_id or not isinstance(obj_id, str) or not obj_id:
      continue
    system = app_tables.systems.get_by_id(system_id)
    if system is None or system["project"] is None or system["project"].get_id() != project.get_id():
      continue
    wanted[obj_id] = (system, obj)

  touched = set()
  for system, obj in wanted.values():
    rows = list(app_tables.system_components.search(system=system)[:300])
    row = next(
      (item for item in rows
       if (item["properties"] or {}).get("digital_twin_plan_id") == plan_id
       and (item["properties"] or {}).get("digital_twin_object_id") == obj["id"]),
      None
    )
    kind = obj.get("kind") or "other"
    engineering_kind = "equipment" if kind in (
      "indoor", "outdoor", "vrf", "ahu", "diffuser", "vent"
    ) else "route" if kind in (
      "drain", "route_refrigerant", "route_duct", "route_cable", "route_hydronic"
    ) else "other"
    props = dict(row["properties"] or {}) if row is not None else {}
    props.update({
      "digital_twin_plan_id": plan_id,
      "digital_twin_object_id": obj["id"],
      "digital_twin_kind": kind,
      "digital_twin_source": "plan"
    })
    values = {
      "system": system, "kind": engineering_kind,
      "name": str(obj.get("name") or kind)[:120],
      "quantity": 1,
      "properties": props,
      "position_x": float(obj.get("x") or 0),
      "position_y": float(obj.get("y") or 0),
      "sort_order": float(obj.get("y") or 0) * 20000 + float(obj.get("x") or 0)
    }
    if row is None:
      row = app_tables.system_components.add_row(**values)
    else:
      row.update(**values)
    touched.add(row.get_id())

  for system in app_tables.systems.search(project=project)[:100]:
    for row in app_tables.system_components.search(system=system)[:300]:
      props = row["properties"] or {}
      if props.get("digital_twin_plan_id") == plan_id and row.get_id() not in touched:
        row.delete()


@anvil.server.callable(require_user=True)
def save_project_plan(project_id, plan_data):
  project, error = _project(project_id)
  if error:
    return {"ok": False, "message": error}
  if not isinstance(plan_data, dict):
    return {"ok": False, "message": "Некорректные данные плана."}
  row = app_tables.project_plans.get(project=project)
  if row is None:
    return {"ok": False, "message": "Сначала загрузите план объекта."}
  settings = plan_data.get("settings")
  if not isinstance(settings, dict):
    return {"ok": False, "message": "Параметры плана должны быть объектом."}
  try:
    import json
    if len(json.dumps(settings, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 400000:
      return {"ok": False, "message": "Схема плана слишком большая."}
  except (TypeError, ValueError, OverflowError, RecursionError):
    return {"ok": False, "message": "Параметры плана содержат недопустимые данные."}
  scale = settings.get("scale_m_per_px")
  if scale is not None:
    try:
      scale = float(scale)
    except (TypeError, ValueError):
      return {"ok": False, "message": "Масштаб должен быть числом."}
    if scale <= 0 or scale > 100:
      return {"ok": False, "message": "Масштаб должен быть от 0 до 100 м/пиксель."}
    settings["scale_m_per_px"] = scale
  title = str(plan_data.get("title") or row["title"] or "План объекта").strip()[:160]
  now = datetime.now(timezone.utc)
  row.update(title=title, settings=settings, updated_at=now)
  _sync_engineering_objects(project, row.get_id(), settings, _user())
  Core.log_audit(
    actor=_user(), action="project.plan_updated",
    entity_type="project_plan", entity_id=row.get_id(),
    details={"project": project["code"]}, created_at=now
  )
  return {"ok": True, "message": "Схема плана сохранена.", "settings": settings}


@anvil.server.callable(require_user=True)
def delete_project_plan(project_id):
  project, error = _project(project_id)
  if error:
    return {"ok": False, "message": error}
  row = app_tables.project_plans.get(project=project)
  if row is None:
    return {"ok": True, "message": "План уже удалён."}
  row.delete()
  return {"ok": True, "message": "План удалён."}
