import anvil.secrets
from datetime import datetime, timezone
import json
import re

import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import PricePagesService


PAGE_STATES = {"draft", "published"}
PAGE_STATE_TITLES = {"draft": "Черновик", "published": "Опубликована"}
MODULE_TYPES = [
  ("text", "Текст"), ("notice", "Уведомление"),
  ("link", "Ссылка"), ("media_reference", "Ссылка на файл"),
  ("contact", "Контакт"), ("form", "Форма"),
  ("hero", "Заглавный блок"), ("image", "Изображение"),
  ("button", "Кнопка"), ("html", "HTML-разметка")
]
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
MAX_MODULES = 100
NEWS_CATEGORY_CODES = {
  "company", "company_events", "company_projects", "equipment",
  "air_conditioning", "vrf_vrv", "ventilation", "guides", "selection",
  "operation", "maintenance"
}
REFERENCE_ARTICLES = (
  {
    "slug": "vybor-konditsionera-dlya-kvartiry",
    "title": "Как выбрать кондиционер для квартиры",
    "date": "01.01.2026",
    "category": "air_conditioning",
    "excerpt": "При выборе учитывают площадь комнаты, солнечную сторону, число людей и особенности планировки.",
    "text": "Начните с площади и назначения комнаты. Для спальни обычно важны низкий уровень шума и точная поддержка температуры; для гостиной — запас производительности и равномерное распределение воздуха. Инверторная модель плавно меняет мощность и помогает поддерживать стабильный комфорт. Перед покупкой проверьте длину трассы, место для наружного блока и условия монтажа."
  },
  {
    "slug": "obsluzhivanie-konditsionera",
    "title": "Когда проводить обслуживание кондиционера",
    "date": "01.01.2026",
    "category": "maintenance",
    "excerpt": "Плановое обслуживание помогает сохранять производительность и качество воздуха.",
    "text": "Перед началом сезона стоит проверить фильтры, теплообменники, дренаж и рабочие режимы. Загрязнение снижает теплообмен и может вызвать посторонний запах. Периодичность обслуживания зависит от интенсивности использования и условий помещения."
  },
  {
    "slug": "vrf-sistemy-dlya-biznesa",
    "title": "Климат для бизнеса: VRF-системы и фанкойлы",
    "date": "01.01.2026",
    "category": "vrf_vrv",
    "excerpt": "Рассказываем, когда стоит рассмотреть мультизональные системы и центральное кондиционирование.",
    "text": "Для офисов, гостиниц и торговых пространств важно поддерживать комфорт в разных зонах. VRF-системы позволяют подключать несколько внутренних блоков и гибко управлять климатом. Выбор оборудования лучше начинать с расчёта теплопритоков и проектирования инженерной системы."
  },
  {
    "slug": "demo-ventilyatsiya-dlya-ofisa",
    "title": "ДЕМО · Пример материала о вентиляции офиса",
    "date": "02.10.2026",
    "category": "ventilation",
    "excerpt": "Тестовая публикация для проверки рубрики «Вентиляция» и отображения статьи.",
    "text": "Демонстрационный материал: проект вентиляции начинается с оценки количества людей, режима работы помещений и требуемого воздухообмена. Этот текст создан для проверки навигации по рубрикам, списка публикаций и страницы статьи. Все данные тестовые."
  },
  {
    "slug": "demo-zapusk-inzhenernoy-sistemy",
    "title": "ДЕМО · Проверка новости о запуске объекта",
    "date": "02.10.2026",
    "category": "company_projects",
    "excerpt": "Временная новость для проверки рубрики проектов и CMS.",
    "text": "Демонстрационная новость о завершении монтажа и проверке климатической системы на объекте. Материал нужен только для тестирования CMS, списка новостей и переходов по категориям; название объекта и результаты работ не являются реальными."
  }
)


def _text(value, label, maximum, required=True):
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


def _decode_small_object(raw, label, maximum=4000):
  if isinstance(raw, dict):
    data = raw
  elif isinstance(raw, str) and len(raw) <= maximum:
    try:
      data = json.loads(raw or "{}")
    except json.JSONDecodeError:
      return None, "Проверьте JSON поля «{}».".format(label)
  else:
    return None, "Поле «{}» должно быть небольшим JSON-объектом.".format(label)
  if not isinstance(data, dict) or len(data) > 24:
    return None, "В поле «{}» допускается не более 24 параметров.".format(label)
  try:
    if len(json.dumps(data, ensure_ascii=False, allow_nan=False)) > maximum:
      return None, "Поле «{}» слишком большое.".format(label)
  except (TypeError, ValueError):
    return None, "Проверьте значения поля «{}».".format(label)
  for key, value in data.items():
    if not isinstance(key, str) or not key or len(key) > 64:
      return None, "Проверьте название параметра в поле «{}».".format(label)
    if value is not None and not isinstance(value, (str, int, float, bool)):
      return None, "CMS принимает короткие текстовые значения и числа."
    value_limit = 40000 if key == "html" else 2000
    if isinstance(value, str) and len(value) > value_limit:
      return None, "Текст модуля слишком длинный."
  return data, None


def _validate_page_settings(settings):
  limits = {
    "publish_date": 10, "excerpt": 600, "seo_title": 120,
    "seo_description": 320, "keywords": 250,
    "canonical_url": 300, "social_image_url": 500
  }
  for key, maximum in limits.items():
    value = settings.get(key)
    if value is None:
      continue
    if not isinstance(value, str):
      return None, "Проверьте поле «{}» в настройках страницы.".format(key)
    value = value.strip()
    if len(value) > maximum:
      return None, "Сократите поле «{}» до {} символов.".format(key, maximum)
    if key in ("canonical_url", "social_image_url") and value:
      if not value.casefold().startswith(("https://", "http://")):
        return None, "Для поля «{}» укажите полный HTTP(S)-адрес.".format(key)
    settings[key] = value
  publish_date = settings.get("publish_date", "")
  if publish_date:
    parsed = None
    for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
      try:
        parsed = datetime.strptime(publish_date, date_format)
        break
      except ValueError:
        continue
    if parsed is None:
      return None, "Введите дату публикации в формате ДД.ММ.ГГГГ."
    settings["publish_date"] = parsed.strftime("%d.%m.%Y")
  news_category = settings.get("news_category")
  if news_category is not None and (
    not isinstance(news_category, str)
    or news_category not in NEWS_CATEGORY_CODES
  ):
    return None, "Выберите рубрику новостей из списка."
  return settings, None


def _page_record(row):
  return {
    "id": row.get_id(), "slug": row["slug"], "title": row["title"],
    "status": row["status"],
    "status_title": PAGE_STATE_TITLES.get(row["status"], row["status"]),
    "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M UTC")
    if row["updated_at"] else ""
  }


def _module_record(row):
  return {
    "id": row.get_id(), "code": row["code"],
    "type_title": dict(MODULE_TYPES).get(row["code"], row["code"]),
    "position": row["position"], "content": row["content"] or {},
    "enabled": bool(row["enabled"]),
    "state_title": "Включён" if row["enabled"] else "Выключен"
  }


def _ensure_reference_articles():
  now = datetime.now(timezone.utc)
  created = []
  for article in REFERENCE_ARTICLES:
    page = app_tables.cms_pages.get(slug=article["slug"])
    if page is not None:
      settings = page["settings"] or {}
      if not settings.get("news_category"):
        settings["news_category"] = article["category"]
        page.update(settings=settings)
      continue
    page = app_tables.cms_pages.add_row(
      slug=article["slug"], title=article["title"], status="published",
      settings={
        "publish_date": article["date"], "excerpt": article["excerpt"],
        "news_category": article["category"]
      },
      updated_at=now
    )
    app_tables.cms_modules.add_row(
      page=page, code="text", position=0,
      content={"title": article["title"], "text": article["text"]},
      enabled=True
    )
    created.append(article["slug"])
  if created:
    Core.log_audit(
      action="cms.reference_articles_seeded", entity_type="cms_page",
      details={"slugs": created}, created_at=now
    )


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def get_cms_pages():
  PricePagesService._seed_price_pages()
  rows = app_tables.cms_pages.search(
    q.fetch_only("slug", "title", "status", "updated_at"),
    order_by("title")
  )[:100]
  return {"ok": True, "rows": [_page_record(row) for row in rows]}


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def get_cms_page(page_id):
  if not isinstance(page_id, str) or not page_id:
    return {"ok": False, "message": "Некорректная страница."}
  page = app_tables.cms_pages.get_by_id(page_id)
  if page is None:
    return {"ok": False, "message": "Страница не найдена."}
  module_rows = app_tables.cms_modules.search(
    q.fetch_only("code", "position", "content", "enabled"),
    order_by("position"), page=page
  )[:MAX_MODULES]
  return {
    "ok": True, "page": _page_record(page),
    "settings": page["settings"] or {},
    "modules": [_module_record(row) for row in module_rows],
    "module_types": MODULE_TYPES
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def save_cms_page(title, slug, settings_raw, page_id=None):
  user = Core.require_permission("cms.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  title, error = _text(title, "Название страницы", 120)
  if error:
    return {"ok": False, "message": error}
  title = title or ""
  slug, error = _text(slug, "Адрес страницы", 80)
  if error:
    return {"ok": False, "message": error}
  slug = slug or ""
  if not SLUG_RE.fullmatch(slug):
    return {"ok": False, "message": "Адрес должен содержать латинские буквы, цифры и дефис."}
  settings, error = _decode_small_object(settings_raw, "Настройки страницы")
  if error:
    return {"ok": False, "message": error}
  settings, error = _validate_page_settings(settings)
  if error:
    return {"ok": False, "message": error}
  if page_id is not None and (not isinstance(page_id, str) or not page_id):
    return {"ok": False, "message": "Некорректная страница."}
  page = app_tables.cms_pages.get_by_id(page_id) if page_id else None
  if page_id and page is None:
    return {"ok": False, "message": "Страница не найдена."}
  duplicate = app_tables.cms_pages.get(slug=slug)
  if duplicate is not None and (page is None or duplicate.get_id() != page.get_id()):
    return {"ok": False, "message": "Такой адрес страницы уже используется."}
  now = datetime.now(timezone.utc)
  values = {
    "title": title or "", "slug": slug, "settings": settings,
    "status": "draft", "updated_by": user, "updated_at": now
  }
  if page is None:
    values["status"] = "draft"
    page = app_tables.cms_pages.add_row(**values)
    action = "cms.page_created"
  else:
    page.update(**values)
    action = "cms.page_updated"
  Core.log_audit(
    actor=user, action=action, entity_type="cms_page",
    entity_id=page.get_id(), details={"slug": slug}, created_at=now
  )
  return {"ok": True, "page_id": page.get_id(), "message": "Страница сохранена."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def save_cms_module(page_id, module_code, position, content_raw,
                    enabled=True, module_id=None):
  user = Core.require_permission("cms.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(page_id, str) or not page_id:
    return {"ok": False, "message": "Выберите страницу."}
  page = app_tables.cms_pages.get_by_id(page_id)
  if page is None:
    return {"ok": False, "message": "Страница не найдена."}
  if not isinstance(module_code, str) or module_code not in dict(MODULE_TYPES):
    return {"ok": False, "message": "Выберите тип CMS-модуля."}
  if isinstance(position, bool) or not isinstance(position, (str, int, float)):
    return {"ok": False, "message": "Проверьте позицию модуля."}
  try:
    position_number = int(position)
  except (TypeError, ValueError, OverflowError):
    return {"ok": False, "message": "Позиция модуля должна быть целым числом."}
  if position_number < 0 or position_number > 100000:
    return {"ok": False, "message": "Позиция модуля вне допустимого диапазона."}
  content, error = _decode_small_object(
    content_raw, "Содержимое модуля", maximum=50000
  )
  if error:
    return {"ok": False, "message": error}
  if not isinstance(enabled, bool):
    return {"ok": False, "message": "Проверьте состояние модуля."}
  if module_id is not None and (not isinstance(module_id, str) or not module_id):
    return {"ok": False, "message": "Некорректный CMS-модуль."}
  row = app_tables.cms_modules.get_by_id(module_id) if module_id else None
  if module_id and (row is None or row["page"].get_id() != page_id):
    return {"ok": False, "message": "Модуль не найден в этой странице."}
  if row is None and len(list(app_tables.cms_modules.search(page=page)[:MAX_MODULES + 1])) >= MAX_MODULES:
    return {"ok": False, "message": "На странице допускается не более 100 модулей."}
  duplicate_position = next((
    item for item in app_tables.cms_modules.search(page=page, position=position_number)
    if row is None or item.get_id() != row.get_id()
  ), None)
  if duplicate_position is not None:
    return {"ok": False, "message": "Эта позиция страницы уже занята другим модулем."}
  now = datetime.now(timezone.utc)
  values = {
    "page": page, "code": module_code, "position": position_number,
    "content": content, "enabled": enabled
  }
  if row is None:
    row = app_tables.cms_modules.add_row(**values)
    action = "cms.module_created"
  else:
    row.update(**values)
    action = "cms.module_updated"
  page.update(status="draft", updated_by=user, updated_at=now)
  Core.log_audit(
    actor=user, action=action, entity_type="cms_module",
    entity_id=row.get_id(),
    details={"page": page["slug"], "type": module_code, "enabled": enabled},
    created_at=now
  )
  return {"ok": True, "module_id": row.get_id(), "message": "Модуль сохранён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def set_cms_module_enabled(module_id, enabled):
  user = Core.require_permission("cms.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(module_id, str) or not module_id or not isinstance(enabled, bool):
    return {"ok": False, "message": "Проверьте модуль и его состояние."}
  row = app_tables.cms_modules.get_by_id(module_id)
  if row is None:
    return {"ok": False, "message": "Модуль не найден."}
  row["enabled"] = enabled
  page = row["page"]
  now = datetime.now(timezone.utc)
  page.update(status="draft", updated_by=user, updated_at=now)
  Core.log_audit(
    actor=user, action="cms.module_toggled", entity_type="cms_module",
    entity_id=module_id,
    details={"enabled": enabled, "page": page["slug"]}, created_at=now
  )
  return {
    "ok": True,
    "message": "Модуль включён." if enabled else "Модуль выключен."
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def reorder_cms_module(page_id, module_id, direction):
  user = Core.require_permission("cms.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(page_id, str) or not isinstance(module_id, str):
    return {"ok": False, "message": "Выберите страницу и блок."}
  if direction not in ("up", "down"):
    return {"ok": False, "message": "Неизвестное направление перемещения."}
  page = app_tables.cms_pages.get_by_id(page_id)
  module = app_tables.cms_modules.get_by_id(module_id)
  if page is None or module is None or module["page"].get_id() != page_id:
    return {"ok": False, "message": "Блок не найден в выбранной странице."}
  rows = list(app_tables.cms_modules.search(
    q.fetch_only("code", "position", "content", "enabled"),
    order_by("position"), page=page
  )[:MAX_MODULES])
  current_index = next((
    index for index, row in enumerate(rows)
    if row.get_id() == module_id
  ), None)
  if current_index is None:
    return {"ok": False, "message": "Блок не найден."}
  target_index = current_index - 1 if direction == "up" else current_index + 1
  if target_index < 0 or target_index >= len(rows):
    return {"ok": True, "message": "Блок уже у края списка."}
  rows[current_index], rows[target_index] = rows[target_index], rows[current_index]
  for index, row in enumerate(rows):
    row["position"] = (index + 1) * 10
  now = datetime.now(timezone.utc)
  page.update(status="draft", updated_by=user, updated_at=now)
  Core.log_audit(
    actor=user, action="cms.module_reordered", entity_type="cms_module",
    entity_id=module_id,
    details={"page": page["slug"], "direction": direction}, created_at=now
  )
  return {"ok": True, "message": "Порядок блоков сохранён."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def delete_cms_module(module_id):
  user = Core.require_permission("cms.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(module_id, str) or not module_id:
    return {"ok": False, "message": "Выберите блок."}
  row = app_tables.cms_modules.get_by_id(module_id)
  if row is None:
    return {"ok": False, "message": "Блок не найден."}
  page = row["page"]
  details = {"page": page["slug"], "type": row["code"]}
  row.delete()
  now = datetime.now(timezone.utc)
  page.update(status="draft", updated_by=user, updated_at=now)
  Core.log_audit(
    actor=user, action="cms.module_deleted", entity_type="cms_module",
    entity_id=module_id, details=details, created_at=now
  )
  return {"ok": True, "message": "Блок удалён. Страница сохранена как черновик."}


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def preview_cms_page(page_id):
  if not isinstance(page_id, str) or not page_id:
    return {"ok": False, "message": "Выберите страницу."}
  page = app_tables.cms_pages.get_by_id(page_id)
  if page is None:
    return {"ok": False, "message": "Страница не найдена."}
  modules = app_tables.cms_modules.search(
    q.fetch_only("code", "position", "content", "enabled"),
    order_by("position"), page=page, enabled=True
  )[:MAX_MODULES]
  return {
    "ok": True, "page": _page_record(page),
    "settings": page["settings"] or {},
    "modules": [_module_record(row) for row in modules]
  }


@anvil.server.callable(require_user=True)
@Core.permission_guard("cms.manage")
def publish_cms_page(page_id):
  user = Core.require_permission("cms.manage")
  if user is None:
    raise anvil.server.PermissionDenied("Войдите в систему.")
  if not isinstance(page_id, str) or not page_id:
    return {"ok": False, "message": "Выберите страницу."}
  page = app_tables.cms_pages.get_by_id(page_id)
  if page is None:
    return {"ok": False, "message": "Страница не найдена."}
  enabled_module = next(iter(app_tables.cms_modules.search(
    q.fetch_only("code"), page=page, enabled=True
  )), None)
  if enabled_module is None:
    return {"ok": False, "message": "Добавьте включённый контентный модуль перед публикацией."}
  now = datetime.now(timezone.utc)
  settings = page["settings"] or {}
  if not settings.get("publish_date"):
    settings["publish_date"] = now.strftime("%d.%m.%Y")
  page.update(status="published", settings=settings, updated_by=user, updated_at=now)
  Core.log_audit(
    actor=user, action="cms.page_published", entity_type="cms_page",
    entity_id=page_id, details={"slug": page["slug"]}, created_at=now
  )
  return {"ok": True, "message": "Страница опубликована."}


@anvil.server.callable
def get_published_cms_page(slug):
  if isinstance(slug, str) and slug.startswith("prices-"):
    PricePagesService._seed_price_pages()
  if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
    return {"ok": False, "message": "Некорректный адрес страницы."}
  page = app_tables.cms_pages.get(slug=slug, status="published")
  if page is None:
    return {"ok": False, "message": "Опубликованная страница не найдена."}
  modules = app_tables.cms_modules.search(
    q.fetch_only("code", "position", "content", "enabled"),
    order_by("position"), page=page, enabled=True
  )[:MAX_MODULES]
  return {
    "ok": True, "page": _page_record(page),
    "article": {
      "publish_date": (page["settings"] or {}).get("publish_date", ""),
      "excerpt": (page["settings"] or {}).get("excerpt", ""),
      "seo_title": (page["settings"] or {}).get("seo_title", ""),
      "seo_description": (page["settings"] or {}).get("seo_description", ""),
      "keywords": (page["settings"] or {}).get("keywords", ""),
      "canonical_url": (page["settings"] or {}).get("canonical_url", ""),
      "social_image_url": (page["settings"] or {}).get("social_image_url", ""),
      "news_category": (page["settings"] or {}).get("news_category", "")
    },
    "modules": [_module_record(row) for row in modules]
  }


@anvil.server.callable
def get_published_cms_pages():
  _ensure_reference_articles()
  rows = [
    row for row in app_tables.cms_pages.search(
      q.fetch_only("slug", "title", "status", "updated_at", "settings"),
      order_by("updated_at", ascending=False),
      status="published"
    )[:120]
    if (row["settings"] or {}).get("price_category") != "prices"
  ][:100]
  records = []
  for row in rows:
    record = _page_record(row)
    settings = row["settings"] or {}
    record["publish_date"] = settings.get("publish_date", "")
    record["excerpt"] = settings.get("excerpt", "")
    record["seo_title"] = settings.get("seo_title", "")
    record["news_category"] = settings.get("news_category", "")
    records.append(record)
  return {"ok": True, "rows": records}
