import math
import uuid
from datetime import datetime, timezone

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
from typing import Any, cast

import Core


MAX_SELECTIONS = 100


def _positive_amount(value, label):
  if isinstance(value, bool) or not isinstance(value, (str, int, float)):
    return None, "Проверьте количество «{}».".format(label)
  try:
    amount = float(str(value).replace(" ", "").replace(",", "."))
  except ValueError:
    return None, "Проверьте количество «{}».".format(label)
  if not math.isfinite(amount) or amount <= 0 or amount > 1000000:
    return None, "Количество «{}» должно быть больше нуля.".format(label)
  return amount, None


def _category_is_material(category):
  while category is not None:
    if category["code"] == "materials":
      return True
    category = category["parent"]
  return False


def _product_unit(product, spec_by_product):
  specs = spec_by_product.get(product.get_id(), {})
  for key in ("unit", "sale_unit", "measurement_unit", "единица", "единица измерения"):
    value = specs.get(key)
    if value:
      return value
  category = product["category"]
  if category is not None and not _category_is_material(category):
    return "шт"
  return ""


def price_catalog_selections(selections, require_installation=False,
                             allow_missing=False, allow_empty=False):
  """Build estimate lines from current catalog prices and product specifications."""
  if not isinstance(selections, list) or len(selections) > MAX_SELECTIONS:
    return {"ok": False, "message": "В смету можно добавить не более 100 позиций."}
  if not selections:
    if allow_empty:
      return {
        "ok": True, "lines": [], "materials_cost": 0.0, "labor_cost": 0.0,
        "materials_base_cost": 0.0, "discount_total": 0.0,
        "currency": Core.get_currency(), "missing_installation": [],
        "missing_pricing": []
      }
    return {"ok": False, "message": "Добавьте оборудование или материал из каталога."}

  normalized = []
  products = []
  seen = set()
  for item in selections:
    if not isinstance(item, dict):
      return {"ok": False, "message": "Проверьте позиции каталога в смете."}
    product_id = item.get("product_id")
    if not isinstance(product_id, str) or not product_id or len(product_id) > 100:
      return {"ok": False, "message": "Выберите позицию из каталога."}
    product = app_tables.products.get_by_id(product_id)
    if product is None or not product["active"]:
      return {"ok": False, "message": "Одна из позиций больше не доступна в каталоге."}
    quantity, error = _positive_amount(item.get("quantity"), product["model"] or "товар")
    if error:
      return {"ok": False, "message": error}
    if product_id in seen:
      return {"ok": False, "message": "Одна позиция каталога указана несколько раз."}
    seen.add(product_id)
    normalized.append((product, quantity))
    products.append(product)

  product_match = q.any_of(*[q.all_of(product=product) for product in products])
  price_by_id = {
    row["product"].get_id(): row
    for row in app_tables.product_prices.search(
      q.fetch_only(
        "product", "sale_price", "special_price", "discount", "currency",
        "installation_price", "updated_at"
      ),
      product_match
    )
  }
  spec_by_product = {}
  for row in app_tables.product_specs.search(
    q.fetch_only("product", "key", "value"), product_match
  ):
    spec_by_product.setdefault(row["product"].get_id(), {})[
      (row["key"] or "").strip().casefold()
    ] = (row["value"] or "").strip()

  currency = Core.get_currency()
  material_total = 0.0
  material_base_total = 0.0
  discount_total = 0.0
  labor_total = 0.0
  lines = []
  missing_installation = []
  missing_pricing = []
  for product, quantity in normalized:
    product_id = product.get_id()
    category = product["category"]
    is_material = category is not None and _category_is_material(category)
    unit = _product_unit(product, spec_by_product)
    brand = product["brand"]
    description = "{} {}".format(
      brand["name"] if brand is not None else "",
      product["model"] or product["sku"] or "Оборудование"
    ).strip()
    price = price_by_id.get(product_id)
    if price is None or price["sale_price"] is None:
      if allow_missing:
        missing_pricing.append(description)
        lines.append({
          "product": product, "description": description,
          "quantity": quantity, "unit": unit,
          "unit_price": None, "currency": "", "line_total": None,
          "source": "catalog", "group": "materials" if is_material else "equipment",
          "snapshot": {"product_id": product_id, "price_missing": True}
        })
        if not is_material:
          missing_installation.append(description)
        continue
      return {
        "ok": False,
        "message": "В каталоге не задана цена продажи для {}.".format(product["model"])
      }
    if (price["currency"] or "").strip() != currency:
      if allow_missing:
        missing_pricing.append(description)
        lines.append({
          "product": product, "description": description,
          "quantity": quantity, "unit": unit,
          "unit_price": None, "currency": price["currency"] or "",
          "line_total": None, "source": "catalog",
          "group": "materials" if is_material else "equipment",
          "snapshot": {"product_id": product_id, "price_currency_mismatch": True}
        })
        if not is_material:
          missing_installation.append(description)
        continue
      return {
        "ok": False,
        "message": "Для {} нужна цена в валюте проекта ({}).".format(product["model"], currency)
      }
    base_unit_price = price["sale_price"]
    if isinstance(base_unit_price, bool) or not isinstance(base_unit_price, (int, float)):
      return {"ok": False, "message": "Проверьте цену {} в каталоге.".format(product["model"])}
    if not math.isfinite(float(base_unit_price)) or base_unit_price < 0:
      return {"ok": False, "message": "Проверьте цену {} в каталоге.".format(product["model"])}
    base_unit_price = float(base_unit_price)
    raw_discount = price["discount"] or 0
    if (
      isinstance(raw_discount, bool) or not isinstance(raw_discount, (int, float))
      or not math.isfinite(float(raw_discount)) or not 0 <= raw_discount <= 100
    ):
      return {"ok": False, "message": "Проверьте скидку {} в каталоге.".format(product["model"])}
    special_price = price["special_price"]
    if special_price is not None:
      if (
        isinstance(special_price, bool) or not isinstance(special_price, (int, float))
        or not math.isfinite(float(special_price)) or special_price < 0
      ):
        return {"ok": False, "message": "Проверьте специальную цену {} в каталоге.".format(product["model"])}
      unit_price = min(base_unit_price, float(special_price))
    else:
      unit_price = base_unit_price * (1 - float(raw_discount) / 100.0)
    unit_discount = round(max(0.0, base_unit_price - unit_price), 2)
    line_discount = round(quantity * unit_discount, 2)
    discount_percent = round(
      (unit_discount / base_unit_price * 100) if base_unit_price else 0, 3
    )
    if not unit:
      if allow_missing:
        missing_pricing.append(description)
        lines.append({
          "product": product, "description": description,
          "quantity": quantity, "unit": "", "unit_price": None,
          "currency": currency, "line_total": None, "source": "catalog",
          "group": "materials" if is_material else "equipment",
          "snapshot": {"product_id": product_id, "unit_missing": True}
        })
        if not is_material:
          missing_installation.append(description)
        continue
      return {
        "ok": False,
        "message": "Добавьте характеристику «unit» для {} в каталоге.".format(product["model"])
      }
    line_total = round(quantity * unit_price, 2)
    material_total += line_total
    material_base_total += round(quantity * base_unit_price, 2)
    discount_total += line_discount
    lines.append({
      "product": product,
      "description": description,
      "quantity": quantity,
      "unit": unit,
      "unit_price": unit_price,
      "base_unit_price": base_unit_price,
      "discount_percent": discount_percent,
      "discount_amount": line_discount,
      "currency": currency,
      "line_total": line_total,
      "source": "catalog",
      "group": "materials" if is_material else "equipment",
      "snapshot": {
        "product_id": product_id,
        "model": product["model"] or "",
        "sku": product["sku"] or "",
        "category": product["category"]["code"] if product["category"] else "",
        "base_unit_price": base_unit_price,
        "unit_price": unit_price,
        "discount_percent": discount_percent,
        "discount_amount": line_discount,
        "price_updated_at": price["updated_at"].isoformat(timespec="minutes")
        if price["updated_at"] else ""
      }
    })

    installation_price = price["installation_price"]
    if not is_material:
      if installation_price is None:
        missing_installation.append(description)
      elif (
        isinstance(installation_price, bool)
        or not isinstance(installation_price, (int, float))
        or not math.isfinite(float(installation_price))
        or installation_price < 0
      ):
        return {"ok": False, "message": "Проверьте цену монтажа {} в каталоге.".format(product["model"])}
      else:
        work_total = round(quantity * float(installation_price), 2)
        labor_total += work_total
        if work_total:
          lines.append({
            "product": product,
            "description": "Монтаж · " + description,
            "quantity": quantity,
            "unit": unit,
            "unit_price": float(installation_price),
            "currency": currency,
            "line_total": work_total,
            "source": "catalog_installation_price",
            "group": "works",
            "snapshot": {
              "product_id": product_id,
              "installation_price": float(installation_price),
              "price_updated_at": price["updated_at"].isoformat(timespec="minutes")
              if price["updated_at"] else ""
            }
          })

  if require_installation and missing_installation:
    return {
      "ok": False,
      "message": "Для КП с монтажом задайте цену монтажа в каталоге: {}.".format(
        ", ".join(missing_installation[:5])
      ),
      "missing_installation": missing_installation
    }
  return {
    "ok": True,
    "lines": lines,
    "materials_cost": round(material_total, 2),
    "materials_base_cost": round(material_base_total, 2),
    "discount_total": round(discount_total, 2),
    "discount_percent": round(
      discount_total / material_base_total * 100 if material_base_total else 0, 3
    ),
    "labor_cost": round(labor_total, 2),
    "currency": currency,
    "missing_installation": missing_installation,
    "missing_pricing": missing_pricing
  }


def save_estimate(project, user, priced, details=None, consumables_cost=0.0):
  if user is None or not Core.can_access_project(project, user):
    return {"ok": False, "message": "Смета доступна только владельцу проекта."}
  if not priced.get("ok"):
    return priced
  previous = next(iter(app_tables.estimates.search(
    q.fetch_only("version"), order_by("updated_at", ascending=False), project=project
  )), None)
  version = str(int(previous["version"]) + 1) if previous and previous["version"] else "1"
  now = datetime.now(timezone.utc)
  consumables = 0.0
  error = None
  if consumables_cost:
    consumables_value, error = _positive_amount(consumables_cost, "расходные материалы")
    if consumables_value is not None:
      consumables = consumables_value
  if error:
    return {"ok": False, "message": error}
  total = round(
    priced["materials_cost"] + priced["labor_cost"] + consumables, 2
  )
  estimate = app_tables.estimates.add_row(
    project=project,
    currency=priced["currency"],
    materials_cost=priced["materials_cost"],
    labor_cost=priced["labor_cost"],
    consumables_cost=consumables,
    total=total,
    details=details or {},
    version=version,
    updated_by=user,
    updated_at=now
  )
  line_rows = []
  for index, line in enumerate(priced["lines"], 1):
    line_rows.append({
      "estimate": estimate,
      "line_key": "line-{}".format(index),
      "product": line.get("product"),
      "description": line["description"],
      "quantity": line["quantity"],
      "unit": line["unit"],
      "unit_price": line["unit_price"],
      "currency": line["currency"],
      "line_total": line["line_total"],
      "source": line["source"],
      "snapshot": line["snapshot"]
    })
  for start in range(0, len(line_rows), 100):
    cast(Any, app_tables.estimate_lines).add_rows(line_rows[start:start + 100])
  Core.log_audit(
    actor=user,
    action="estimate.created",
    entity_type="estimate",
    entity_id=estimate.get_id(),
    details={"version": version, "total": total, "currency": priced["currency"]},
    created_at=now
  )
  return {
    "ok": True,
    "estimate_id": estimate.get_id(),
    "version": version,
    "currency": priced["currency"],
    "materials_cost": priced["materials_cost"],
    "labor_cost": priced["labor_cost"],
    "consumables_cost": consumables,
    "total": total,
    "lines": priced["lines"]
  }


def create_quote(project, estimate, user, terms=""):
  if user is None or not Core.can_access_project(project, user):
    return {"ok": False, "message": "КП доступно только владельцу проекта."}
  if estimate is None or estimate["project"].get_id() != project.get_id():
    return {"ok": False, "message": "Сначала сохраните смету для этого проекта."}
  if not isinstance(terms, str) or len(terms) > 2000:
    return {"ok": False, "message": "Проверьте условия коммерческого предложения."}
  now = datetime.now(timezone.utc)
  number = "HV-{}-{}".format(now.strftime("%Y%m%d"), uuid.uuid4().hex[:6].upper())
  quote = app_tables.quotes.add_row(
    project=project,
    client=project["client"],
    estimate=estimate,
    number=number,
    status="draft",
    terms=terms.strip(),
    total=estimate["total"],
    currency=estimate["currency"],
    estimate_version=estimate["version"],
    created_at=now,
    updated_at=now
  )
  project.update(status="quoted", updated_at=now)
  Core.log_audit(
    actor=user,
    action="quote.created",
    entity_type="quote",
    entity_id=quote.get_id(),
    details={"number": number, "total": quote["total"], "currency": quote["currency"]},
    created_at=now
  )
  return {"ok": True, "quote_id": quote.get_id(), "number": number}


def create_catalog_quote(project, user, selections, terms="", details=None,
                         require_installation=False, require_work=False,
                         extra_work_lines=None):
  if user is None or not Core.can_access_project(project, user):
    return {"ok": False, "message": "КП доступно только владельцу проекта."}
  priced = price_catalog_selections(selections, require_installation)
  if not priced["ok"]:
    return priced
  for line in extra_work_lines or []:
    if not isinstance(line, dict):
      return {"ok": False, "message": "Проверьте позиции работ для сметы."}
    quantity, error = _positive_amount(line.get("quantity"), "работы")
    if error:
      return {"ok": False, "message": error}
    if quantity is None:
      return {"ok": False, "message": "Проверьте количество работ."}
    unit_price = line.get("unit_price")
    if isinstance(unit_price, bool) or not isinstance(unit_price, (int, float)):
      return {"ok": False, "message": "Проверьте цену работ."}
    if not math.isfinite(float(unit_price)) or unit_price < 0:
      return {"ok": False, "message": "Проверьте цену работ."}
    line_total = round(quantity * float(unit_price), 2)
    priced["lines"].append({
      "product": None,
      "description": str(line.get("description") or "Работы"),
      "quantity": quantity,
      "unit": str(line.get("unit") or ""),
      "unit_price": float(unit_price),
      "currency": priced["currency"],
      "line_total": line_total,
      "source": str(line.get("source") or "installation_formula"),
      "group": "works",
      "snapshot": dict(line.get("snapshot") or {})
    })
    priced["labor_cost"] = round(priced["labor_cost"] + line_total, 2)
  if require_work and priced["labor_cost"] <= 0:
    return {
      "ok": False,
      "message": "Для КП с монтажом задайте цену работ в формуле монтажа или в карточке оборудования."
    }
  saved = save_estimate(project, user, priced, details)
  if not saved["ok"]:
    return saved
  estimate = app_tables.estimates.get_by_id(saved["estimate_id"])
  quote = create_quote(project, estimate, user, terms)
  if not quote["ok"]:
    return quote
  return {
    "ok": True,
    "estimate_id": saved["estimate_id"],
    "estimate_version": saved["version"],
    "quote_id": quote["quote_id"],
    "quote_number": quote["number"],
    "total": saved["total"],
    "currency": saved["currency"],
    "materials_cost": saved["materials_cost"],
    "labor_cost": saved["labor_cost"],
    "missing_installation": priced["missing_installation"],
    "message": "Смета и коммерческое предложение созданы."
  }
