import anvil.server
"""Shared report formatting and export actions for engineering calculators."""

from anvil import BlobMedia
import anvil.js
import anvil.media
from urllib.parse import quote


def _number_line(label, value, unit=""):
  if value is None:
    return None
  suffix = " {}".format(unit) if unit else ""
  return "{}: {}{}".format(label, value, suffix)


def calculation_report(result):
  if not isinstance(result, dict) or not result.get("ok"):
    return "Расчёт пока не готов."
  lines = [
    "ЭКО-КЛИМАТ",
    result.get("profile_title", "Инженерный расчёт"),
    ""
  ]
  inputs = result.get("inputs", {})
  labels = (
    ("area_m2", "Площадь", "м²"), ("height_m", "Высота", "м"),
    ("people_count", "Люди", "чел."), ("equipment_kw", "Тепловыделение", "кВт"),
    ("indoor_unit_count", "Внутренние блоки", "шт."),
    ("route_length_m", "Холодильная трасса", "м"),
    ("height_difference_m", "Перепад высот", "м"),
    ("airflow_m3_h", "Расход воздуха", "м³/ч")
  )
  lines.append("Исходные параметры")
  for key, label, unit in labels:
    line = _number_line(label, inputs.get(key), unit)
    if line:
      lines.append(line)
  lines.extend(["", "Результат: {} {}".format(result.get("result", result.get("design_value", "—")), result.get("result_unit", result.get("design_unit", ""))).strip()])
  lines.append("Состав расчёта")
  for item in result.get("components", []):
    lines.append("• {}: {} {}".format(item.get("label", "Параметр"), item.get("value", "—"), item.get("unit", "")))
  equipment = result.get("selected_product") or result.get("equipment")
  if equipment:
    lines.extend(["", "Оборудование из каталога", "{} {} · {} {}".format(
      equipment.get("brand", ""), equipment.get("model", ""),
      equipment.get("capacity", ""), equipment.get("capacity_unit", "")
    ).strip()])
  currency = result.get("currency", "RUB")
  customer_lines = result.get("customer_lines", [])
  if customer_lines:
    lines.extend(["", "Стоимость для заказчика"])
    for row in customer_lines:
      amount = row.get("amount")
      lines.append("{} — {} {}".format(
        row.get("description", "Позиция"),
        amount if amount is not None else "не рассчитано",
        currency
      ))
  else:
    for key, heading in (("work_lines", "Работы"), ("material_lines", "Материалы"), ("equipment_lines", "Оборудование")):
      rows = result.get(key, [])
      if rows:
        lines.extend(["", heading])
        for row in rows:
          amount = row.get("line_total")
          line_text = "{} — {} {} — {} {}".format(
            row.get("description", "Позиция"), row.get("quantity", "—"),
            row.get("unit", ""), amount if amount is not None else "цена не задана",
            currency if amount is not None else ""
          )
          if row.get("discount_amount"):
            line_text += " · скидка {}% / {} {}".format(
              row.get("discount_percent", 0), row["discount_amount"], currency
            )
          lines.append(line_text)
  if not customer_lines and result.get("catalog_discount_amount"):
    lines.append("Скидка каталога: {}% · {} {} (учтена в ценах выше)".format(
      result.get("catalog_discount_percent", 0),
      result["catalog_discount_amount"], currency
    ))
  if not customer_lines and result.get("additional_discount_amount"):
    lines.append("Дополнительная скидка: {}% · {} {}".format(
      result.get("additional_discount_percent", 0),
      result["additional_discount_amount"], currency
    ))
  if result.get("undiscounted_total") is not None:
    lines.extend(["", "До скидок: {} {}".format(result["undiscounted_total"], currency)])
  total = result.get("total")
  if total is not None:
    lines.extend(["", "Итого: {} {}".format(total, currency)])
  warnings = result.get("warnings", [])
  if warnings:
    lines.extend(["", "Допущения и замечания"])
    lines.extend("• " + str(item) for item in warnings)
  lines.extend(["", "Источник формул: {} · версия {}".format(result.get("source", ""), result.get("version", ""))])
  return "\n".join(lines)


def download_report(text, filename):
  media = BlobMedia("text/plain; charset=utf-8", text.encode("utf-8"), name=filename)
  anvil.media.download(media)


def open_telegram_share(title, text):
  message = "{}\n{}".format(title, text)
  url = "https://t.me/share/url?url=&text={}".format(quote(message[:3500], safe=""))
  anvil.js.window.open(url, "_blank", "noopener")
