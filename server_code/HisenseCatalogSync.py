"""Sync the complete Hisense catalog snapshot from the Lovable project into Anvil."""

from datetime import datetime, timezone
import math
import re
import uuid

import anvil
import anvil.server
from anvil.tables import app_tables, order_by, query as q

import Core
from HisenseLovableCatalogData import CATALOG_PARTS


SYNC_STATE_KEY = "hisense_lovable_catalog_sync_v1"
CATALOG_VERSION = "2026-09-15"

PHOTO_URLS = {
  "sensation": "https://images.breez.ru/catalog/hisense/sensation-slider-pro-superior-dc-inverter/sensation-slider-pro-superior-dc-inverter-01.png",
  "sensation-carbon": "https://images.breez.ru/catalog/hisense/sensation-slider-pro-carbon-superior-dc-inverter/sensation-slider-pro-carbon-superior-dc-inverter-01.png",
  "vision": "https://images.breez.ru/catalog/hisense/vision-pro-2-0-superior-dc-inverter/vision-pro-2-0-superior-dc-inverter-01.png",
  "vision-carbon": "https://images.breez.ru/catalog/hisense/vision-pro-2-0-carbon-superior-dc-inverter/vision-pro-2-0-carbon-superior-dc-inverter-01.png",
  "vibe": "https://images.breez.ru/catalog/hisense/vibe-dc-inverter/vibe-dc-inverter-01.png",
  "vibe-pro-carbon": "https://images.breez.ru/catalog/hisense/vibe-pro-carbon-eu-dc-inverter/vibe-pro-carbon-eu-dc-inverter-01.png",
  "vibe-pro-silver": "https://images.breez.ru/catalog/hisense/vibe-pro-silver-eu-dc-inverter/vibe-pro-silver-eu-dc-inverter-01.png",
  "vibe-pro-champagne": "https://images.breez.ru/catalog/hisense/vibe-pro-champagne-eu-dc-inverter/vibe-pro-champagne-eu-dc-inverter-01.png",
  "strong-vibe": "https://images.breez.ru/catalog/hisense/classic-strong-vibe-a/classic-strong-vibe-a-05.png",
  "expert": "https://images.breez.ru/catalog/hisense/expert-pro-2-0-eu-dc-inverter/expert-pro-2-0-eu-dc-inverter-01.png",
  "goal": "https://images.breez.ru/catalog/hisense/split-system-goal-2-0-dc-inverter-wi-fi/split-system-goal-2-0-dc-inverter-wi-fi-01.png",
  "goal-classic": "https://images.breez.ru/catalog/hisense/split-system-goal-2-0-classic-a-wi-fi/split-system-goal-2-0-classic-a-wi-fi-01.png",
  "city": "https://images.breez.ru/catalog/hisense/classic-split-system-city-a/classic-split-system-city-a-01.png",
  "city-2": "https://images.breez.ru/catalog/hisense/classic-split-system-city-a/classic-split-system-city-a-01.png",
  "zoom": "https://images.breez.ru/catalog/hisense/zoom-2-0-dc-inverter/zoom-2-0-dc-inverter-01.png",
  "zoom-classic": "https://images.breez.ru/catalog/hisense/zoom-2-0-classic-a/zoom-2-0-classic-a-01.png",
  "cassette": "https://images.breez.ru/catalog/hisense/split-sistem-kasset-heavy-eu-dc-inverter/split-sistem-kasset-heavy-eu-dc-inverter-01.png",
  "duct": "https://images.breez.ru/catalog/hisense/split-sistem-kanal-heavy-eu-dc-inverter-r32/split-sistem-kanal-heavy-eu-dc-inverter-r32-01.png",
  "floor": "https://images.breez.ru/catalog/hisense/split-sistem-pol-potolok-heavy-eu-dc-inverter-r32/split-sistem-pol-potolok-heavy-eu-dc-inverter-r32-01.png",
  "column": "https://images.breez.ru/catalog/hisense/kolonnie-vn-bloky-vrf/kolonnie-vn-bloky-vrf-01.png",
  "console": "https://images.breez.ru/catalog/hisense/split-sistem-konsol-eu-dc-inverter-r32/split-sistem-konsol-eu-dc-inverter-r32-01.png",
  "multi-outdoor": "https://images.breez.ru/catalog/hisense/outdoor-multi-eu-dc-inverter/outdoor-multi-eu-dc-inverter-01.png",
  "multi-sensation": "https://images.breez.ru/catalog/hisense/sensation-pro-2-0-multi-superior-dc-inverter/sensation-pro-2-0-multi-superior-dc-inverter-01.png",
  "multi-sensation-carbon": "https://images.breez.ru/catalog/hisense/sensation-pro-carbon-multi-superior-dc-inverter/sensation-pro-carbon-multi-superior-dc-inverter-01.png",
  "multi-vision": "https://images.breez.ru/catalog/hisense/vision-pro-2-0-superior-dc-inverter/vision-pro-2-0-superior-dc-inverter-01.png",
  "multi-vision-carbon": "https://images.breez.ru/catalog/hisense/vision-pro-2-0-carbon-multi-superior-dc-inverter/vision-pro-2-0-carbon-multi-superior-dc-inverter-01.png",
  "multi-vibe-pro": "https://images.breez.ru/catalog/hisense/vibe-pro-multi-eu-dc-inverter/vibe-pro-multi-eu-dc-inverter-01.png",
  "multi-vibe-pro-carbon": "https://images.breez.ru/catalog/hisense/vibe-pro-carbon-multi-eu-dc-inverter/vibe-pro-carbon-multi-eu-dc-inverter-01.png",
  "multi-vibe-pro-silver": "https://images.breez.ru/catalog/hisense/vibe-pro-silver-multi-eu-dc-inverter/vibe-pro-silver-multi-eu-dc-inverter-01.png",
  "multi-vibe-pro-champagne": "https://images.breez.ru/catalog/hisense/vibe-pro-champagne-multi-eu-dc-inverter/vibe-pro-champagne-multi-eu-dc-inverter-01.png",
  "multi-zoom": "https://images.breez.ru/catalog/hisense/zoom-dc-inverter-wi-fi/zoom-dc-inverter-wi-fi-01.png",
  "multi-premium-black": "https://images.breez.ru/catalog/hisense/vn-bl-premium-black-free-match-dc-2023/vn-bl-premium-black-free-match-dc-2023-01.png",
  "multi-console": "https://images.breez.ru/catalog/hisense/split-sistem-konsol-eu-dc-inverter-r32/split-sistem-konsol-eu-dc-inverter-r32-01.png",
  "multi-duct": "https://images.breez.ru/catalog/hisense/split-sistem-kanal-heavy-eu-dc-inverter-r32/split-sistem-kanal-heavy-eu-dc-inverter-r32-01.png",
  "multi-cassette": "https://images.breez.ru/catalog/hisense/hi-invert-split-sistemi-kassetnogo-tipa/hi-invert-split-sistemi-kassetnogo-tipa-01.png",
  "multi-floor": "https://images.breez.ru/catalog/hisense/split-sistem-pol-potolok-heavy-eu-dc-inverter-r32/split-sistem-pol-potolok-heavy-eu-dc-inverter-r32-01.png",
  "mobileV": "https://images.breez.ru/catalog/hisense/mob-cond-v/mob-cond-v-01.png",
  "mobileW": "https://images.breez.ru/catalog/hisense/mob-cond-w/mob-cond-w-01.png",
  "mobileC": "https://images.breez.ru/catalog/hisense/mob-cond-c/mob-cond-c-01.png",
  "dehumidifier": "https://images.breez.ru/catalog/hisense/osushit-vozd-air-go-pro/osushit-vozd-air-go-pro-01.png",
  "accessory": "https://images.breez.ru/catalog/hisense/accessories/accessories-01.png",
}

IMAGE_SOURCE = "GitHub · synced from Lovable Hisense catalog"
CDN_IMAGE_SOURCE = "Lovable Hisense catalog · external catalog CDN"

GITHUB_PHOTO_BASE = "https://raw.githubusercontent.com/klimatst/anviklimat/master/theme/assets/catalog/hisense"
SOURCE_URL = "https://github.com/klimatst/anviklimat/blob/master/server_code/HisenseLovableCatalogData.py"


def _safe_float(value):
  if value is None or not str(value).strip():
    return 0.0
  try:
    number = float(str(value).strip().replace(",", "."))
  except (TypeError, ValueError, OverflowError):
    return 0.0
  return number if math.isfinite(number) else 0.0


def _slug(value):
  raw = str(value or "").strip().casefold()
  raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
  return raw or ("item-" + uuid.uuid4().hex[:10])


def _normalize_series(model, raw_series):
  value = (model or "").upper()
  series = (raw_series or "").strip()
  if series and not re.match(r"^(СПЛИТ-СИСТЕМЫ|СПЕЦИАЛЬНАЯ СЕРИЯ|КОНДИЦИОНЕРЫ)", series):
    return series
  rules = (
    ("RWMQK00", lambda: "SENSATION SLIDER PRO CARBON SUPERIOR DC Inverter 2026 Wi-Fi" if "(B)" in value else "SENSATION SLIDER PRO SUPERIOR DC Inverter 2026 Wi-Fi"),
    ("RXVQH", lambda: "VISION PRO 2.0 CARBON SUPERIOR DC Inverter 2026 Wi-Fi" if "(B)" in value else "VISION PRO 2.0 SUPERIOR DC Inverter 2026 Wi-Fi"),
    ("RBVQH", lambda: "VISION PRO 2.0 CARBON SUPERIOR DC Inverter 2026 Wi-Fi" if "(B)" in value else "VISION PRO 2.0 SUPERIOR DC Inverter 2026 Wi-Fi"),
    ("RLCHB", lambda: "VIBE PRO CARBON EU DC Inverter"),
    ("RXPHB", lambda: "VIBE PRO CARBON EU DC Inverter"),
    ("RFWHB", lambda: "VIBE PRO CARBON EU DC Inverter"),
    ("RLCHD", lambda: "VIBE PRO SILVER EU DC Inverter" if "(S)" in value else ("VIBE PRO CHAMPAGNE EU DC Inverter" if "(C)" in value else "VIBE PRO EU DC Inverter")),
    ("RLCHC", lambda: "EXPERT PRO 2.0 EU DC Inverter"),
    ("RXPHC", lambda: "EXPERT PRO 2.0 EU DC Inverter"),
    ("RFWHC", lambda: "EXPERT PRO 2.0 EU DC Inverter"),
    ("RKZHB", lambda: "STRONG VIBE Classic A"),
    ("RYRHB", lambda: "VIBE DC Inverter"),
    ("RMSHB", lambda: "VIBE DC Inverter"),
    ("RBTHB", lambda: "VIBE DC Inverter"),
    ("RYRKJ", lambda: "GOAL 2.0 DC Inverter"),
    ("RMSKJ", lambda: "GOAL 2.0 DC Inverter" if value.startswith(("AS-18UW", "AS-24UW")) else "GOAL 2.0 Classic A"),
    ("RBTKJ", lambda: "GOAL 2.0 DC Inverter" if value.startswith(("AS-18UW", "AS-24UW")) else "GOAL 2.0 Classic A"),
    ("RYRKA", lambda: "CITY 2.0 DC Inverter"),
    ("RMSKA", lambda: "CITY 2.0 DC Inverter"),
    ("RBTKA", lambda: "CITY 2.0 DC Inverter"),
    ("RYRKB", lambda: "ZOOM 2.0 DC Inverter"),
    ("RMSKB", lambda: "ZOOM 2.0 Classic A"),
    ("RBTKB", lambda: "ZOOM 2.0 Classic A"),
    ("RLRKJ", lambda: "GOAL 2.0 Classic A"),
    ("RLRKA", lambda: "CITY 2.0 Classic A"),
    ("RLRKB", lambda: "ZOOM 2.0 Classic A"),
  )
  for token, factory in rules:
    if token in value:
      return factory()
  return series or "Hisense climate equipment"


def _photo_key(model, series, category, imported_key):
  value = (model or "").upper()
  series_value = (series or "").upper()
  if "RWMQK00" in value:
    return "sensation-carbon" if "(B)" in value else "sensation"
  if "RXVQH" in value or "RBVQH" in value:
    return "vision-carbon" if "(B)" in value else "vision"
  if category == "dehumidifier":
    return "dehumidifier"
  if category == "accessory":
    return "accessory"
  if category == "mobile":
    imported = (imported_key or "").casefold()
    if "mobile-v" in imported:
      return "mobileV"
    if "mobile-w" in imported:
      return "mobileW"
    if "mobile-c" in imported:
      return "mobileC"
    return "mobileC"
  if category == "multi-split":
    if "НАРУЖНЫЕ БЛОКИ" in series_value:
      return "multi-outdoor"
    for key, marker in (
      ("multi-sensation-carbon", ("SENSATION", "CARBON")),
      ("multi-sensation", ("SENSATION",)),
      ("multi-vision-carbon", ("VISION", "CARBON")),
      ("multi-vision", ("VISION",)),
      ("multi-vibe-pro-silver", ("VIBE PRO SILVER",)),
      ("multi-vibe-pro-champagne", ("VIBE PRO CHAMPAGNE",)),
      ("multi-vibe-pro-carbon", ("VIBE PRO CARBON",)),
      ("multi-vibe-pro", ("VIBE PRO",)),
      ("multi-zoom", ("ZOOM",)),
      ("multi-premium-black", ("PREMIUM BLACK",)),
      ("multi-console", ("КОНСОЛ",)),
      ("multi-duct", ("КАНАЛ",)),
      ("multi-cassette", ("КАССЕТ",)),
      ("multi-floor", ("НАПОЛЬНО-ПОТОЛОЧ",)),
    ):
      if all(marker in series_value for marker in marker):
        return key
  for token, key in (
    ("RLCHB", "vibe-pro-carbon"), ("RXPHB", "vibe-pro-carbon"), ("RFWHB", "vibe-pro-carbon"),
    ("RLCHD", "vibe-pro-silver"), ("RLCHC", "expert"), ("RXPHC", "expert"), ("RFWHC", "expert"),
    ("RKZHB", "strong-vibe"), ("RYRHB", "vibe"), ("RMSHB", "vibe"), ("RBTHB", "vibe"),
    ("RYRKJ", "goal"), ("RMSKJ", "goal"), ("RBTKJ", "goal"),
    ("RYRKA", "city"), ("RMSKA", "city"), ("RBTKA", "city"),
    ("RYRKB", "zoom"), ("RMSKB", "zoom"), ("RBTKB", "zoom"),
    ("RLRKJ", "goal-classic"), ("RLRKA", "city"), ("RLRKB", "zoom-classic"),
  ):
    if token in value:
      return key
  for marker, key in (
    ("КАНАЛ", "duct"), ("КАССЕТ", "cassette"), ("НАПОЛЬНО-ПОТОЛОЧ", "floor"),
    ("КОЛОН", "column"), ("КОНСОЛ", "console"), ("SENSATION", "sensation"),
    ("VISION", "vision"), ("STRONG VIBE", "strong-vibe"), ("VIBE PRO CARBON", "vibe-pro-carbon"),
    ("VIBE PRO SILVER", "vibe-pro-silver"), ("VIBE PRO CHAMPAGNE", "vibe-pro-champagne"),
    ("VIBE PRO", "vibe-pro-carbon"), ("VIBE", "vibe"), ("EXPERT", "expert"),
    ("GOAL", "goal"), ("CITY", "city"), ("ZOOM", "zoom"),
  ):
    if marker in series_value:
      return key
  return imported_key if imported_key in PHOTO_URLS else "vibe"


def _catalog():
  import CatalogService as Catalog
  return Catalog


def _category_target(category, series):
  series_value = (series or "").upper()
  if category == "split":
    return "air-conditioning", "air-conditioning-split-systems"
  if category == "multi-split":
    return (
      "multi-split-systems",
      "multi-split-systems-outdoor-blocks"
      if "НАРУЖНЫЕ" in series_value else "multi-split-systems-indoor-blocks"
    )
  if category == "lcac":
    key = (
      "duct-type" if "КАНАЛ" in series_value else
      "cassette-type" if "КАССЕТ" in series_value else
      "floor-ceiling" if "НАПОЛЬНО-ПОТОЛОЧ" in series_value else
      "console-type" if "КОНСОЛ" in series_value else
      "column-type" if "КОЛОН" in series_value else
      "cassette-type"
    )
    return "semi-industrial", "semi-industrial-" + key
  if category == "mobile":
    return "air-conditioning", "air-conditioning-portable"
  if category == "dehumidifier":
    return "dehumidification", None
  return "accessories-options", None


def _unit_type(series, category):
  value = (series or "").upper()
  if category == "mobile":
    return "Мобильный кондиционер"
  if category == "dehumidifier":
    return "Осушитель"
  if category == "accessory":
    return "Аксессуар"
  if category == "multi-split":
    if "НАРУЖНЫЕ" in value:
      return "Наружный блок multi"
    if "КАНАЛ" in value:
      return "Внутренний канальный блок"
    if "КАССЕТ" in value:
      return "Внутренний кассетный блок"
    if "НАПОЛЬНО-ПОТОЛОЧ" in value:
      return "Внутренний напольно-потолочный блок"
    if "КОНСОЛ" in value:
      return "Внутренний консольный блок"
    return "Внутренний настенный блок"
  if category == "lcac":
    if "КАНАЛ" in value:
      return "Канальный"
    if "КАССЕТ" in value:
      return "Кассетный"
    if "НАПОЛЬНО-ПОТОЛОЧ" in value:
      return "Напольно-потолочный"
    if "КОЛОН" in value:
      return "Колонный"
    if "КОНСОЛ" in value:
      return "Консольный"
    return "Полупромышленный"
  return "Настенная сплит-система"


def _category_description(category):
  return {
    "split": "Сплит-система Hisense для бытового применения.",
    "multi-split": "Компонент системы Hisense Free Match / Multi: внутренний или наружный блок.",
    "lcac": "Полупромышленная сплит-система Hisense для офисных и коммерческих помещений.",
    "mobile": "Мобильный кондиционер Hisense без стационарной трассы.",
    "dehumidifier": "Осушитель воздуха Hisense для управления влажностью.",
    "accessory": "Аксессуар для монтажа, управления или обслуживания климатического оборудования."
  }.get(category, "Климатическое оборудование Hisense.")


def _parse_rows():
  rows = []
  for raw in CATALOG_PARTS:
    for line in raw.splitlines():
      line = line.strip()
      if not line:
        continue
      parts = line.split("|")
      if len(parts) < 13:
        continue
      tail = parts[-12:]
      model = "|".join(parts[:-12]).strip()
      price, cool, heat, energy, noise, indoor_dim, outdoor_dim, weight, series_raw, ns_code, category, imported_key = tail
      if not model:
        continue
      category = category if category in {"split", "multi-split", "lcac", "mobile", "dehumidifier", "accessory"} else "split"
      series = _normalize_series(model, series_raw)
      photo_key = _photo_key(model, series, category, imported_key)
      photo_url = PHOTO_URLS.get(photo_key, "")
      rows.append({
        "model": model, "price": _safe_float(price), "cool": _safe_float(cool),
        "heat": _safe_float(heat), "energy": energy or "", "noise": noise or "",
        "indoor_dim": indoor_dim or "", "outdoor_dim": outdoor_dim or "",
        "weight": weight or "", "series": series, "ns_code": ns_code or "",
        "category": category, "photo_key": photo_key,
        "photo_url": (GITHUB_PHOTO_BASE + "/" + photo_key + ".png") if photo_key else "",
        "photo_fallback_url": photo_url
      })
  return rows


def _ensure_child(parent, code, title):
  existing = next((row for row in app_tables.catalog_categories.search() if row["code"] == code), None)
  if existing is not None:
    return existing
  return app_tables.catalog_categories.add_row(
    code=code, title=title, parent=parent, active=True,
    sort_order=(parent["sort_order"] or 0) + 50, description=""
  )


def _ensure_target_categories():
  _catalog()._ensure_categories()
  roots = {row["code"]: row for row in app_tables.catalog_categories.search()}
  targets = {}
  mapping = {
    ("air-conditioning", "air-conditioning-split-systems"): "Инверторные сплит-системы Hisense",
    ("air-conditioning", "air-conditioning-portable"): "Мобильные кондиционеры Hisense",
    ("multi-split-systems", "multi-split-systems-outdoor-blocks"): "Наружные блоки Hisense Multi",
    ("multi-split-systems", "multi-split-systems-indoor-blocks"): "Внутренние блоки Hisense Multi",
    ("semi-industrial", "semi-industrial-duct-type"): "Канальные системы Hisense",
    ("semi-industrial", "semi-industrial-cassette-type"): "Кассетные системы Hisense",
    ("semi-industrial", "semi-industrial-floor-ceiling"): "Напольно-потолочные системы Hisense",
    ("semi-industrial", "semi-industrial-console-type"): "Консольные системы Hisense",
    ("semi-industrial", "semi-industrial-column-type"): "Колонные системы Hisense",
  }
  for (root_code, child_code), title in mapping.items():
    root = roots.get(root_code)
    if root is not None:
      targets[child_code] = _ensure_child(root, child_code, title)
  return roots, targets


def _ensure_series(category, title, min_power, max_power):
  key = (category.get_id(), title.casefold())
  existing = next((
    row for row in app_tables.catalog_series.search(category=category)
    if (row["title"] or "").casefold() == key[1]
  ), None)
  power_range = (
    "{:.2f}–{:.2f} кВт".format(min_power, max_power)
    if max_power > 0 else ""
  )
  if existing is not None:
    existing.update(
      description="Серия Hisense из каталога Lovable. Цены и характеристики синхронизированы с источником.",
      power_range=power_range,
      is_new=("2026" in title.upper() or "NEW" in title.upper()),
      active=True, status="active", updated_at=datetime.now(timezone.utc)
    )
    return existing, False
  return app_tables.catalog_series.add_row(
    code="hisense-" + _slug(title) + "-" + uuid.uuid4().hex[:8],
    title=title, category=category,
    description="Серия Hisense из каталога Lovable. Цены и характеристики синхронизированы с источником.",
    status="active",
    is_new=("2026" in title.upper() or "NEW" in title.upper()),
    power_range=power_range,
    image=None, sort_order=0, active=True,
    created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)
  ), True


def _find_product(model, sku):
  identity = _catalog().product_identity_key("Hisense", model, sku)
  product = app_tables.products.get(identity_key=identity)
  if product is None and sku:
    product = app_tables.products.get(sku_key=sku.casefold())
  return product


def _upsert_spec(product, key, value, unit, order):
  if value in (None, ""):
    return
  existing = next((
    row for row in app_tables.product_specs.search(product=product)
    if (row["key_key"] or "").casefold() == key.casefold()
  ), None)
  values = {
    "key": key, "key_key": key.casefold(), "value": str(value)[:200],
    "unit": unit[:32], "source": "Lovable catalog",
    "sort_order": order, "visible": True,
    "updated_at": datetime.now(timezone.utc)
  }
  if existing is None:
    app_tables.product_specs.add_row(product=product, **values)
  else:
    existing.update(**values)


def _upsert_photo(product, url, model, photo_key):
  if not url:
    return
  existing = next((
    row for row in app_tables.product_media.search(product=product)
    if (row["url"] or "") == url
  ), None)
  primary_rows = list(app_tables.product_media.search(product=product, type="primary"))
  if existing is not None:
    existing.update(
      source=IMAGE_SOURCE, type="primary", is_primary=True,
      alt_text="Hisense " + model, checksum=""
    )
    for row in primary_rows:
      if row.get_id() != existing.get_id() and row["is_primary"]:
        row.update(is_primary=False)
    return
  if primary_rows and not isinstance(primary_rows[0]["file"], anvil.Media):
    row = primary_rows[0]
    row.update(
      url=url, source=IMAGE_SOURCE, type="primary", is_primary=True,
      alt_text="Hisense " + model, checksum=""
    )
  else:
    if next((row for row in primary_rows if (row["url"] or "") == url), None):
      return
    for row in app_tables.product_media.search(product=product):
      if row["is_primary"]:
        row.update(is_primary=False)
    app_tables.product_media.add_row(
      product=product, file_id="", file=None, url=url,
      source=IMAGE_SOURCE, type="primary",
      alt_text="Hisense " + model, is_primary=True,
      sort_order=0, created_at=datetime.now(timezone.utc), checksum=""
    )


def _write_sync_state(total, created, updated, series_created):
  state = {
    "version": CATALOG_VERSION, "total": total, "created": created,
    "updated": updated, "series_created": series_created,
    "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "source": SOURCE_URL
  }
  row = app_tables.system_settings.get(key=SYNC_STATE_KEY)
  if row is None:
    app_tables.system_settings.add_row(
      key=SYNC_STATE_KEY, value=state,
      updated_at=datetime.now(timezone.utc), updated_by=Core.get_admin_user()
    )
  else:
    row.update(
      value=state, updated_at=datetime.now(timezone.utc),
      updated_by=Core.get_admin_user()
    )
  return state


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_hisense_lovable_sync_status():
  Core.require_admin_user()
  row = app_tables.system_settings.get(key=SYNC_STATE_KEY)
  return {"ok": True, "state": row["value"] if row is not None and isinstance(row["value"], dict) else None}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def sync_hisense_lovable_catalog(force=False):
  actor = Core.require_admin_user()
  if not isinstance(force, bool):
    return {"ok": False, "message": "Некорректный режим синхронизации."}
  existing_state = app_tables.system_settings.get(key=SYNC_STATE_KEY)
  if (
    not force and existing_state is not None and
    isinstance(existing_state["value"], dict) and
    existing_state["value"].get("version") == CATALOG_VERSION
  ):
    state = existing_state["value"]
    return {
      "ok": True, "created": state.get("created", 0),
      "updated": state.get("updated", 0), "series_created": state.get("series_created", 0),
      "total": state.get("total", 0),
      "message": "Каталог Hisense уже синхронизирован ({})".format(CATALOG_VERSION)
    }

  roots, target_categories = _ensure_target_categories()
  rows = _parse_rows()
  if not rows:
    return {"ok": False, "message": "Источник каталога Lovable пуст или повреждён."}

  brand = app_tables.brands.get(name_key="hisense")
  if brand is None:
    brand = app_tables.brands.add_row(name="Hisense", name_key="hisense")

  series_stats = {}
  for row in rows:
    root_code, child_code = _category_target(row["category"], row["series"])
    category = roots.get(root_code)
    subcategory = target_categories.get(child_code)
    if category is None:
      continue
    key = (subcategory or category).get_id()
    stat = series_stats.setdefault((key, row["series"]), {"min": 0.0, "max": 0.0})
    if row["cool"] > 0:
      stat["min"] = row["cool"] if stat["min"] <= 0 else min(stat["min"], row["cool"])
      stat["max"] = max(stat["max"], row["cool"])

  series_map = {}
  series_created = 0
  for (category_id, title), stat in series_stats.items():
    category = app_tables.catalog_categories.get_by_id(category_id)
    series, was_created = _ensure_series(category, title, stat["min"], stat["max"])
    series_created += 1 if was_created else 0
    series_map[(category_id, title.casefold())] = series

  created = updated = 0
  now = datetime.now(timezone.utc)
  for row in rows:
    root_code, child_code = _category_target(row["category"], row["series"])
    category = roots.get(root_code)
    subcategory = target_categories.get(child_code)
    if category is None:
      continue
    assigned_category = subcategory or category
    series = series_map.get((assigned_category.get_id(), row["series"].casefold()))
    product = _find_product(row["model"], row["ns_code"])
    is_new = product is None
    full_description = (
      "{} Серия: {}. Тип: {}. "
      "Охлаждение: {} кВт; обогрев: {} кВт; энергоэффективность: {}; "
      "шум: {} дБ; внутренний блок: {}; наружный блок: {}; вес: {} кг. "
      "НС-код: {}. Прайс-лист: {}."
    ).format(
      _category_description(row["category"]), row["series"],
      _unit_type(row["series"], row["category"]),
      row["cool"] or "—", row["heat"] or "—", row["energy"] or "—",
      row["noise"] or "—", row["indoor_dim"] or "—",
      row["outdoor_dim"] or "—", row["weight"] or "—",
      row["ns_code"] or "—", CATALOG_VERSION
    )[:2000]

    if product is None:
      product = app_tables.products.add_row(
        identity_key=Catalog.product_identity_key("Hisense", row["model"], row["ns_code"]),
        brand=brand, model=row["model"], sku=row["ns_code"],
        sku_key=(row["ns_code"] or "").casefold(),
        category=category, subcategory=subcategory, series=series,
        type=_unit_type(row["series"], row["category"]),
        description=full_description,
        active=True, created_at=now, updated_at=now
      )
    else:
      product.update(
        brand=brand, model=row["model"], sku=row["ns_code"],
        sku_key=(row["ns_code"] or "").casefold(),
        category=category, subcategory=subcategory, series=series,
        type=_unit_type(row["series"], row["category"]),
        description=full_description,
        active=True, updated_at=now
      )

    price = app_tables.product_prices.get(product=product)
    if price is None:
      app_tables.product_prices.add_row(
        product=product, sale_price=row["price"], currency="RUB", updated_at=now
      )
    else:
      price.update(sale_price=row["price"], currency="RUB", updated_at=now)

    _upsert_spec(product, "Мощность охлаждения", row["cool"], "кВт", 10)
    _upsert_spec(product, "Мощность обогрева", row["heat"], "кВт", 20)
    _upsert_spec(product, "Энергоэффективность", row["energy"], "", 30)
    _upsert_spec(product, "Шум", row["noise"], "дБ", 40)
    _upsert_spec(product, "Габариты внутреннего блока", row["indoor_dim"], "мм", 50)
    _upsert_spec(product, "Габариты наружного блока", row["outdoor_dim"], "мм", 60)
    _upsert_spec(product, "Вес", row["weight"], "кг", 70)
    _upsert_spec(product, "Серия", row["series"], "", 80)
    _upsert_spec(product, "НС-код", row["ns_code"], "", 90)
    _upsert_spec(product, "Тип оборудования", _unit_type(row["series"], row["category"]), "", 100)
    _upsert_spec(product, "Категория Lovable", row["category"], "", 110)
    _upsert_spec(product, "Фото", row["photo_url"], "", 120)
    _upsert_spec(product, "Резервная ссылка фото", row.get("photo_fallback_url", ""), "", 125)
    _upsert_spec(product, "Источник фото", IMAGE_SOURCE, "", 130)
    _upsert_photo(product, row["photo_url"], row["model"], row["photo_key"])
    source = next(iter(app_tables.product_sources.search(product=product)), None)
    source_values = {
      "url": SOURCE_URL, "publisher": "Lovable · Hisense catalog",
      "version": CATALOG_VERSION, "checked_at": now
    }
    if source is None:
      app_tables.product_sources.add_row(product=product, **source_values)
    else:
      source.update(**source_values)
    if is_new:
      created += 1
    else:
      updated += 1

  state = _write_sync_state(len(rows), created, updated, series_created)
  Core.log_audit(
    actor=actor, action="catalog.hisense_lovable_sync",
    entity_type="catalog", entity_id=SYNC_STATE_KEY,
    details={"version": CATALOG_VERSION, "total": len(rows), "created": created, "updated": updated},
    created_at=now
  )
  return {
    "ok": True, "total": len(rows), "created": created,
    "updated": updated, "series_created": series_created,
    "message": "Hisense синхронизирован из Lovable: {} позиций, новых {}, обновлено {}.".format(
      len(rows), created, updated
    )
  }
