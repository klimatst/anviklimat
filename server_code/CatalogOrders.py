"""Public catalog order intake and protected order management."""

import re
from datetime import datetime, timezone

import anvil.server
from anvil.tables import app_tables, order_by, query as q
import Core
import Analytics
import AdminStudio


ORDER_STATUSES = {
  "new": "Новый",
  "processing": "В обработке",
  "completed": "Завершён",
  "cancelled": "Отменён"
}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _clean_text(value, label, maximum, required=False, trim=True):
  if value is None:
    value = ""
  if not isinstance(value, str):
    return None, "Проверьте поле «{}» и повторите отправку.".format(label)
  if trim:
    value = value.strip()
  if required and not value.strip():
    return None, "Заполните поле «{}».".format(label)
  if len(value) > maximum:
    return None, "Поле «{}» слишком длинное.".format(label)
  return value, None


@anvil.server.callable
def get_catalog_order_form_settings():
  return _catalog_order_form_settings()


def _catalog_order_form_settings():
  message_limit = AdminStudio.get_admin_studio_setting("forms.message_limit", 1200)
  if (isinstance(message_limit, bool)
      or not isinstance(message_limit, (int, float))
      or message_limit < 100 or message_limit > 5000):
    message_limit = 1200
  return {
    "enabled": AdminStudio.get_admin_studio_setting("orders.accept_public", True) is not False,
    "phone_required": AdminStudio.get_admin_studio_setting("orders.require_phone", True) is not False,
    "email_required": AdminStudio.get_admin_studio_setting("orders.require_email", False) is True,
    "comment_enabled": AdminStudio.get_admin_studio_setting("forms.lead_comment", True) is not False,
    "comment_limit": int(message_limit)
  }


@anvil.server.callable
def create_catalog_order(product_id, quantity, customer_name, phone, email="", comment=""):
  if AdminStudio.get_admin_studio_setting("orders.accept_public", True) is False:
    return {"ok": False, "message": "Приём заявок через каталог временно отключён."}
  if not isinstance(product_id, str) or not product_id or len(product_id) > 100:
    return {"ok": False, "message": "Не удалось определить товар. Обновите каталог и повторите заказ."}

  if isinstance(quantity, bool) or not isinstance(quantity, (str, int)):
    return {"ok": False, "message": "Количество должно быть целым числом от 1 до 999."}
  try:
    parsed_quantity = int(quantity)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Количество должно быть целым числом от 1 до 999."}
  if parsed_quantity < 1 or parsed_quantity > 999:
    return {"ok": False, "message": "Количество должно быть целым числом от 1 до 999."}
  if isinstance(quantity, str) and str(parsed_quantity) != quantity.strip():
    return {"ok": False, "message": "Количество должно быть целым числом от 1 до 999."}

  form_settings = _catalog_order_form_settings()
  trim_input = AdminStudio.get_admin_studio_setting("forms.trim_input", True) is not False
  customer_name, error = _clean_text(
    customer_name, "имя", 120, required=True, trim=trim_input
  )
  if error:
    return {"ok": False, "message": error}
  phone, error = _clean_text(phone, "телефон", 40, trim=trim_input)
  if error:
    return {"ok": False, "message": error}
  email, error = _clean_text(email, "email", 160, trim=trim_input)
  if error:
    return {"ok": False, "message": error}
  comment, error = _clean_text(
    comment, "комментарий", form_settings["comment_limit"], trim=trim_input
  )
  if error:
    return {"ok": False, "message": error}
  if not phone and not email:
    return {"ok": False, "message": "Укажите телефон или email для связи."}
  if form_settings["phone_required"] and not phone:
    return {"ok": False, "message": "Укажите телефон для связи."}
  if form_settings["email_required"] and not email:
    return {"ok": False, "message": "Укажите email для связи."}
  if not form_settings["comment_enabled"]:
    comment = ""
  if phone and sum(character.isdigit() for character in phone) < 7:
    return {"ok": False, "message": "Проверьте номер телефона."}
  if email and not EMAIL_RE.fullmatch(email):
    return {"ok": False, "message": "Проверьте адрес email."}

  product = app_tables.products.get_by_id(product_id)
  if product is None or not product["active"]:
    return {"ok": False, "message": "Товар больше недоступен. Обновите каталог."}

  brand = product["brand"]
  model = product["model"] or ""
  product_name = "{} {}".format(
    brand["name"] if brand is not None else "", model
  ).strip() or model or product["type"] or "Товар каталога"
  category = product["category"]
  subcategory = product["subcategory"]
  series = product["series"]
  category_name = category["title"] if category is not None else ""
  subcategory_name = subcategory["title"] if subcategory is not None else ""
  series_name = series["title"] if series is not None else ""
  price = app_tables.product_prices.get(product=product)
  now = datetime.now(timezone.utc)
  sale_price = price["sale_price"] if price is not None else None
  initial_status = AdminStudio.get_admin_studio_setting("orders.initial_status", "new")
  if initial_status not in ("new", "processing"):
    initial_status = "new"
  order = app_tables.catalog_orders.add_row(
    product=product,
    product_name=product_name[:160],
    category_name=category_name[:120],
    subcategory_name=subcategory_name[:120],
    series_name=series_name[:120],
    model=model[:100],
    sku=(product["sku"] or "")[:80],
    quantity=parsed_quantity,
    unit_price=sale_price if sale_price is not None else 0,
    price_known=sale_price is not None,
    currency=(price["currency"] or "RUB") if price is not None else "RUB",
    customer_name=customer_name or "",
    phone=phone or "",
    email=email or "",
    comment=comment or "",
    status=initial_status,
    created_at=now,
    updated_at=now
  )
  Core.log_audit(
    action="catalog.order_created", entity_type="catalog_order",
    entity_id=order.get_id(),
    details={
      "product_id": product_id, "quantity": parsed_quantity,
      "category": category_name, "subcategory": subcategory_name,
      "series": series_name
    },
    created_at=now
  )
  Analytics.notify_telegram_order(order)
  success_title = AdminStudio.get_admin_studio_setting("orders.success_title", "Заявка отправлена")
  success_message = AdminStudio.get_admin_studio_setting(
    "orders.success_message", "Мы свяжемся с вами для уточнения деталей."
  )
  return {
    "ok": True,
    "order_id": order.get_id(),
    "message": "{} · №{}. {}".format(
      success_title, order.get_id()[-8:], success_message
    )
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def get_catalog_orders(search_text="", status="all", limit=200):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для работы с заказами каталога.")
  if not isinstance(search_text, str) or len(search_text) > 120:
    return {"ok": False, "message": "Поисковый запрос слишком длинный.", "rows": []}
  if status not in ("all",) + tuple(ORDER_STATUSES):
    return {"ok": False, "message": "Выбран неизвестный статус заказа.", "rows": []}
  if isinstance(limit, bool) or not isinstance(limit, int):
    return {"ok": False, "message": "Некорректный размер списка заказов.", "rows": []}
  limit = min(max(limit, 1), 500)

  expressions = [
    q.fetch_only(
      "product_name", "category_name", "subcategory_name", "series_name",
      "model", "sku", "quantity", "unit_price", "price_known", "currency",
      "customer_name", "phone", "email", "comment", "status", "created_at"
    ),
    order_by("created_at", ascending=False),
    q.page_size(limit + 1)
  ]
  term = search_text.strip()
  if term:
    pattern = "%" + term + "%"
    expressions.append(q.any_of(
      product_name=q.ilike(pattern), model=q.ilike(pattern),
      category_name=q.ilike(pattern), subcategory_name=q.ilike(pattern),
      series_name=q.ilike(pattern), sku=q.ilike(pattern), customer_name=q.ilike(pattern),
      phone=q.ilike(pattern), email=q.ilike(pattern)
    ))
  filters = {} if status == "all" else {"status": status}
  records = list(app_tables.catalog_orders.search(*expressions, **filters)[:limit + 1])
  has_more = len(records) > limit
  rows = []
  for row in records[:limit]:
    created_at = row["created_at"]
    rows.append({
      "id": row.get_id(),
      "product_name": row["product_name"] or "Товар удалён из каталога",
      "category_name": row["category_name"] or "",
      "subcategory_name": row["subcategory_name"] or "",
      "series_name": row["series_name"] or "",
      "model": row["model"] or "",
      "sku": row["sku"] or "",
      "quantity": row["quantity"] or 1,
      "unit_price": row["unit_price"],
      "price_known": bool(row["price_known"]),
      "currency": row["currency"] or "RUB",
      "customer_name": row["customer_name"] or "",
      "phone": row["phone"] or "",
      "email": row["email"] or "",
      "comment": row["comment"] or "",
      "status": row["status"] or "new",
      "status_title": ORDER_STATUSES.get(row["status"] or "new", "Неизвестный статус"),
      "created_at": created_at.isoformat(timespec="minutes") if created_at else ""
    })
  return {
    "ok": True, "rows": rows, "has_more": has_more,
    "message": "Показано заявок: {}{}".format(len(rows), " · есть ещё" if has_more else "")
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("catalog.manage")
def update_catalog_order_status(order_id, status):
  user = Core.require_permission("catalog.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Недостаточно прав для изменения заказов каталога.")
  if not isinstance(order_id, str) or not order_id or len(order_id) > 100:
    return {"ok": False, "message": "Выберите заказ."}
  if status not in ORDER_STATUSES:
    return {"ok": False, "message": "Выбран неизвестный статус заказа."}
  row = app_tables.catalog_orders.get_by_id(order_id)
  if row is None:
    return {"ok": False, "message": "Заказ не найден."}
  previous_status = row["status"] or "new"
  now = datetime.now(timezone.utc)
  row.update(status=status, updated_at=now)
  Core.log_audit(
    actor=user, action="catalog.order_status_updated",
    entity_type="catalog_order", entity_id=order_id,
    details={"from": previous_status, "to": status}, created_at=now
  )
  return {"ok": True, "message": "Статус заказа обновлён."}
