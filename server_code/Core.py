import anvil.secrets
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q


DEFAULT_SETTINGS = {
  "organization_name": "ЭКО-КЛИМАТ",
  "currency": "RUB",
  "contact_email": "",
  "contact_phone": "+79257873848",
  "contact_address": "",
  "site_theme": "blue"
}
SITE_THEME_CODES = frozenset((
  "blue", "graphite", "ice", "amber", "crimson", "violet"
))
AUDIT_LOG_LIMIT = 1000
AUDIT_LOG_PRUNE_BATCH = 100
AUDIT_LOG_PRUNE_KEY = "audit_logs_pruned_at"
AUDIT_LOG_PRUNE_INTERVAL = timedelta(hours=1)
LOCAL_ADMIN_EMAIL = "admin@local.invalid"
MODERATOR_PERMISSIONS = (
  "dashboard.view", "catalog.manage", "cms.manage", "import.manage",
  "projects.manage", "calculations.manage", "installation.manage",
  "engineering.manage", "operations.manage", "service.manage"
)
EDITABLE_PERMISSIONS = frozenset(MODERATOR_PERMISSIONS)


def _prune_audit_logs(now, actor=None):
  settings = app_tables.system_settings
  marker = settings.get(key=AUDIT_LOG_PRUNE_KEY)
  last_pruned = marker["value"] if marker is not None else None
  if isinstance(last_pruned, datetime):
    if last_pruned.tzinfo is None:
      last_pruned = last_pruned.replace(tzinfo=timezone.utc)
    if now - last_pruned < AUDIT_LOG_PRUNE_INTERVAL:
      return
  elif isinstance(last_pruned, (int, float)) and not isinstance(last_pruned, bool):
    if now.timestamp() - last_pruned < AUDIT_LOG_PRUNE_INTERVAL.total_seconds():
      return

  pruned_at = now.timestamp()

  audit_table = app_tables.audit_logs
  rows = list(audit_table.search(
    order_by("created_at")
  )[:AUDIT_LOG_LIMIT + AUDIT_LOG_PRUNE_BATCH + 1])
  if len(rows) > AUDIT_LOG_LIMIT:
    excess = min(len(rows) - AUDIT_LOG_LIMIT, AUDIT_LOG_PRUNE_BATCH)
    for old_row in rows[:excess]:
      old_row.delete()

  if marker is None:
    if actor is None:
      settings.add_row(key=AUDIT_LOG_PRUNE_KEY, value=pruned_at, updated_at=now)
    else:
      settings.add_row(
        key=AUDIT_LOG_PRUNE_KEY, value=pruned_at, updated_at=now, updated_by=actor
      )
  else:
    if actor is None:
      marker.update(value=pruned_at, updated_at=now)
    else:
      marker.update(value=pruned_at, updated_at=now, updated_by=actor)


def log_audit(**values):
  now = values.get("created_at") or datetime.now(timezone.utc)
  values.setdefault("created_at", now)
  audit_table = app_tables.audit_logs
  row = audit_table.add_row(**values)
  _prune_audit_logs(now, values.get("actor"))
  return row


def _role_by_code(code):
  normalized = code.casefold()
  return next((
    role for role in app_tables.roles.search()
    if isinstance(role["code"], str) and role["code"].casefold() == normalized
  ), None)


def _ensure_roles():
  admin_role = _role_by_code("admin")
  if admin_role is None:
    admin_role = app_tables.roles.add_row(
      code="admin", title="Администратор", permissions=["*"]
    )

  user_role = _role_by_code("user")
  if user_role is None:
    user_role = app_tables.roles.add_row(
      code="user", title="Пользователь", permissions=[]
    )
  moderator_role = _role_by_code("moderator")
  if moderator_role is None:
    moderator_role = app_tables.roles.add_row(
      code="moderator", title="Модератор",
      permissions=list(MODERATOR_PERMISSIONS)
    )
  return admin_role, user_role, moderator_role


@anvil.server.callable
def register_site_user(email, password):
  """Create a confirmed USER account; the client cannot choose its role."""
  if not isinstance(email, str):
    return {"ok": False, "message": "Введите корректный email."}
  email = email.strip().lower()
  if len(email) > 160 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
    return {"ok": False, "message": "Введите корректный email."}
  if email == LOCAL_ADMIN_EMAIL:
    return {"ok": False, "message": "Этот email зарезервирован для локального администратора."}
  if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
    return {"ok": False, "message": "Пароль должен содержать от 8 до 128 символов."}

  _, user_role, _ = _ensure_roles()
  try:
    anvil.users.signup_with_email(email, password, remember=False)
  except anvil.users.UserExists:
    return {"ok": False, "message": "Учётная запись с таким email уже существует."}
  except anvil.users.PasswordNotAcceptable:
    return {"ok": False, "message": "Выберите пароль, который принимает сервис пользователей Anvil."}
  user = app_tables.users.get(email=email)
  if user is None:
    raise RuntimeError("The registered user account was not persisted.")
  user.update(role=user_role, enabled=True, confirmed_email=True)
  log_audit(
    actor=user,
    action="auth.user_registered",
    entity_type="user",
    entity_id=str(user.get_id()),
    details={"role": "user"},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Профиль создан."}


def _ensure_core_data(user):
  if user["role"] is not None:
    return

  _, user_role, _ = _ensure_roles()

  for key, value in DEFAULT_SETTINGS.items():
    if app_tables.system_settings.get(key=key) is None:
      app_tables.system_settings.add_row(
        key=key, value=value, updated_at=datetime.now(timezone.utc)
      )

  user["role"] = user_role


def _is_admin(user):
  if user is None:
    return False
  role = user["role"]
  code = role["code"] if role is not None else None
  return isinstance(code, str) and code.casefold() == "admin"


def _permissions_for(user):
  if user is None:
    return set()
  if _is_admin(user):
    return {"*"}
  role = user["role"]
  role_permissions = role["permissions"] if role is not None else []
  user_permissions = user["permissions"] or []
  if not isinstance(role_permissions, (list, tuple, set)):
    role_permissions = []
  if not isinstance(user_permissions, (list, tuple, set)):
    user_permissions = []
  return {
    permission for permission in list(role_permissions or []) + list(user_permissions)
    if isinstance(permission, str)
  }


def has_permission(user, permission):
  if _is_admin(user):
    return True
  permissions = _permissions_for(user)
  return permission in permissions or "*" in permissions


def get_admin_user():
  user = anvil.users.get_user()
  return user if _is_admin(user) else None


def require_admin_user():
  user = anvil.users.get_user()
  if not _is_admin(user):
    raise anvil.server.PermissionDenied("Доступ разрешён только администратору.")
  return user


def require_staff_user():
  user = anvil.users.get_user()
  role = user["role"] if user is not None else None
  raw_role_code = role["code"] if role is not None else "user"
  role_code = raw_role_code.casefold() if isinstance(raw_role_code, str) else "user"
  if role_code == "admin":
    return user
  if role_code == "moderator" and has_permission(user, "dashboard.view"):
    return user
  raise anvil.server.PermissionDenied("Админ-панель доступна только ADMIN и MODERATOR.")


def require_permission(permission):
  user = anvil.users.get_user()
  if not has_permission(user, permission):
    raise anvil.server.PermissionDenied(
      "Недостаточно прав для действия «{}».".format(permission)
    )
  return user


def can_access_project(project, user=None):
  """Allow project editors all projects and users only their own rows."""
  user = user if user is not None else anvil.users.get_user()
  if user is None or project is None:
    return False
  if has_permission(user, "projects.manage"):
    return True
  owner = project["owner"]
  return owner is not None and owner.get_id() == user.get_id()


def admin_guard(function):
  """Apply the shared ADMIN role check before server callable logic runs."""
  @wraps(function)
  def guarded(*args, **kwargs):
    require_admin_user()
    return function(*args, **kwargs)
  return guarded


def staff_guard(function):
  """Require an ADMIN or permitted MODERATOR role for the admin workspace."""
  @wraps(function)
  def guarded(*args, **kwargs):
    require_staff_user()
    return function(*args, **kwargs)
  return guarded


def permission_guard(permission):
  """Apply a server-side working-data permission before callable logic."""
  def decorate(function):
    @wraps(function)
    def guarded(*args, **kwargs):
      require_permission(permission)
      return function(*args, **kwargs)
    return guarded
  return decorate


def _setting_value(key):
  row = app_tables.system_settings.get(key=key)
  if row is None:
    return DEFAULT_SETTINGS[key]
  value = row["value"]
  if key == "contact_phone" and value == "+79257873847":
    value = DEFAULT_SETTINGS[key]
    row.update(value=value, updated_at=datetime.now(timezone.utc))
  return value


def _current_site_theme():
  value = _setting_value("site_theme")
  if isinstance(value, str) and value in SITE_THEME_CODES:
    return value
  return DEFAULT_SETTINGS["site_theme"]


def get_currency():
  return _setting_value("currency")


@anvil.server.callable
def get_session_context():
  user = anvil.users.get_user()
  if user is None:
    return {
      "email": "",
      "role_code": "user",
      "role_title": "Пользователь",
      "permissions": []
    }

  role = user["role"]
  raw_role_code = role["code"] if role is not None else "user"
  role_code = raw_role_code.casefold() if isinstance(raw_role_code, str) else "user"
  return {
    "email": user["email"],
    "role_code": role_code,
    "role_title": role["title"] if role is not None else "Пользователь",
    "permissions": sorted(_permissions_for(user))
  }


@anvil.server.callable
def get_public_contact_details():
  import AdminStudio

  message_limit = AdminStudio.get_admin_studio_setting("forms.message_limit", 1200)
  if (isinstance(message_limit, bool)
      or not isinstance(message_limit, (int, float))
      or message_limit < 100 or message_limit > 5000):
    message_limit = 1200
  return {
    "organization_name": _setting_value("organization_name") or "ЭКО-КЛИМАТ",
    "contact_email": _setting_value("contact_email"),
    "contact_phone": _setting_value("contact_phone") or "+79257873848",
    "contact_address": _setting_value("contact_address"),
    "form": {
      "email_required": AdminStudio.get_admin_studio_setting("forms.contact_email", True) is not False,
      "phone_required": AdminStudio.get_admin_studio_setting("forms.contact_phone", True) is not False,
      "message_enabled": AdminStudio.get_admin_studio_setting("forms.lead_comment", True) is not False,
      "message_limit": int(message_limit),
      "trim_input": AdminStudio.get_admin_studio_setting("forms.trim_input", True) is not False,
      "error_message": AdminStudio.get_admin_studio_setting(
        "forms.error_message", "Проверьте заполнение полей."
      )
    }
  }


@anvil.server.callable
def get_current_site_theme():
  return _current_site_theme()

@anvil.server.callable
def get_public_shell_data():
  """Return the data required for the first public render in one server round-trip."""
  import AdminStudio
  import CatalogService
  import SiteMenuService

  catalog = CatalogService.get_catalog_menu_tree(include_counts=False)
  return {
    "ok": True,
    "site_theme": _current_site_theme(),
    "session_context": get_session_context(),
    "catalog": catalog,
    "extensions": AdminStudio.get_public_site_extensions()
  }


@anvil.server.callable(require_user=True)
@admin_guard
def get_admin_users_page(search_text="", cursor=None):
  _ensure_roles()
  if not isinstance(search_text, str) or len(search_text) > 160:
    return {"ok": False, "message": "Проверьте поисковый email.", "rows": [], "has_more": False}
  filters = {}
  if cursor:
    if not isinstance(cursor, str) or len(cursor) > 160:
      return {"ok": False, "message": "Некорректный курсор списка.", "rows": [], "has_more": False}
    filters["email"] = q.greater_than(cursor)
  expressions = [
    q.fetch_only(
      "email", "enabled", "confirmed_email", "role", "permissions",
      "last_login", "n_password_failures",
      role=q.fetch_only("code", "title")
    ),
    order_by("email"), q.page_size(41)
  ]
  term = search_text.strip()
  if term:
    expressions.append(q.any_of(email=q.ilike("%{}%".format(term))))
  rows = list(app_tables.users.search(*expressions, **filters)[:41])
  has_more = len(rows) > 40
  rows = rows[:40]
  return {
    "ok": True,
    "rows": [{
      "id": row.get_id(),
      "email": row["email"],
      "role_code": row["role"]["code"] if row["role"] is not None else "user",
      "role_title": row["role"]["title"] if row["role"] is not None else "Пользователь",
      "enabled": bool(row["enabled"]),
      "confirmed_email": bool(row["confirmed_email"]),
      "permissions": list(row["permissions"] or []),
      "last_login": row["last_login"].isoformat() if row["last_login"] else "",
      "n_password_failures": row["n_password_failures"] or 0
    } for row in rows],
    "roles": [
      (row["title"], row["code"])
      for row in sorted(
        app_tables.roles.search(),
        key=lambda item: (
          {"admin": 0, "moderator": 1, "user": 2}.get(
            (item["code"] or "").casefold(), 3
          ),
          (item["title"] or "").casefold()
        )
      )
    ],
    "has_more": has_more,
    "next_cursor": rows[-1]["email"] if has_more else None
  }


def _role_permission_values(raw):
  if raw is None:
    raw = []
  if not isinstance(raw, list) or len(raw) > len(EDITABLE_PERMISSIONS):
    return None, "Проверьте список разрешений роли."
  if any(not isinstance(item, str) for item in raw):
    return None, "Проверьте список разрешений роли."
  permissions = sorted(set(item.strip() for item in raw if item.strip()))
  if any(item not in EDITABLE_PERMISSIONS for item in permissions):
    return None, "Роль может содержать только известные права рабочего пространства."
  return permissions, None


@anvil.server.callable(require_user=True)
@admin_guard
def get_managed_roles():
  _ensure_roles()
  users = app_tables.users
  role_rows = list(app_tables.roles.search())
  role_rows.sort(key=lambda row: (
    {"admin": 0, "moderator": 1, "user": 2}.get(
      (row["code"] or "").casefold(), 3
    ),
    (row["title"] or "").casefold()
  ))
  return {
    "ok": True,
    "permissions": sorted(EDITABLE_PERMISSIONS),
    "roles": [{
      "id": row.get_id(),
      "code": row["code"] or "",
      "title": row["title"] or "",
      "permissions": list(row["permissions"] or []),
      "built_in": (row["code"] or "").casefold() in (
        "admin", "moderator", "user"
      ),
      "protected": (row["code"] or "").casefold() == "admin",
      "assigned_users": len(list(users.search(role=row)[:1001]))
    } for row in role_rows]
  }


@anvil.server.callable(require_user=True)
@admin_guard
def save_managed_role(role_id=None, code="", title="", permissions=None):
  actor = anvil.users.get_user()
  if not isinstance(title, str):
    return {"ok": False, "message": "Введите название роли."}
  title = title.strip()
  if not title or len(title) > 80:
    return {"ok": False, "message": "Название роли должно содержать от 1 до 80 символов."}
  if not isinstance(code, str):
    return {"ok": False, "message": "Введите короткий код роли."}
  code = code.strip().casefold()
  if (
    not 2 <= len(code) <= 32
    or not code[0].isascii()
    or not code[0].isalpha()
    or not code.isascii()
    or any(not (character.isalnum() or character == "_") for character in code)
  ):
    return {"ok": False, "message": "Код роли: латинская буква, затем латинские буквы, цифры или _."}
  clean_permissions, error = _role_permission_values(permissions)
  if error:
    return {"ok": False, "message": error}
  if role_id is not None and (not isinstance(role_id, str) or not role_id):
    return {"ok": False, "message": "Некорректная роль."}
  role = app_tables.roles.get_by_id(role_id) if role_id else None
  if role_id and role is None:
    return {"ok": False, "message": "Роль больше не существует."}
  current_code = (role["code"] or "").casefold() if role is not None else ""
  if current_code == "admin":
    return {"ok": False, "message": "Системную роль ADMIN изменить нельзя."}
  if current_code in ("user", "moderator") and code != current_code:
    return {"ok": False, "message": "Код встроенной роли изменить нельзя."}
  if code == "admin":
    return {"ok": False, "message": "Код admin зарезервирован системной ролью."}
  duplicate = _role_by_code(code)
  if duplicate is not None and (
    role is None or duplicate.get_id() != role.get_id()
  ):
    return {"ok": False, "message": "Такой код роли уже используется."}
  now = datetime.now(timezone.utc)
  if role is None:
    role = app_tables.roles.add_row(
      code=code, title=title, permissions=clean_permissions
    )
    action = "auth.role_created"
  else:
    role.update(code=code, title=title, permissions=clean_permissions)
    action = "auth.role_updated"
  log_audit(
    actor=actor, action=action, entity_type="role",
    entity_id=str(role.get_id()),
    details={"code": code, "title": title, "permissions": clean_permissions},
    created_at=now
  )
  return {"ok": True, "role_id": role.get_id(), "message": "Роль сохранена."}


@anvil.server.callable(require_user=True)
@admin_guard
def delete_managed_role(role_id):
  actor = anvil.users.get_user()
  if not isinstance(role_id, str) or not role_id:
    return {"ok": False, "message": "Выберите роль."}
  role = app_tables.roles.get_by_id(role_id)
  if role is None:
    return {"ok": False, "message": "Роль не найдена."}
  code = (role["code"] or "").casefold()
  if code in ("admin", "moderator", "user"):
    return {"ok": False, "message": "Встроенную роль удалить нельзя."}
  assigned = list(app_tables.users.search(role=role)[:1])
  if assigned:
    return {
      "ok": False,
      "message": "Сначала назначьте пользователям другую роль, затем удалите эту."
    }
  details = {"code": role["code"] or "", "title": role["title"] or ""}
  role.delete()
  log_audit(
    actor=actor, action="auth.role_deleted", entity_type="role",
    entity_id=role_id, details=details, created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Роль удалена."}


@anvil.server.callable(require_user=True)
@admin_guard
def set_user_access(user_id, role_code, enabled):
  actor = anvil.users.get_user()
  if actor is None:
    raise anvil.server.PermissionDenied("Войдите как администратор.")
  if not isinstance(user_id, str) or not user_id:
    return {"ok": False, "message": "Некорректная учётная запись."}
  if not isinstance(role_code, str) or not role_code.strip():
    return {"ok": False, "message": "Выберите роль."}
  if not isinstance(enabled, bool):
    return {"ok": False, "message": "Некорректное состояние учётной записи."}
  target = app_tables.users.get_by_id(user_id)
  if target is None:
    return {"ok": False, "message": "Учётная запись не найдена."}
  role_code = role_code.casefold()
  if target.get_id() == actor.get_id() and (
    role_code != "admin" or not enabled
  ):
    return {"ok": False, "message": "Нельзя отключить или лишить роли текущую учётную запись."}
  admin_role = _role_by_code("admin")
  target_is_admin = target["role"] is not None and _is_admin(target)
  if target_is_admin and (role_code != "admin" or not enabled):
    active_admins = [
      row for row in app_tables.users.search(role=admin_role)
      if row["enabled"]
    ]
    if len(active_admins) <= 1:
      return {"ok": False, "message": "В системе должен остаться хотя бы один активный ADMIN."}
  _ensure_roles()
  role = _role_by_code(role_code.casefold())
  if role is None:
    return {"ok": False, "message": "Выбранная роль больше не существует."}
  target.update(role=role, enabled=enabled)
  now = datetime.now(timezone.utc)
  log_audit(
    actor=actor,
    action="auth.user_access_updated",
    entity_type="user",
    entity_id=str(target.get_id()),
    details={"role": role_code, "enabled": enabled},
    created_at=now
  )
  return {"ok": True, "message": "Роль и состояние учётной записи сохранены."}


def _validated_user_permissions(raw, role_code):
  if raw is None:
    raw = []
  if not isinstance(raw, list) or len(raw) > len(EDITABLE_PERMISSIONS):
    return None, "Проверьте список дополнительных прав."
  if any(not isinstance(item, str) for item in raw):
    return None, "Проверьте список дополнительных прав."
  permissions = sorted(set(raw))
  if any(item not in EDITABLE_PERMISSIONS for item in permissions):
    return None, "Нельзя назначить системное или неизвестное право."
  if role_code == "admin" and permissions:
    return None, "Для ADMIN дополнительные права задавать не нужно."
  return permissions, None


@anvil.server.callable(require_user=True)
@admin_guard
def create_managed_user(email, password="", role_code="user", permissions=None):
  actor = anvil.users.get_user()
  if actor is None:
    raise anvil.server.PermissionDenied("Войдите как администратор.")
  if not isinstance(email, str):
    return {"ok": False, "message": "Введите корректный email."}
  email = email.strip().lower()
  if len(email) > 160 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
    return {"ok": False, "message": "Введите корректный email."}
  if not isinstance(role_code, str) or not role_code.strip():
    return {"ok": False, "message": "Выберите роль."}
  role_code = role_code.casefold()
  if not isinstance(password, str) or (password and not 8 <= len(password) <= 128):
    return {"ok": False, "message": "Пароль должен содержать от 8 до 128 символов."}
  password = password or secrets.token_urlsafe(18)
  permissions, error = _validated_user_permissions(permissions, role_code)
  if error:
    return {"ok": False, "message": error}
  _ensure_roles()
  role = _role_by_code(role_code)
  if role is None:
    return {"ok": False, "message": "Выбранная роль больше не существует."}
  try:
    anvil.users.signup_with_email(email, password, remember=False)
  except anvil.users.UserExists:
    return {"ok": False, "message": "Пользователь с таким email уже существует."}
  except anvil.users.PasswordNotAcceptable:
    return {"ok": False, "message": "Пароль не прошёл проверку сервиса Users."}
  finally:
    if actor is not None:
      anvil.users.force_login(actor, remember=False)
  user = app_tables.users.get(email=email)
  if user is None:
    raise RuntimeError("Created Users account was not persisted.")
  user.update(
    role=role, enabled=True, confirmed_email=True, permissions=permissions,
    n_password_failures=0, remembered_logins=[]
  )
  now = datetime.now(timezone.utc)
  log_audit(
    actor=actor, action="auth.managed_user_created", entity_type="user",
    entity_id=str(user.get_id()),
    details={"email": email, "role": role_code}, created_at=now
  )
  return {
    "ok": True, "user_id": user.get_id(), "email": email,
    "role_code": role_code, "password": password,
    "message": "Пользователь создан и активирован без подтверждения email."
  }


@anvil.server.callable(require_user=True)
@admin_guard
def update_managed_user(user_id, role_code, enabled, permissions=None):
  actor = anvil.users.get_user()
  if actor is None:
    raise anvil.server.PermissionDenied("Войдите как администратор.")
  if not isinstance(user_id, str) or not user_id:
    return {"ok": False, "message": "Некорректная учётная запись."}
  if not isinstance(role_code, str) or not role_code.strip():
    return {"ok": False, "message": "Выберите роль USER, MODERATOR или ADMIN."}
  if not isinstance(enabled, bool):
    return {"ok": False, "message": "Некорректное состояние учётной записи."}
  role_code = role_code.casefold()
  target = app_tables.users.get_by_id(user_id)
  if target is None:
    return {"ok": False, "message": "Учётная запись не найдена."}
  current_role = target["role"]
  current_role_code = (
    current_role["code"].casefold() if current_role is not None else "user"
  )
  _ensure_roles()
  if _role_by_code(role_code) is None:
    return {"ok": False, "message": "Выбранная роль больше не существует."}
  permissions, error = _validated_user_permissions(permissions, role_code)
  if error:
    return {"ok": False, "message": error}
  if target.get_id() == actor.get_id() and (role_code != "admin" or not enabled):
    return {"ok": False, "message": "Нельзя отключить или понизить текущую ADMIN-учётную запись."}
  if _is_admin(target) and (role_code != "admin" or not enabled):
    active_admins = [
      row for row in app_tables.users.search(role=_role_by_code("admin"))
      if row["enabled"]
    ]
    if len(active_admins) <= 1:
      return {"ok": False, "message": "В системе должен остаться хотя бы один активный ADMIN."}
  role = _role_by_code(role_code)
  if role is None:
    raise RuntimeError("Required role is missing from the roles table.")
  target.update(
    role=role, enabled=enabled, permissions=permissions,
    remembered_logins=[], n_password_failures=0
  )
  now = datetime.now(timezone.utc)
  log_audit(
    actor=actor, action="auth.managed_user_updated", entity_type="user",
    entity_id=str(target.get_id()),
    details={"email": target["email"], "role": role_code,
             "enabled": enabled, "permissions": permissions},
    created_at=now
  )
  return {"ok": True, "message": "Профиль и права пользователя сохранены."}


@anvil.server.callable(require_user=True)
@admin_guard
def reset_managed_user_access(user_id):
  actor = anvil.users.get_user()
  if actor is None:
    raise anvil.server.PermissionDenied("Войдите как администратор.")
  if not isinstance(user_id, str) or not user_id:
    return {"ok": False, "message": "Некорректная учётная запись."}
  target = app_tables.users.get_by_id(user_id)
  if target is None:
    return {"ok": False, "message": "Учётная запись не найдена."}
  target.update(
    enabled=True, confirmed_email=True, n_password_failures=0,
    remembered_logins=[]
  )
  anvil.users.send_password_reset_email(target["email"])
  log_audit(
    actor=actor, action="auth.managed_user_access_reset", entity_type="user",
    entity_id=str(target.get_id()), details={"email": target["email"]},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Доступ разблокирован; отправлена ссылка для сброса пароля."}


@anvil.server.callable(require_user=True)
@admin_guard
def delete_managed_user(user_id):
  actor = anvil.users.get_user()
  if actor is None:
    raise anvil.server.PermissionDenied("Войдите как администратор.")
  if not isinstance(user_id, str) or not user_id:
    return {"ok": False, "message": "Некорректная учётная запись."}
  target = app_tables.users.get_by_id(user_id)
  if target is None:
    return {"ok": False, "message": "Учётная запись не найдена."}
  if target.get_id() == actor.get_id():
    return {"ok": False, "message": "Нельзя удалить текущую ADMIN-учётную запись."}
  if _is_admin(target) and target["enabled"]:
    active_admins = [
      row for row in app_tables.users.search(role=_role_by_code("admin"))
      if row["enabled"]
    ]
    if len(active_admins) <= 1:
      return {"ok": False, "message": "Нельзя удалить последнего активного ADMIN."}
  target_id = str(target.get_id())
  email = target["email"]
  log_audit(
    actor=actor, action="auth.managed_user_deleted", entity_type="user",
    entity_id=target_id, details={"email": email},
    created_at=datetime.now(timezone.utc)
  )
  target.delete()
  return {"ok": True, "message": "Учётная запись удалена."}


@anvil.server.callable(require_user=True)
@admin_guard
def get_managed_user_activity(user_id):
  if not isinstance(user_id, str) or not user_id:
    return {"ok": False, "message": "Некорректная учётная запись.", "rows": []}
  user = app_tables.users.get_by_id(user_id)
  if user is None:
    return {"ok": False, "message": "Учётная запись не найдена.", "rows": []}
  rows = app_tables.audit_logs.search(
    q.fetch_only("action", "entity_type", "entity_id", "created_at", "details", "actor",
                 actor=q.fetch_only("email")),
    order_by("created_at", ascending=False),
    q.any_of(actor=user, entity_id=user_id)
  )[:50]
  return {
    "ok": True,
    "rows": [{
      "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M UTC") if row["created_at"] else "",
      "action": row["action"] or "",
      "entity_type": row["entity_type"] or "",
      "actor": row["actor"]["email"] if row["actor"] else "system",
      "details": row["details"] or {}
    } for row in rows]
  }


@anvil.server.callable(require_user=True)
@admin_guard
def get_recent_audit_logs():
  rows = app_tables.audit_logs.search(
    q.fetch_only(
      "action", "entity_type", "entity_id", "created_at"
    ),
    order_by("created_at", ascending=False)
  )[:40]
  return [
    "{} · {} · {}{}".format(
      row["created_at"].strftime("%Y-%m-%d %H:%M UTC") if row["created_at"] else "",
      row["action"] or "Событие",
      row["entity_type"] or "система",
      " · " + row["entity_id"] if row["entity_id"] else ""
    )
    for row in rows
  ]


@anvil.server.callable(require_user=True)
def record_successful_login():
  user = anvil.users.get_user()
  if user is None:
    return
  _ensure_core_data(user)
  log_audit(
    actor=user,
    action="auth.login",
    entity_type="session",
    entity_id="",
    details={},
    created_at=datetime.now(timezone.utc)
  )


@anvil.server.callable(require_user=True)
@admin_guard
def get_system_settings():
  user = anvil.users.get_user()
  if user is None:
    return None
  _ensure_core_data(user)
  return {
    "organization_name": _setting_value("organization_name"),
    "currency": _setting_value("currency"),
    "contact_email": _setting_value("contact_email"),
    "contact_phone": _setting_value("contact_phone"),
    "contact_address": _setting_value("contact_address"),
    "site_theme": _current_site_theme()
  }


@anvil.server.callable(require_user=True)
@admin_guard
def save_system_settings(values):
  user = anvil.users.get_user()
  if user is None:
    return {"ok": False, "message": "Для сохранения настроек необходимо войти."}
  _ensure_core_data(user)
  if not isinstance(values, dict):
    return {"ok": False, "message": "Некорректные данные настроек."}

  organization_name = values.get("organization_name")
  currency = values.get("currency")
  contact_email = values.get("contact_email", _setting_value("contact_email"))
  contact_phone = values.get("contact_phone", _setting_value("contact_phone"))
  contact_address = values.get("contact_address", _setting_value("contact_address"))
  site_theme = values.get("site_theme", _current_site_theme())
  if not isinstance(organization_name, str) or len(organization_name.strip()) > 120:
    return {"ok": False, "message": "Название организации не должно превышать 120 символов."}
  if not isinstance(currency, str):
    return {"ok": False, "message": "Укажите код валюты из трёх латинских букв."}
  currency = currency.strip().upper()
  if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
    return {"ok": False, "message": "Укажите код валюты из трёх латинских букв."}
  if not isinstance(contact_email, str) or len(contact_email.strip()) > 160 or (
    contact_email.strip() and (
      "@" not in contact_email.strip()
      or "." not in contact_email.strip().rsplit("@", 1)[-1]
    )
  ):
    return {"ok": False, "message": "Проверьте публичный email."}
  if not isinstance(contact_phone, str) or len(contact_phone.strip()) > 40:
    return {"ok": False, "message": "Телефон не должен превышать 40 символов."}
  if not isinstance(contact_address, str) or len(contact_address.strip()) > 240:
    return {"ok": False, "message": "Адрес не должен превышать 240 символов."}
  if not isinstance(site_theme, str) or site_theme not in SITE_THEME_CODES:
    return {"ok": False, "message": "Выберите одну из доступных тем оформления."}

  updated_at = datetime.now(timezone.utc)
  for key, value in (
    ("organization_name", organization_name.strip()),
    ("currency", currency),
    ("contact_email", contact_email.strip().lower()),
    ("contact_phone", contact_phone.strip()),
    ("contact_address", contact_address.strip()),
    ("site_theme", site_theme)
  ):
    row = app_tables.system_settings.get(key=key)
    if row is None:
      app_tables.system_settings.add_row(
        key=key, value=value, updated_at=updated_at, updated_by=user
      )
    else:
      row.update(value=value, updated_at=updated_at, updated_by=user)

  log_audit(
    actor=user,
    action="settings.update",
    entity_type="system_settings",
    entity_id="",
    details={"keys": [
      "organization_name", "currency", "contact_email", "contact_phone",
      "contact_address", "site_theme"
    ]},
    created_at=updated_at
  )
  return {"ok": True, "message": "Настройки сохранены."}
