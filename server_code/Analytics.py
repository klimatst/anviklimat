import anvil.secrets
from datetime import datetime, timedelta, timezone
import math
from typing import Any, cast

import anvil.http
import anvil.server
import anvil.users
from anvil.tables import app_tables, query as q
from urllib.parse import urlsplit
import Config
import Core
import AdminStudio


TELEGRAM_TOKEN_SECRET = "TELEGRAM_BOT_TOKEN"


def _admin_user():
  return Core.get_admin_user()


def _count(table_name, **filters):
  # Data Table schemas can lag behind code when an app is synced to an
  # environment that has not created every optional module table yet.
  table = getattr(app_tables, table_name, None)
  if table is None:
    return 0
  return len(table.search(q.fetch_only(), **filters))


def _telegram_chat_id():
  table = getattr(app_tables, "system_settings", None)
  if table is None:
    return ""
  row = table.get(key="telegram_chat_id")
  value = row["value"] if row is not None else ""
  return value if isinstance(value, str) else ""


def _telegram_chat_ids():
  targets = [_telegram_chat_id()]
  row = app_tables.system_settings.get(key="telegram_chat_targets")
  extra = row["value"] if row is not None else []
  if isinstance(extra, list):
    targets.extend(value for value in extra if isinstance(value, str))
  return list(dict.fromkeys(value.strip() for value in targets if value.strip()))


def _valid_telegram_chat_id(chat_id):
  if not isinstance(chat_id, str):
    return False
  chat_id = chat_id.strip()
  numeric = chat_id.isdigit() or (
    len(chat_id) > 1 and chat_id.startswith("-") and chat_id[1:].isdigit()
  )
  channel = (
    chat_id.startswith("@") and 6 <= len(chat_id) <= 33
    and chat_id[1:].isascii()
    and all(char.isalnum() or char == "_" for char in chat_id[1:])
  )
  return bool(chat_id and (numeric and len(chat_id.lstrip("-")) <= 32 or channel))


def _dashboard(include_admin_settings=True, include_widgets=False, include_audit=False):
  now = datetime.now(timezone.utc)
  week_ago = now - timedelta(days=7)
  visible_products = list(app_tables.products.search(
    q.fetch_only("identity_key", "description"),
    active=True,
    identity_key=q.not_(q.ilike("demo|%"))
  ))
  visible_product_ids = {row.get_id() for row in visible_products}
  products_with_images = {
    row["product"].get_id()
    for row in app_tables.product_media.search(
      # file_id and url are present in both the current and legacy table
      # schemas. Some deployed environments do not yet have the optional
      # `file` Media column, so the dashboard must not depend on it.
      q.fetch_only("product", "file_id", "url")
    )
    if row["product"] is not None
    and row["product"].get_id() in visible_product_ids
    and (row["file_id"] or row["url"])
  }
  new_catalog_orders = _count("catalog_orders", status="new")
  processing_catalog_orders = _count("catalog_orders", status="processing")
  open_tasks = _count("crm_tasks", status="open") + _count(
    "crm_tasks", status="in_progress"
  )
  recent_activity = _count("audit_logs", created_at=q.greater_than(week_ago))
  ai_calls = _count("ai_usage", created_at=q.greater_than(week_ago))
  metrics = [
    ("Новые заявки каталога", new_catalog_orders),
    ("Заявки в обработке", processing_catalog_orders),
    ("Товары витрины", len(visible_products)),
    ("Товары без изображений", len(visible_product_ids - products_with_images)),
    ("Товары без описания", sum(
      1 for row in visible_products if not (row["description"] or "").strip()
    )),
    ("Активные категории", _count("catalog_categories", active=True)),
    ("Страницы CMS", _count("cms_pages")),
    ("Опубликованные страницы", _count("cms_pages", status="published")),
    ("Проекты", _count("projects")),
    ("Объекты", _count("objects")),
    ("Клиенты CRM", _count("crm_clients")),
    ("Открытые задачи", open_tasks),
    ("Предложения на согласовании", _count("quotes", status="sent")),
    ("Сервисные работы в процессе", _count("service", status="in_progress")),
    ("События аудита за 7 дней", recent_activity),
    ("AI-запросы за 7 дней", ai_calls)
  ]
  if include_admin_settings:
    metrics.append(("Активные пользователи", _count("users", enabled=True)))
  dashboard_widgets = {"widgets": [], "available_count": 0}
  if include_widgets:
    widget_cache = {
      "active_products": visible_products,
      "product_image_ids": products_with_images
    }
    dashboard_widgets = cast(Any, AdminStudio)._admin_dashboard_widget_data(widget_cache)
  recent_audit = Core.get_recent_audit_logs() if include_audit else []
  return {
    "ok": True,
    "as_of": now.isoformat(timespec="minutes"),
    "metrics": [{"label": label, "value": value} for label, value in metrics],
    "widgets": dashboard_widgets["widgets"],
    "widgets_available_count": dashboard_widgets["available_count"],
    "recent_audit": recent_audit,
    "telegram_chat_id": _telegram_chat_id() if include_admin_settings else "",
    "telegram_configured": (
      bool(Config.get_secret(TELEGRAM_TOKEN_SECRET)) if include_admin_settings else False
    )
  }


@anvil.server.callable(require_user=True)
@Core.staff_guard
def get_admin_dashboard():
  user = Core.require_staff_user()
  return _dashboard(
    include_admin_settings=Core._is_admin(user), include_widgets=True,
    include_audit=Core._is_admin(user)
  )


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_telegram_target(chat_id):
  user = _admin_user()
  if user is None:
    return {"ok": False, "message": "Настройка Telegram доступна только администратору."}
  if not isinstance(chat_id, str):
    return {"ok": False, "message": "Укажите Telegram chat ID или имя канала."}
  chat_id = chat_id.strip()
  if len(chat_id) > 64:
    return {"ok": False, "message": "Идентификатор Telegram слишком длинный."}
  if chat_id and not _valid_telegram_chat_id(chat_id):
    return {"ok": False, "message": "Проверьте числовой chat ID или имя канала вида @channel."}

  now = datetime.now(timezone.utc)
  row = app_tables.system_settings.get(key="telegram_chat_id")
  if row is None:
    app_tables.system_settings.add_row(
      key="telegram_chat_id", value=chat_id,
      updated_at=now, updated_by=user
    )
  else:
    row.update(value=chat_id, updated_at=now, updated_by=user)
  Core.log_audit(
    actor=user, action="settings.telegram_target_update",
    entity_type="system_settings", entity_id="telegram_chat_id",
    details={}, created_at=now
  )
  return {"ok": True, "message": "Получатель Telegram сохранён."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_telegram_chat_targets(targets_text):
  user = _admin_user()
  if user is None:
    return {"ok": False, "message": "Настройка Telegram доступна только администратору."}
  if not isinstance(targets_text, str) or len(targets_text) > 400:
    return {"ok": False, "message": "Укажите до четырёх дополнительных чатов."}
  primary = _telegram_chat_id()
  targets = []
  for chat_id in targets_text.splitlines():
    chat_id = chat_id.strip()
    if not chat_id:
      continue
    if not _valid_telegram_chat_id(chat_id):
      return {"ok": False, "message": "Проверьте ID чата или публичное имя вида @channel."}
    if chat_id != primary and chat_id not in targets:
      targets.append(chat_id)
  if len(targets) > 4:
    return {"ok": False, "message": "Можно добавить не более четырёх дополнительных чатов."}
  now = datetime.now(timezone.utc)
  row = app_tables.system_settings.get(key="telegram_chat_targets")
  if row is None:
    app_tables.system_settings.add_row(
      key="telegram_chat_targets", value=targets, updated_at=now, updated_by=user
    )
  else:
    row.update(value=targets, updated_at=now, updated_by=user)
  Core.log_audit(
    actor=user, action="settings.telegram_targets_update",
    entity_type="system_settings", entity_id="telegram_chat_targets",
    details={"count": len(targets)}, created_at=now
  )
  return {"ok": True, "message": "Список дополнительных Telegram-чатов сохранён."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_social_settings():
  user = _admin_user()
  if user is None:
    raise anvil.server.PermissionDenied("Раздел доступен только администратору.")
  values = {}
  for platform in ("vk", "ok", "dzen", "max"):
    row = app_tables.system_settings.get(key="social_{}_url".format(platform))
    value = row["value"] if row is not None else ""
    values["{}_url".format(platform)] = value if isinstance(value, str) else ""
  values.update({
    "telegram_chat_id": _telegram_chat_id(),
    "telegram_chat_targets": "\n".join(
      target for target in _telegram_chat_ids() if target != _telegram_chat_id()
    ),
    "telegram_configured": bool(Config.get_secret(TELEGRAM_TOKEN_SECRET))
  })
  return {"ok": True, "settings": values}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_social_links(values):
  user = _admin_user()
  if user is None:
    raise anvil.server.PermissionDenied("Раздел доступен только администратору.")
  if not isinstance(values, dict):
    return {"ok": False, "message": "Проверьте ссылки на площадки."}
  platforms = {
    "vk_url": "vk",
    "ok_url": "ok",
    "dzen_url": "dzen",
    "max_url": "max"
  }
  checked = {}
  for field, platform in platforms.items():
    value = values.get(field, "")
    if value is None:
      value = ""
    if not isinstance(value, str) or len(value.strip()) > 500:
      return {"ok": False, "message": "Проверьте адрес каждой площадки."}
    value = value.strip()
    if value:
      try:
        parsed = urlsplit(value)
      except ValueError:
        return {"ok": False, "message": "Проверьте адрес каждой площадки."}
      if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return {"ok": False, "message": "Используйте полные публичные HTTPS-ссылки."}
    checked[platform] = value

  now = datetime.now(timezone.utc)
  for platform, value in checked.items():
    key = "social_{}_url".format(platform)
    row = app_tables.system_settings.get(key=key)
    if row is None:
      app_tables.system_settings.add_row(
        key=key, value=value, updated_at=now, updated_by=user
      )
    else:
      row.update(value=value, updated_at=now, updated_by=user)
  Core.log_audit(
    actor=user, action="settings.social_links_update",
    entity_type="system_settings", entity_id="social_channels",
    details={"platforms": list(checked)}, created_at=now
  )
  return {"ok": True, "message": "Ссылки на социальные каналы сохранены."}


def _format_report(dashboard):
  lines = ["HVAC Studio · сводка", "На дату: {} UTC".format(dashboard["as_of"])]
  lines.extend(
    "{}: {}".format(metric["label"], metric["value"])
    for metric in dashboard["metrics"]
  )
  return "\n".join(lines)


def _send_telegram_message(chat_id, text, token=None):
  token = token or Config.get_secret(TELEGRAM_TOKEN_SECRET)
  if not token:
    return False
  try:
    response = anvil.http.request(
      "https://api.telegram.org/bot{}/sendMessage".format(token),
      method="POST", data={"chat_id": chat_id, "text": text},
      json=True, timeout=10
    )
  except anvil.http.HttpError:
    return False
  return isinstance(response, dict) and response.get("ok") is True


@anvil.server.callable(require_user=True)
@Core.admin_guard
def send_telegram_summary():
  user = _admin_user()
  if user is None:
    return {"ok": False, "message": "Отправка сводки доступна только администратору."}
  token = Config.get_secret(TELEGRAM_TOKEN_SECRET)
  chat_ids = _telegram_chat_ids()
  if not token:
    return {"ok": False, "message": "Задайте TELEGRAM_BOT_TOKEN в Anvil Secrets."}
  if not chat_ids:
    return {"ok": False, "message": "Сохраните основной или дополнительный chat ID Telegram."}

  now = datetime.now(timezone.utc)
  throttle = app_tables.system_settings.get(key="telegram_last_attempt")
  last_attempt = throttle["value"] if throttle is not None else None
  if (
    isinstance(last_attempt, (int, float)) and not isinstance(last_attempt, bool)
    and math.isfinite(last_attempt)
    and now.timestamp() - last_attempt < 60
  ):
    return {"ok": False, "message": "Отправка сводки доступна не чаще раза в минуту."}
  if throttle is None:
    throttle = app_tables.system_settings.add_row(
      key="telegram_last_attempt", value=now.timestamp(),
      updated_at=now, updated_by=user
    )
  else:
    throttle.update(value=now.timestamp(), updated_at=now, updated_by=user)

  dashboard = _dashboard()
  sent = sum(1 for chat_id in chat_ids
             if _send_telegram_message(chat_id, _format_report(dashboard), token))
  if not sent:
    return {"ok": False, "message": "Telegram не подтвердил отправку сводки."}
  Core.log_audit(
    actor=user, action="telegram.summary_sent", entity_type="telegram",
    entity_id="", details={"metrics": len(dashboard["metrics"]),
                            "sent": sent, "targets": len(chat_ids)},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Сводка отправлена в {} из {} чатов Telegram.".format(sent, len(chat_ids))}


def notify_telegram_order(order):
  """Send an opt-in order notification to configured server-side Telegram chats."""
  if AdminStudio.get_admin_studio_setting("notifications.telegram_orders", False) is not True:
    return {"ok": True, "sent": 0}
  token = Config.get_secret(TELEGRAM_TOKEN_SECRET)
  chat_ids = _telegram_chat_ids()
  if not token or not chat_ids:
    return {"ok": False, "sent": 0}
  details = [
    "Новая заявка каталога",
    "Товар: {}".format(order["product_name"] or "—"),
    "Модель / артикул: {} / {}".format(order["model"] or "—", order["sku"] or "—"),
    "Количество: {}".format(order["quantity"] or 1),
    "Клиент: {}".format(order["customer_name"] or "—"),
    "Телефон: {}".format(order["phone"] or "—")
  ]
  if order["email"]:
    details.append("Email: {}".format(order["email"]))
  if order["comment"]:
    details.append("Комментарий: {}".format(order["comment"][:700]))
  message = "\n".join(details)
  sent = sum(1 for chat_id in chat_ids if _send_telegram_message(chat_id, message, token))
  return {"ok": sent > 0, "sent": sent}


def notify_telegram_import(filename, products, pages, failed_pages, images):
  """Send an opt-in PDF import completion summary without extracted contents."""
  if AdminStudio.get_admin_studio_setting("notifications.telegram_imports", False) is not True:
    return {"ok": True, "sent": 0}
  token = Config.get_secret(TELEGRAM_TOKEN_SECRET)
  chat_ids = _telegram_chat_ids()
  if not token or not chat_ids:
    return {"ok": False, "sent": 0}
  message = "\n".join([
    "Обработка PDF завершена",
    "Файл: {}".format((filename or "PDF")[:120]),
    "Страниц: {}".format(pages),
    "Черновых товаров: {}".format(products),
    "Изображений: {}".format(images),
    "Страниц с ошибкой: {}".format(failed_pages)
  ])
  sent = sum(1 for chat_id in chat_ids if _send_telegram_message(chat_id, message, token))
  return {"ok": sent > 0, "sent": sent}
