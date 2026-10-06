"""Shared access checks and ordinary full-page navigation helpers."""

from anvil import Notification, open_form
import anvil.server
import anvil.users


_SESSION_CONTEXT = None
_ADMIN_NAVIGATION_ACTIVE = False
_ADMIN_NAVIGATION_CATEGORY = None
_ADMIN_WINDOW_TITLE = "Обзор проекта"
_SITE_THEME_CACHE = None
_ADMIN_FORM_TITLES = {
  "AdminTools": "Обзор проекта",
  "Profile": "Личный кабинет",
  "Catalog": "Каталог и товары",
  "Catalog.ProductEditor": "Карточка товара",
  "Catalog.Orders": "Заявки каталога",
  "Catalog.Media": "Медиа каталога",
  "Catalog.Taxonomy": "Категории и бренды",
  "ImportEngine": "Импорт каталога",
  "Compatibility": "Совместимость оборудования",
  "CMS": "Страницы и контент",
  "SiteMenu": "Меню сайта",
  "Gallery": "Галерея работ",
  "Calculations": "Инженерные расчёты",
  "VentilationCalculator": "Расчёт вентиляции",
  "InstallationCalculator": "Монтаж и расчёты",
  "Projects": "Проекты и системы",
  "Operations": "Клиенты и обслуживание",
  "AdminUsers": "Пользователи и роли",
  "AdminSettings": "Центр настроек",
  "SystemDiagnostics": "Системная диагностика",
  "Backup": "Резервные копии",
  "AIOperator": "ИИ и интеграции",
  "SocialSettings": "Социальные каналы"
}


def get_session_context():
  """Reuse the read-only access lookup across Forms in this session."""
  global _SESSION_CONTEXT
  if _SESSION_CONTEXT is None:
    try:
      _SESSION_CONTEXT = anvil.server.call("get_access_context")
    except Exception:
      user = anvil.users.get_user()
      return {
        "email": user["email"] if user is not None else "",
        "role_code": "user", "role_title": "Пользователь",
        "permissions": [], "runtime_unavailable": True
      }
  return _SESSION_CONTEXT


def get_cached_session_context():
  """Return UI permissions without starting a server call during public navigation."""
  if _SESSION_CONTEXT is not None:
    return _SESSION_CONTEXT

  user = anvil.users.get_user()
  email = user["email"] if user is not None else ""
  return {
    "email": email,
    "role_code": "user",
    "role_title": "Пользователь",
    "permissions": []
  }


def clear_session_context():
  """Drop cached permissions after login or logout changes the active user."""
  global _SESSION_CONTEXT
  _SESSION_CONTEXT = None


def get_site_theme():
  """Read and cache the public site theme for subsequent page layouts."""
  global _SITE_THEME_CACHE
  if _SITE_THEME_CACHE not in ("blue", "graphite", "ice", "amber", "crimson", "violet"):
    try:
      theme = anvil.server.call("get_current_site_theme")
    except Exception:
      return "blue"
    _SITE_THEME_CACHE = theme if theme in (
      "blue", "graphite", "ice", "amber", "crimson", "violet"
    ) else "blue"
  return _SITE_THEME_CACHE


def set_site_theme(theme):
  """Keep newly saved theme choices in sync across client-side navigation."""
  global _SITE_THEME_CACHE
  if theme in ("blue", "graphite", "ice", "amber", "crimson", "violet"):
    _SITE_THEME_CACHE = theme


def open_window(form_name, *args, **properties):
  """Keep old call sites working while opening every section as a page."""
  close_admin_navigation()
  global _ADMIN_WINDOW_TITLE
  _ADMIN_WINDOW_TITLE = "Обзор проекта"
  properties.pop("window_title", None)
  properties.pop("window_key", None)
  return open_form(form_name, *args, **properties)


def open_admin_window(form_name, *args, **properties):
  """Open an admin tool while keeping the shared admin rail visible."""
  global _ADMIN_NAVIGATION_ACTIVE, _ADMIN_WINDOW_TITLE
  _ADMIN_NAVIGATION_ACTIVE = True
  _ADMIN_WINDOW_TITLE = properties.pop("window_title", None) or _ADMIN_FORM_TITLES.get(
    form_name, form_name.replace(".", " · ")
  )
  properties.pop("window_key", None)
  return open_form(form_name, *args, **properties)


def open_context_window(form_name, *args, **properties):
  """Keep admin navigation when moving between tools; close it for public pages."""
  if _ADMIN_NAVIGATION_ACTIVE:
    return open_admin_window(form_name, *args, **properties)
  return open_window(form_name, *args, **properties)


def open_admin_dashboard():
  """Open the dashboard inside the shared, persistent admin workspace."""
  global _ADMIN_NAVIGATION_ACTIVE, _ADMIN_NAVIGATION_CATEGORY, _ADMIN_WINDOW_TITLE
  _ADMIN_NAVIGATION_ACTIVE = True
  _ADMIN_NAVIGATION_CATEGORY = None
  _ADMIN_WINDOW_TITLE = "Обзор проекта"
  return open_form("AdminTools")


def open_context_home():
  """Return to the current workspace home without changing public navigation."""
  if _ADMIN_NAVIGATION_ACTIVE:
    return open_admin_dashboard()
  return open_window("Form1")


def get_admin_window_title():
  return _ADMIN_WINDOW_TITLE


def close_admin_navigation():
  global _ADMIN_NAVIGATION_ACTIVE, _ADMIN_NAVIGATION_CATEGORY
  _ADMIN_NAVIGATION_ACTIVE = False
  _ADMIN_NAVIGATION_CATEGORY = None


def admin_navigation_active():
  return _ADMIN_NAVIGATION_ACTIVE


def get_admin_navigation_category():
  return _ADMIN_NAVIGATION_CATEGORY


def set_admin_navigation_category(category):
  global _ADMIN_NAVIGATION_CATEGORY
  _ADMIN_NAVIGATION_CATEGORY = category


def has_permission(permission):
  context = get_session_context()
  return context["role_code"] == "admin" or permission in context["permissions"]


def require_permission_form(permission):
  context = get_session_context()
  if context.get("runtime_unavailable"):
    Notification(
      "Сервер Anvil не отвечает. Права доступа не удалось проверить; "
      "повторите вход, когда сервер приложения восстановится.", style="warning"
    ).show()
    return False
  if context["role_code"] == "admin" or permission in context["permissions"]:
    return True
  Notification("Недостаточно прав для этого раздела.").show()
  return False


def require_staff_form():
  context = get_session_context()
  if context.get("runtime_unavailable"):
    Notification(
      "Сервер Anvil не отвечает. Админ-панель не может проверить права доступа.",
      style="warning"
    ).show()
    return False
  is_staff = context["role_code"] == "admin" or (
    context["role_code"] == "moderator"
    and "dashboard.view" in context["permissions"]
  )
  if is_staff:
    return True
  Notification("Админ-панель доступна только ADMIN и MODERATOR.", style="warning").show()
  return False


def require_admin_form():
  context = get_session_context()
  if context.get("runtime_unavailable"):
    Notification(
      "Сервер Anvil не отвечает. Административный доступ не подтверждён.",
      style="warning"
    ).show()
    return False
  if context["role_code"] == "admin":
    return True
  Notification("Раздел доступен только ADMIN.", style="warning").show()
  return False


def require_user_form():
  if anvil.users.get_user() is not None:
    return True
  open_form("Profile")
  return False


def route_after_login():
  """Return to the public home page without another server request."""
  return open_form("Form1")
