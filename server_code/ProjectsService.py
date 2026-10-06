import anvil.secrets
from datetime import datetime, timezone
import json
import math
import uuid

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import ConstructorService as Constructor


OBJECT_TYPES = [
  ("apartment", "Квартира"), ("house", "Дом"), ("office", "Офис"),
  ("shop", "Магазин"), ("restaurant", "Ресторан"), ("hotel", "Отель"),
  ("warehouse", "Склад"), ("production", "Производство"),
  ("server_room", "Серверная"), ("medical", "Медицинский объект"),
  ("pool", "Бассейн"), ("sports", "Спортивный объект"),
  ("industrial", "Промышленный объект"), ("other", "Другой")
]
PROJECT_STATUSES = [
  ("draft", "Черновик"), ("calculation", "Расчёт"), ("review", "Проверка"),
  ("ready", "Готов"), ("quoted", "Предложение"), ("approved", "Согласован"),
  ("installation", "Монтаж"), ("commissioning", "Пусконаладка"),
  ("completed", "Завершён"), ("archived", "Архив")
]
OBJECT_NAMES = dict(OBJECT_TYPES)
STATUS_NAMES = dict(PROJECT_STATUSES)
PAGE_SIZE = 20
MAX_PARAMETER_BYTES = 4000
MAX_PARAMETER_FIELDS = 32


def _user():
  return anvil.users.get_user()


def _text(value, label, maximum, required=False):
  if value is None:
    value = ""
  if not isinstance(value, str):
    return None, "Проверьте поле «{}».".format(label)
  value = value.strip()
  if required and not value:
    return None, "Заполните поле «{}».".format(label)
  if len(value) > maximum:
    return None, "Поле «{}» слишком длинное.".format(label)
  return value, None


def _positive_number(value, label, optional=False):
  if value is None or (isinstance(value, str) and not value.strip()):
    return (None, None) if optional else (None, "Заполните поле «{}».".format(label))
  if isinstance(value, bool) or not isinstance(value, (int, float, str)):
    return None, "Проверьте числовое поле «{}».".format(label)
  try:
    result = float(str(value).replace(" ", "").replace(",", "."))
  except ValueError:
    return None, "Проверьте числовое поле «{}».".format(label)
  if not math.isfinite(result) or result <= 0 or result > 1000000:
    return None, "Значение поля «{}» должно быть больше нуля.".format(label)
  return result, None


def _parameters(raw, label):
  if raw is None or raw == "":
    return {}, None
  if isinstance(raw, str):
    try:
      if len(raw.encode("utf-8")) > MAX_PARAMETER_BYTES:
        return None, "Параметры «{}» превышают 4 КБ.".format(label)
    except UnicodeEncodeError:
      return None, "Проверьте текст параметров «{}».".format(label)
    try:
      value = json.loads(raw)
    except json.JSONDecodeError:
      return None, "Проверьте JSON параметров «{}».".format(label)
  else:
    value = raw
  if not isinstance(value, dict) or len(value) > MAX_PARAMETER_FIELDS:
    return None, "Параметры «{}» должны быть небольшим JSON-объектом (до 32 полей).".format(label)
  if any(not isinstance(key, str) or not key or len(key) > 64 for key in value):
    return None, "Названия параметров «{}» должны быть коротким текстом.".format(label)
  try:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
  except (TypeError, ValueError, RecursionError):
    return None, "Параметры «{}» должны содержать только данные JSON.".format(label)
  if len(encoded.encode("utf-8")) > MAX_PARAMETER_BYTES:
    return None, "Параметры «{}» превышают 4 КБ.".format(label)
  return value, None


@anvil.server.callable(require_user=True)
def get_projects_page(search_text="", cursor=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": [], "has_more": False}
  if not isinstance(search_text, str) or len(search_text) > 100:
    return {"ok": False, "message": "Поисковый запрос слишком длинный.", "rows": [], "has_more": False}
  filters = {}
  if not Core.has_permission(user, "projects.manage"):
    filters["owner"] = user
  if cursor:
    if not isinstance(cursor, str) or len(cursor) > 100:
      return {"ok": False, "message": "Некорректный курсор проектов.", "rows": [], "has_more": False}
    filters["code"] = q.greater_than(cursor)
  expressions = [
    q.fetch_only("code", "title", "status", "updated_at", "object",
                 object=q.fetch_only("name", "object_type")),
    order_by("code"), q.page_size(PAGE_SIZE + 1)
  ]
  term = search_text.strip()
  if term:
    pattern = "%" + term + "%"
    expressions.append(q.any_of(title=q.ilike(pattern), code=q.ilike(pattern)))
  rows = list(app_tables.projects.search(*expressions, **filters)[:PAGE_SIZE + 1])
  has_more = len(rows) > PAGE_SIZE
  rows = rows[:PAGE_SIZE]
  result = []
  for row in rows:
    obj = row["object"]
    result.append({
      "id": row.get_id(), "code": row["code"], "title": row["title"],
      "status": row["status"],
      "status_title": STATUS_NAMES.get(row["status"], row["status"]),
      "object_name": obj["name"] if obj is not None else "Объект не задан",
      "object_type": OBJECT_NAMES.get(obj["object_type"], "Другой") if obj is not None else "",
      "engineering_profile": (
        (obj["parameters"] or {}).get("engineering_profile", "combined")
        if obj is not None else "combined"
      ),
      "engineering_profile_title": {
        "combined": "Комплексный HVAC",
        "vrv_vrf": "VRV / VRF",
        "ventilation": "Вентиляция",
        "split_multi": "Сплит / мультисплит"
      }.get(
        (obj["parameters"] or {}).get("engineering_profile", "combined")
        if obj is not None else "combined",
        "Комплексный HVAC"
      ),
      "engineering_goal": (
        (obj["parameters"] or {}).get("engineering_goal", "design")
        if obj is not None else "design"
      ),
      "project_priority": (
        (obj["parameters"] or {}).get("project_priority", "standard")
        if obj is not None else "standard"
      )
    })
  return {
    "ok": True, "rows": result, "has_more": has_more,
    "next_cursor": rows[-1]["code"] if has_more else None,
    "object_types": [(title, code) for code, title in OBJECT_TYPES],
    "statuses": [(title, code) for code, title in PROJECT_STATUSES],
    "system_types": [(title, code) for code, title in Constructor.SYSTEM_TYPES]
  }


@anvil.server.callable(require_user=True)
def get_project_workspace(project_id):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный идентификатор проекта."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден."}
  if not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  obj = project["object"]
  rooms = []
  systems = []
  if obj is not None:
    for room in app_tables.rooms.search(
      q.fetch_only("name", "area", "height", "parameters", "sort_order"),
      order_by("sort_order"), object=obj
    )[:100]:
      rooms.append({
        "id": room.get_id(), "project_id": project.get_id(),
        "name": room["name"], "area": room["area"], "height": room["height"],
        "parameters": room["parameters"] or {},
        "area_label": "{} м²".format(room["area"]),
        "height_label": "{} м".format(room["height"])
      })
  for system in app_tables.systems.search(
    q.fetch_only("type", "title", "status", "version"),
    order_by("title"), project=project
  )[:100]:
    system_type_title = dict(Constructor.SYSTEM_TYPES).get(system["type"], system["type"])
    systems.append({
      "id": system.get_id(), "title": system["title"],
      "type_title": system_type_title, "status": system["status"] or "Черновик",
      "version": system["version"] or "1", "project_id": project.get_id()
    })
  return {
    "ok": True,
    "project": {
      "id": project.get_id(), "code": project["code"], "title": project["title"],
      "status": project["status"],
      "object_name": obj["name"] if obj is not None else "",
      "object_type": obj["object_type"] if obj is not None else "other",
      "address": obj["address"] if obj is not None else "",
      "object_parameters": (obj["parameters"] or {}) if obj is not None else {}
    },
    "rooms": rooms,
    "systems": systems,
    "object_types": [(title, code) for code, title in OBJECT_TYPES],
    "statuses": [(title, code) for code, title in PROJECT_STATUSES],
    "system_types": [(title, code) for code, title in Constructor.SYSTEM_TYPES]
  }


@anvil.server.callable(require_user=True)
def save_project(project_data, project_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_data, dict):
    return {"ok": False, "message": "Проверьте данные проекта."}
  title, error = _text(project_data.get("title"), "Название проекта", 120, True)
  if error:
    return {"ok": False, "message": error}
  title = title or ""
  object_name, error = _text(project_data.get("object_name"), "Название объекта", 120, True)
  if error:
    return {"ok": False, "message": error}
  object_name = object_name or ""
  address, error = _text(project_data.get("address"), "Адрес", 300)
  if error:
    return {"ok": False, "message": error}
  address = address or ""
  object_parameters, error = _parameters(
    project_data.get("object_parameters", {}), "объекта"
  )
  if error:
    return {"ok": False, "message": error}
  object_type = project_data.get("object_type")
  if not isinstance(object_type, str) or object_type not in OBJECT_NAMES:
    return {"ok": False, "message": "Выберите тип объекта."}
  status = project_data.get("status") or "draft"
  if not isinstance(status, str) or status not in STATUS_NAMES:
    return {"ok": False, "message": "Выберите статус проекта."}
  if not Core.has_permission(user, "projects.manage") and status not in ("draft", "calculation"):
    return {"ok": False, "message": "Пользователь может перевести проект в черновик или расчёт."}
  if project_id is not None and (not isinstance(project_id, str) or not project_id):
    return {"ok": False, "message": "Некорректный идентификатор проекта."}
  project = app_tables.projects.get_by_id(project_id) if project_id else None
  if project_id and project is None:
    return {"ok": False, "message": "Проект не найден."}
  if project is not None and not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}

  now = datetime.now(timezone.utc)
  obj = project["object"] if project is not None else None
  if obj is None:
    obj = app_tables.objects.add_row(
      name=object_name, object_type=object_type, address=address,
      parameters=object_parameters, created_by=user, created_at=now, updated_at=now
    )
  else:
    obj.update(
      name=object_name, object_type=object_type, address=address,
      parameters=object_parameters, updated_at=now
    )
  is_new = project is None
  if is_new:
    code = "PRJ-" + uuid.uuid4().hex[:12].upper()
    project = app_tables.projects.add_row(
      code=code, title=title, object=obj, status=status,
      version="1", owner=user, created_at=now, updated_at=now
    )
  else:
    project.update(title=title, object=obj, status=status, updated_at=now)
  Core.log_audit(
    actor=user,
    action="project.created" if is_new else "project.updated",
    entity_type="project", entity_id=project.get_id(),
    details={"code": project["code"], "status": status}, created_at=now
  )
  return {"ok": True, "project_id": project.get_id(), "message": "Проект сохранён."}


@anvil.server.callable(require_user=True)
def save_room(project_id, room_data, room_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id or not isinstance(room_data, dict):
    return {"ok": False, "message": "Проверьте данные помещения."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None or project["object"] is None:
    return {"ok": False, "message": "Сначала сохраните объект проекта."}
  if not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  name, error = _text(room_data.get("name"), "Название помещения", 100, True)
  if error:
    return {"ok": False, "message": error}
  name = name or ""
  area, error = _positive_number(room_data.get("area"), "Площадь")
  if error:
    return {"ok": False, "message": error}
  height, error = _positive_number(room_data.get("height"), "Высота")
  if error:
    return {"ok": False, "message": error}
  area = area or 0.0
  height = height or 0.0
  parameters, error = _parameters(room_data.get("parameters", {}), "помещения")
  if error:
    return {"ok": False, "message": error}
  if room_id is not None and (not isinstance(room_id, str) or not room_id):
    return {"ok": False, "message": "Некорректный идентификатор помещения."}
  room = app_tables.rooms.get_by_id(room_id) if room_id else None
  if room_id and (
    room is None or room["object"] is None
    or room["object"].get_id() != project["object"].get_id()
  ):
    return {"ok": False, "message": "Помещение не найдено в этом проекте."}
  now = datetime.now(timezone.utc)
  if room is None:
    room = app_tables.rooms.add_row(
      object=project["object"], name=name, area=area, height=height,
      parameters=parameters, sort_order=now.timestamp(), created_at=now
    )
    action = "project.room_created"
  else:
    room.update(name=name, area=area, height=height, parameters=parameters)
    action = "project.room_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="room", entity_id=room.get_id(),
    details={"project": project["code"]}, created_at=now
  )
  return {"ok": True, "room_id": room.get_id(), "message": "Помещение сохранено."}


@anvil.server.callable(require_user=True)
def delete_room(project_id, room_id):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id or not isinstance(room_id, str) or not room_id:
    return {"ok": False, "message": "Некорректный идентификатор помещения."}
  project = app_tables.projects.get_by_id(project_id)
  room = app_tables.rooms.get_by_id(room_id)
  if project is not None and not Core.can_access_project(project, user):
    return {"ok": False, "message": "Проект недоступен этой учётной записи."}
  if (
    project is None or room is None or project["object"] is None
    or room["object"] is None
    or project["object"].get_id() != room["object"].get_id()
  ):
    return {"ok": False, "message": "Помещение не найдено в этом проекте."}
  room.delete()
  Core.log_audit(
    actor=user, action="project.room_deleted", entity_type="room",
    entity_id=room_id, details={"project": project["code"]},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Помещение удалено."}
