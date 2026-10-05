import anvil.secrets
from datetime import date, datetime, time, timezone
import json
import math
import uuid
from typing import Any

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import EstimateEngine as Estimates


TASK_STATUSES = [
  ("open", "Открыта"), ("in_progress", "В работе"),
  ("done", "Выполнена"), ("cancelled", "Отменена")
]
QUOTE_STATUSES = {
  "draft": "Черновик", "sent": "Отправлено", "approved": "Согласовано",
  "rejected": "Отклонено", "expired": "Истекло", "cancelled": "Отменено"
}
QUOTE_TRANSITIONS = {
  "draft": {"sent", "cancelled"},
  "sent": {"approved", "rejected", "expired", "cancelled"}
}
SERVICE_TYPES = [
  ("installation", "Монтаж"), ("maintenance", "Обслуживание"),
  ("repair", "Ремонт"), ("commissioning", "Пусконаладка"),
  ("measurement", "Измерения"), ("diagnosis", "Диагностика"),
  ("humidification_maintenance", "Сервис увлажнения")
]
SERVICE_STATUSES = [
  ("scheduled", "Запланировано"), ("in_progress", "В работе"),
  ("completed", "Выполнено"), ("cancelled", "Отменено")
]


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


def _amount(value, label, required=True):
  if value is None or (isinstance(value, str) and not value.strip()):
    if required:
      return None, "Заполните поле «{}».".format(label)
    return None, None
  if isinstance(value, bool) or not isinstance(value, (int, float, str)):
    return None, "Проверьте числовое поле «{}».".format(label)
  try:
    result = float(str(value).replace(" ", "").replace(",", "."))
  except (OverflowError, ValueError):
    return None, "Проверьте числовое поле «{}».".format(label)
  if not math.isfinite(result) or result < 0 or result > 1000000000000:
    return None, "Значение поля «{}» вне допустимого диапазона.".format(label)
  return round(result, 2), None


def _date(value, label):
  if value is None or value == "":
    return None, None
  if isinstance(value, datetime):
    return value.date(), None
  if isinstance(value, date):
    return value, None
  if not isinstance(value, str) or len(value) != 10:
    return None, "Укажите дату «{}» в формате ГГГГ-ММ-ДД.".format(label)
  try:
    return date.fromisoformat(value), None
  except ValueError:
    return None, "Укажите дату «{}» в формате ГГГГ-ММ-ДД.".format(label)


def _decode_details(raw, label="Параметры"):
  if isinstance(raw, dict):
    details = raw
  elif isinstance(raw, str) and len(raw) <= 4000:
    try:
      details = json.loads(raw or "{}")
    except json.JSONDecodeError:
      return None, "Проверьте JSON поля «{}».".format(label)
  else:
    return None, "Поле «{}» должно быть небольшим JSON-объектом.".format(label)
  if not isinstance(details, dict) or len(details) > 32:
    return None, "Поле «{}» должно содержать не более 32 параметров.".format(label)
  try:
    encoded = json.dumps(details, ensure_ascii=False, allow_nan=False)
  except (TypeError, ValueError):
    return None, "Проверьте значения поля «{}».".format(label)
  if len(encoded) > 4000:
    return None, "Поле «{}» слишком большое.".format(label)
  return details, None


def _client_label(client):
  if client is None:
    return "Клиент не назначен"
  return client["name"]


def _project_label(project):
  if project is None:
    return "Проект не назначен"
  return "{} · {}".format(project["code"], project["title"])


@anvil.server.callable
def submit_public_enquiry(payload):
  """Store a public contact request in the existing CRM tables."""
  if not isinstance(payload, dict):
    return {"ok": False, "message": "Проверьте данные заявки."}
  fields = (
    ("name", "Имя", 120, True),
    ("company", "Компания", 160, False),
    ("email", "Email", 160, False),
    ("phone", "Телефон", 40, False),
    ("message", "Описание задачи", 1000, True)
  )
  values = {}
  for key, label, maximum, required in fields:
    value, error = _text(payload.get(key), label, maximum, required)
    if error:
      return {"ok": False, "message": error}
    values[key] = value or ""
  values["email"] = values["email"].lower()
  if values["email"] and (
    "@" not in values["email"]
    or "." not in values["email"].rsplit("@", 1)[-1]
  ):
    return {"ok": False, "message": "Проверьте email."}
  if not values["email"] and not values["phone"]:
    return {"ok": False, "message": "Укажите email или телефон для ответа."}

  topics = {
    "equipment": "Подбор оборудования",
    "calculation": "Инженерный расчёт",
    "installation": "Монтаж",
    "service": "Сервис",
    "maintenance": "Сервис · обслуживание",
    "repair": "Сервис · ремонт",
    "commissioning": "Сервис · пусконаладка",
    "measurement": "Сервис · измерения",
    "diagnosis": "Сервис · диагностика",
    "humidification_maintenance": "Сервис · увлажнитель",
    "other": "Другое"
  }
  topic = payload.get("topic")
  if topic not in topics:
    return {"ok": False, "message": "Выберите тему заявки."}
  now = datetime.now(timezone.utc)
  name = values["company"] or values["name"]
  notes = "Заявка с сайта · {}\nКонтакт: {}\n\n{}".format(
    topics[topic], values["name"], values["message"]
  )
  client = app_tables.crm_clients.add_row(
    name=name,
    client_type="organization" if values["company"] else "individual",
    tax_id="",
    email=values["email"],
    phone=values["phone"],
    address="",
    notes=notes,
    created_at=now,
    updated_at=now
  )
  app_tables.crm_contacts.add_row(
    client=client,
    name=values["name"],
    role=topics[topic],
    email=values["email"],
    phone=values["phone"]
  )
  Core.log_audit(
    actor=anvil.users.get_user(),
    action="contact.public_enquiry_created",
    entity_type="crm_client",
    entity_id=str(client.get_id()),
    details={"topic": topic},
    created_at=now
  )
  return {"ok": True, "message": "Заявка сохранена. Администратор свяжется с вами."}


@anvil.server.callable(require_user=True)
def get_operations_options():
  user = _user()
  if not (
    Core.has_permission(user, "operations.manage")
    or Core.has_permission(user, "service.manage")
  ):
    raise anvil.server.PermissionDenied("Недостаточно прав для раздела операций.")
  return {
    "ok": True,
    "task_statuses": TASK_STATUSES,
    "quote_statuses": list(QUOTE_STATUSES.items()),
    "service_types": SERVICE_TYPES,
    "service_statuses": SERVICE_STATUSES
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def get_crm_clients():
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": []}
  rows = app_tables.crm_clients.search(
    q.fetch_only("name", "client_type", "email", "phone", "updated_at"),
    order_by("name")
  )[:100]
  return {
    "ok": True,
    "rows": [{
      "id": row.get_id(), "name": row["name"],
      "client_type": row["client_type"] or "",
      "email": row["email"] or "", "phone": row["phone"] or "",
      "display_type": "Организация" if row["client_type"] == "organization" else "Частный клиент"
    } for row in rows]
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def get_crm_client_details(client_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(client_id, str) or not client_id:
    return {"ok": False, "message": "Некорректный клиент."}
  client = app_tables.crm_clients.get_by_id(client_id)
  if client is None:
    return {"ok": False, "message": "Клиент не найден."}
  contact = next(iter(app_tables.crm_contacts.search(
    q.fetch_only("name", "role", "email", "phone"),
    order_by("name"), client=client
  )), None)
  return {
    "ok": True,
    "client": {
      "id": client.get_id(), "name": client["name"],
      "client_type": client["client_type"] or "organization",
      "tax_id": client["tax_id"] or "", "email": client["email"] or "",
      "phone": client["phone"] or "", "address": client["address"] or "",
      "notes": client["notes"] or "",
      "contact_name": contact["name"] if contact is not None else "",
      "contact_role": contact["role"] if contact is not None else "",
      "contact_email": contact["email"] if contact is not None else "",
      "contact_phone": contact["phone"] if contact is not None else ""
    }
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def save_crm_client(client_data, contact_data, client_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(client_data, dict) or not isinstance(contact_data, dict):
    return {"ok": False, "message": "Проверьте карточку клиента."}
  fields = (
    ("name", "Название клиента", 160, True),
    ("tax_id", "ИНН или регистрационный номер", 32, False),
    ("email", "Электронная почта", 160, False),
    ("phone", "Телефон", 40, False),
    ("address", "Адрес", 300, False),
    ("notes", "Заметки", 1000, False)
  )
  values = {}
  for key, label, maximum, required in fields:
    value, error = _text(client_data.get(key), label, maximum, required)
    if error:
      return {"ok": False, "message": error}
    values[key] = value or ""
  if values["email"] and "@" not in values["email"]:
    return {"ok": False, "message": "Проверьте адрес электронной почты клиента."}
  client_type = client_data.get("client_type")
  if client_type not in ("organization", "individual"):
    return {"ok": False, "message": "Выберите тип клиента."}
  contact_fields = (
    ("name", "Контактное лицо", 120), ("role", "Должность", 80),
    ("email", "Почта контакта", 160), ("phone", "Телефон контакта", 40)
  )
  contact_values = {}
  for key, label, maximum in contact_fields:
    value, error = _text(contact_data.get(key), label, maximum)
    if error:
      return {"ok": False, "message": error}
    contact_values[key] = value or ""
  if contact_values["email"] and "@" not in contact_values["email"]:
    return {"ok": False, "message": "Проверьте адрес почты контактного лица."}
  if client_id is not None and (not isinstance(client_id, str) or not client_id):
    return {"ok": False, "message": "Некорректный клиент."}
  client = app_tables.crm_clients.get_by_id(client_id) if client_id else None
  if client_id and client is None:
    return {"ok": False, "message": "Клиент не найден."}

  now = datetime.now(timezone.utc)
  values.update({
    "client_type": client_type, "assigned_to": user, "updated_at": now
  })
  if client is None:
    values["created_at"] = now
    client = app_tables.crm_clients.add_row(**values)
    action = "crm.client_created"
  else:
    client.update(**values)
    action = "crm.client_updated"
  has_contact = any(contact_values.values())
  if has_contact:
    email = contact_values["email"].lower()
    contact = app_tables.crm_contacts.get(client=client, email=email) if email else None
    if contact is None and not email and contact_values["name"]:
      contact = next((
        row for row in app_tables.crm_contacts.search(client=client)
        if (row["name"] or "").casefold() == contact_values["name"].casefold()
      ), None)
    if contact is None:
      app_tables.crm_contacts.add_row(client=client, **contact_values)
    else:
      contact.update(**contact_values)
  Core.log_audit(
    actor=user, action=action, entity_type="crm_client",
    entity_id=client.get_id(),
    details={"client_type": client_type}, created_at=now
  )
  return {"ok": True, "client_id": client.get_id(), "message": "Карточка клиента сохранена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def assign_project_client(project_id, client_id):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект."}
  if client_id is not None and (not isinstance(client_id, str) or not client_id):
    return {"ok": False, "message": "Некорректный клиент."}
  project = app_tables.projects.get_by_id(project_id)
  client = app_tables.crm_clients.get_by_id(client_id) if client_id else None
  if project is None or (client_id and client is None):
    return {"ok": False, "message": "Проект или клиент не найден."}
  now = datetime.now(timezone.utc)
  project["client"] = client
  project["updated_at"] = now
  Core.log_audit(
    actor=user, action="crm.project_client_assigned", entity_type="project",
    entity_id=project_id,
    details={"client_id": client.get_id() if client is not None else None},
    created_at=now
  )
  return {"ok": True, "message": "Клиент проекта обновлён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def get_crm_tasks():
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": []}
  rows = app_tables.crm_tasks.search(
    q.fetch_only(
      "title", "status", "due_at", "client", "project",
      client=q.fetch_only("name"),
      project=q.fetch_only("code", "title")
    ),
    order_by("due_at", ascending=True)
  )[:100]
  return {
    "ok": True,
    "rows": [{
      "id": row.get_id(), "title": row["title"],
      "status": row["status"] or "open",
      "status_title": dict(TASK_STATUSES).get(row["status"], "Открыта"),
      "due_label": row["due_at"].isoformat() if row["due_at"] else "Срок не задан",
      "client_title": _client_label(row["client"]),
      "project_title": _project_label(row["project"])
    } for row in rows],
    "statuses": TASK_STATUSES
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def save_crm_task(task_data, task_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(task_data, dict):
    return {"ok": False, "message": "Проверьте задачу."}
  title, error = _text(task_data.get("title"), "Название задачи", 160, True)
  if error:
    return {"ok": False, "message": error}
  description, error = _text(task_data.get("description"), "Описание задачи", 1000)
  if error:
    return {"ok": False, "message": error}
  status = task_data.get("status") or "open"
  if not isinstance(status, str) or status not in dict(TASK_STATUSES):
    return {"ok": False, "message": "Выберите состояние задачи."}
  due_at, error = _date(task_data.get("due_at"), "срок выполнения")
  if error:
    return {"ok": False, "message": error}
  client_id = task_data.get("client_id")
  project_id = task_data.get("project_id")
  if client_id is not None and (not isinstance(client_id, str) or not client_id):
    return {"ok": False, "message": "Некорректный клиент задачи."}
  if project_id is not None and (not isinstance(project_id, str) or not project_id):
    return {"ok": False, "message": "Некорректный проект задачи."}
  client = app_tables.crm_clients.get_by_id(client_id) if client_id else None
  project = app_tables.projects.get_by_id(project_id) if project_id else None
  if (client_id and client is None) or (project_id and project is None):
    return {"ok": False, "message": "Клиент или проект задачи не найден."}
  if client is not None and project is not None:
    project_client = project["client"]
    if project_client is not None and project_client.get_id() != client.get_id():
      return {"ok": False, "message": "Выбранный клиент не совпадает с клиентом проекта."}
  if client is None and project is not None:
    client = project["client"]
  if client is None and project is None:
    return {"ok": False, "message": "Свяжите задачу с клиентом или проектом."}
  if task_id is not None and (not isinstance(task_id, str) or not task_id):
    return {"ok": False, "message": "Некорректная задача."}
  row = app_tables.crm_tasks.get_by_id(task_id) if task_id else None
  if task_id and row is None:
    return {"ok": False, "message": "Задача не найдена."}
  now = datetime.now(timezone.utc)
  values = {
    "client": client, "project": project, "title": title or "",
    "description": description or "", "status": status,
    "due_at": due_at, "assigned_to": user, "updated_at": now
  }
  if row is None:
    values["created_at"] = now
    row = app_tables.crm_tasks.add_row(**values)
    action = "crm.task_created"
  else:
    row.update(**values)
    action = "crm.task_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="crm_task",
    entity_id=row.get_id(), details={"status": status}, created_at=now
  )
  return {"ok": True, "task_id": row.get_id(), "message": "Задача сохранена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def update_crm_task_status(task_id, status):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(task_id, str) or not task_id:
    return {"ok": False, "message": "Некорректная задача."}
  if not isinstance(status, str) or status not in dict(TASK_STATUSES):
    return {"ok": False, "message": "Выберите состояние задачи."}
  row = app_tables.crm_tasks.get_by_id(task_id)
  if row is None:
    return {"ok": False, "message": "Задача не найдена."}
  row.update(status=status, updated_at=datetime.now(timezone.utc))
  Core.log_audit(
    actor=user, action="crm.task_status_updated", entity_type="crm_task",
    entity_id=task_id, details={"status": status},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Состояние задачи обновлено."}


def _estimate_line_snapshot(properties):
  snapshot = {}
  product_snapshot = properties.get("product") or {}
  if product_snapshot:
    snapshot["product"] = product_snapshot
  else:
    snapshot.update({
      key: properties[key] for key in (
        "route_type", "unit_price_source", "unit_price_version"
      ) if key in properties
    })
  price = properties.get("price")
  if isinstance(price, dict) and isinstance(price.get("updated_at"), str):
    snapshot["price_updated_at"] = price["updated_at"]
  return snapshot


def _project_bom_rows(project):
  systems = list(app_tables.systems.search(
    q.fetch_only("title"), project=project
  )[:101])
  if len(systems) > 100:
    return None, "Проект содержит больше 100 систем; сформируйте сметы по частям."
  if not systems:
    return [], "В проекте пока нет систем."
  system_match = q.any_of(*[
    q.all_of(system=system) for system in systems
  ])
  rows = list(app_tables.bom.search(
    q.fetch_only("line_key", "description", "quantity", "unit", "properties",
                 "product", "system"),
    system_match
  )[:10001])
  if len(rows) > 10000:
    return None, "Спецификация проекта превышает 10000 строк."
  if not rows:
    return [], "Сначала сформируйте BOM для систем проекта."
  return rows, None


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def build_project_estimate(project_id, labor_cost, consumables_cost):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден."}
  labor, error = _amount(labor_cost, "Стоимость работ")
  if error:
    return {"ok": False, "message": error}
  consumables, error = _amount(consumables_cost, "Расходные материалы")
  if error:
    return {"ok": False, "message": error}
  rows, error = _project_bom_rows(project)
  if error:
    return {"ok": False, "message": error}
  rows = rows or []
  if len(rows) > 600:
    return {"ok": False, "message": "Смета ограничена 600 строками. Разделите расчёт на несколько проектов."}
  currency = Core.get_currency()
  materials_cost = 0.0
  missing = []
  estimate_lines = []
  for row in rows:
    quantity, error = _amount(row["quantity"], "Количество BOM")
    if error:
      return {"ok": False, "message": "{}: {}".format(row["description"], error)}
    properties = row["properties"] or {}
    price_info = properties.get("price", {})
    unit_price = price_info.get("sale_price")
    line_currency = price_info.get("currency")
    if unit_price is None:
      unit_price = properties.get("unit_price")
      line_currency = properties.get("unit_price_currency")
      if not properties.get("unit_price_source") or not properties.get("unit_price_version"):
        unit_price = None
    if unit_price is None or line_currency != currency:
      if len(missing) < 20:
        missing.append(row["description"])
      continue
    unit_price, error = _amount(unit_price, "Цена за единицу")
    if error:
      return {"ok": False, "message": "{}: {}".format(row["description"], error)}
    line_total = round((quantity or 0.0) * (unit_price or 0.0), 2)
    materials_cost += line_total
    if not math.isfinite(materials_cost) or materials_cost > 1000000000000:
      return {"ok": False, "message": "Сумма материалов превышает допустимый предел."}
    line_snapshot = _estimate_line_snapshot(properties)
    estimate_lines.append({
      "line_key": row["line_key"] or "line-{}".format(len(estimate_lines) + 1),
      "product": row["product"],
      "description": row["description"],
      "quantity": quantity or 0.0,
      "unit": row["unit"] or "",
      "unit_price": unit_price or 0.0,
      "currency": line_currency,
      "line_total": line_total,
      "source": row["source"] or "",
      "snapshot": line_snapshot,
      "group": "materials"
    })
  if missing:
    return {
      "ok": False, "message": "Не задана цена в {} для части спецификации.".format(currency),
      "missing": missing
    }
  materials_cost = round(materials_cost, 2)
  priced = {
    "ok": True,
    "lines": estimate_lines,
    "materials_cost": materials_cost,
    "labor_cost": labor or 0.0,
    "currency": currency
  }
  saved = Estimates.save_estimate(
    project,
    user,
    priced,
    {"bom_lines": len(rows), "system_count": len({
      row["system"].get_id() for row in rows if row["system"] is not None
    })},
    consumables or 0.0
  )
  if saved["ok"]:
    saved["message"] = "Смета рассчитана и сохранена."
  return saved


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def get_project_estimate(project_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден."}
  estimate = next(iter(app_tables.estimates.search(
    q.fetch_only("version", "currency", "materials_cost", "labor_cost",
                 "consumables_cost", "total", "updated_at"),
    order_by("updated_at", ascending=False), project=project
  )), None)
  if estimate is None:
    return {"ok": True, "estimate": None}
  return {
    "ok": True,
    "estimate": {
      "id": estimate.get_id(), "version": estimate["version"],
      "currency": estimate["currency"], "materials_cost": estimate["materials_cost"],
      "labor_cost": estimate["labor_cost"], "consumables_cost": estimate["consumables_cost"],
      "total": estimate["total"], "updated_at": estimate["updated_at"]
    }
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def create_project_quote(project_id, terms, expires_at=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект."}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден."}
  terms, error = _text(terms, "Условия предложения", 2000, required=False)
  if error:
    return {"ok": False, "message": error}
  expires, error = _date(expires_at, "срок действия")
  if error:
    return {"ok": False, "message": error}
  if expires is not None and expires < date.today():
    return {"ok": False, "message": "Срок действия предложения не может быть в прошлом."}
  estimate = next(iter(app_tables.estimates.search(
    q.fetch_only("version", "total", "currency"),
    order_by("updated_at", ascending=False), project=project
  )), None)
  if estimate is None:
    return {"ok": False, "message": "Сначала сформируйте смету по проекту."}
  now = datetime.now(timezone.utc)
  number = "HV-" + now.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
  quote = app_tables.quotes.add_row(
    project=project, client=project["client"], estimate=estimate,
    number=number, status="draft", terms=terms or "",
    total=estimate["total"], currency=estimate["currency"],
    estimate_version=estimate["version"], created_at=now, updated_at=now
  )
  if expires is not None:
    quote["expires_at"] = expires
  project.update(status="quoted", updated_at=now)
  Core.log_audit(
    actor=user, action="quote.created", entity_type="quote",
    entity_id=quote.get_id(),
    details={"number": number, "total": quote["total"], "currency": quote["currency"]},
    created_at=now
  )
  return {"ok": True, "quote_id": quote.get_id(), "number": number, "message": "Предложение создано."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def get_project_quotes(project_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": []}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект.", "rows": []}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден.", "rows": []}
  rows = app_tables.quotes.search(
    q.fetch_only("number", "status", "expires_at", "total", "currency",
                 "estimate_version", "created_at"),
    order_by("created_at", ascending=False), project=project
  )[:100]
  return {
    "ok": True,
    "rows": [{
      "id": row.get_id(), "number": row["number"],
      "status": row["status"],
      "status_title": QUOTE_STATUSES.get(row["status"], row["status"]),
      "total": row["total"], "total_label": "{} {}".format(row["total"], row["currency"]),
      "estimate_version": row["estimate_version"],
      "expires_label": row["expires_at"].isoformat() if row["expires_at"] else "Без срока"
    } for row in rows]
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("operations.manage")
def update_quote_status(quote_id, status):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(quote_id, str) or not quote_id:
    return {"ok": False, "message": "Некорректное предложение."}
  if not isinstance(status, str) or status not in QUOTE_STATUSES:
    return {"ok": False, "message": "Выберите допустимый статус предложения."}
  quote = app_tables.quotes.get_by_id(quote_id)
  if quote is None:
    return {"ok": False, "message": "Предложение не найдено."}
  current_status = quote["status"]
  if status not in QUOTE_TRANSITIONS.get(current_status, set()):
    return {"ok": False, "message": "Этот переход статуса предложения недоступен."}
  now = datetime.now(timezone.utc)
  quote.update(status=status, updated_at=now)
  if status == "approved":
    quote["project"]["status"] = "approved"
  Core.log_audit(
    actor=user, action="quote.status_updated", entity_type="quote",
    entity_id=quote_id, details={"status": status}, created_at=now
  )
  return {"ok": True, "message": "Статус предложения обновлён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("service.manage")
def get_service_records(project_id):
  if _user() is None:
    return {"ok": False, "message": "Войдите в систему.", "rows": []}
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Некорректный проект.", "rows": []}
  project = app_tables.projects.get_by_id(project_id)
  if project is None:
    return {"ok": False, "message": "Проект не найден.", "rows": []}
  rows = app_tables.service.search(
    q.fetch_only(
      "system", "product", "serial", "service_type", "status", "details",
      "scheduled_at", "completed_at",
      system=q.fetch_only("title"), product=q.fetch_only("model", "brand", brand=q.fetch_only("name"))
    ),
    order_by("created_at", ascending=False), project=project
  )[:100]
  return {
    "ok": True,
    "rows": [{
      "id": row.get_id(), "serial": row["serial"] or "Серийный номер не указан",
      "equipment": _product_label(row["product"]),
      "service_type": row["service_type"],
      "service_type_title": dict(SERVICE_TYPES).get(row["service_type"], "Вид работ не указан"),
      "status": row["status"],
      "status_title": dict(SERVICE_STATUSES).get(row["status"], "Состояние не указано"),
      "details_label": json.dumps(row["details"] or {}, ensure_ascii=False, sort_keys=True),
      "scheduled_label": row["scheduled_at"].strftime("%Y-%m-%d") if row["scheduled_at"] else "Без даты",
      "completed_label": row["completed_at"].strftime("%Y-%m-%d") if row["completed_at"] else ""
    } for row in rows]
  }


def _product_label(product):
  if product is None:
    return "Оборудование не привязано"
  brand = product["brand"]
  return "{} {}".format(
    brand["name"] if brand is not None else "", product["model"] or ""
  ).strip()


@anvil.server.callable(require_user=True)
@Core.permission_guard("service.manage")
def save_service_record(service_data, record_id=None):
  user = _user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(service_data, dict):
    return {"ok": False, "message": "Проверьте сервисную запись."}
  project_id = service_data.get("project_id")
  system_id = service_data.get("system_id")
  product_id = service_data.get("product_id")
  if not isinstance(project_id, str) or not project_id:
    return {"ok": False, "message": "Выберите проект обслуживания."}
  project = app_tables.projects.get_by_id(project_id)
  system = app_tables.systems.get_by_id(system_id) if isinstance(system_id, str) and system_id else None
  product = app_tables.products.get_by_id(product_id) if isinstance(product_id, str) and product_id else None
  if project is None:
    return {"ok": False, "message": "Проект не найден."}
  if system_id and (
    system is None or system["project"].get_id() != project.get_id()
  ):
    return {"ok": False, "message": "Система не принадлежит выбранному проекту."}
  if product_id and product is None:
    return {"ok": False, "message": "Товар оборудования не найден."}
  if system is None and product is None:
    return {"ok": False, "message": "Выберите систему или реальное оборудование."}
  serial, error = _text(service_data.get("serial"), "Серийный номер", 120)
  if error:
    return {"ok": False, "message": error}
  service_type = service_data.get("service_type")
  if not isinstance(service_type, str) or service_type not in dict(SERVICE_TYPES):
    return {"ok": False, "message": "Выберите вид сервисной работы."}
  status = service_data.get("status") or "scheduled"
  if not isinstance(status, str) or status not in dict(SERVICE_STATUSES):
    return {"ok": False, "message": "Выберите состояние сервисной записи."}
  details, error = _decode_details(service_data.get("details", "{}"), "Сервисные параметры")
  if error:
    return {"ok": False, "message": error}
  scheduled, error = _date(service_data.get("scheduled_at"), "плановая дата")
  if error:
    return {"ok": False, "message": error}
  completed, error = _date(service_data.get("completed_at"), "дата выполнения")
  if error:
    return {"ok": False, "message": error}
  if record_id is not None and (not isinstance(record_id, str) or not record_id):
    return {"ok": False, "message": "Некорректная сервисная запись."}
  row = app_tables.service.get_by_id(record_id) if record_id else None
  if record_id and (row is None or row["project"].get_id() != project.get_id()):
    return {"ok": False, "message": "Сервисная запись не найдена в этом проекте."}
  now = datetime.now(timezone.utc)
  scheduled_at = datetime.combine(scheduled, time.min, tzinfo=timezone.utc) if scheduled else None
  completed_at = datetime.combine(completed, time.min, tzinfo=timezone.utc) if completed else None
  values = {
    "project": project, "system": system, "product": product,
    "serial": serial or "", "service_type": service_type,
    "status": status, "details": details,
    "scheduled_at": scheduled_at, "completed_at": completed_at,
    "assigned_to": user
  }
  if row is None:
    values["created_at"] = now
    row = app_tables.service.add_row(**values)
    action = "service.record_created"
  else:
    row.update(**values)
    action = "service.record_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="service",
    entity_id=row.get_id(),
    details={"type": service_type, "status": status}, created_at=now
  )
  return {"ok": True, "record_id": row.get_id(), "message": "Сервисная запись сохранена."}
