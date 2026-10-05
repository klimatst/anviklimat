import anvil.secrets
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import math
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

import anvil.http
import anvil.server
import anvil.users
from anvil.tables import app_tables, order_by, query as q
import Core
import Config


SLOTS = ("primary", "secondary", "third", "local")
SLOT_TITLES = {
  "primary": "Основной",
  "secondary": "Резервный 1",
  "third": "Резервный 2",
  "local": "Локальный"
}
PRIORITIES = {slot: (index + 1) * 10 for index, slot in enumerate(SLOTS)}
OPERATIONS = {
  "hvac_consult": "Консультация по HVAC",
  "load_assessment": "Оценка тепловой нагрузки",
  "equipment_selection": "Подбор оборудования",
  "refrigerant_lines": "Линейка холодильщика",
  "ventilation": "Анализ вентиляции",
  "installation": "Планирование монтажа",
  "create": "Создание",
  "edit": "Редактирование",
  "import": "Импорт",
  "calculate": "Расчёт",
  "analyze": "Анализ",
  "diagnose": "Диагностика неисправности",
  "generate": "Генерация",
  "audit": "Аудит",
  "pdf_catalog_extract": "Извлечение товаров из PDF",
  "catalog_classify": "Классификация товара по каталогу",
  "catalog_enrich": "Карточка товара по источнику",
  "duplicate_review": "Проверка похожих моделей",
  "spec_compare": "Сравнение характеристик",
  "commissioning": "Пусконаладочный чек-лист",
  "maintenance_plan": "План технического обслуживания",
  "energy_audit": "Аудит энергопотребления",
  "work_order": "Задание монтажной бригаде",
  "quote_audit": "Проверка сметы и КП",
  "refrigerant_diagnosis": "Диагностика холодильного контура",
  "site_rewrite": "Редактор текста сайта",
  "site_seo": "SEO-редактор",
  "site_faq": "Редактор FAQ",
  "site_headline": "Редактор заголовков",
  "catalog_description": "Редактор карточки товара",
  "catalog_specs": "Нормализация характеристик",
  "catalog_category": "Подбор категории каталога",
  "order_reply": "Помощник по ответам клиентам",
  "order_summary": "Сводка заявки клиента",
  "admin_settings_advice": "Помощник по настройкам проекта",
  "admin_diagnostic": "Разбор системной диагностики",
  "site_accessibility": "Проверка доступности контента",
  "site_translate": "Перевод контента сайта",
  "site_outline": "План структуры страницы",
  "catalog_import_mapping": "Сопоставление полей импорта",
  "catalog_taxonomy_review": "Проверка дерева категорий",
  "pdf_import_triage": "Разбор ошибок PDF-импорта"
}
OPERATION_INSTRUCTIONS = {
  "hvac_consult": "Дай практический ответ по HVAC, опираясь только на вопрос и переданные данные.",
  "load_assessment": "Проверь предварительную тепловую нагрузку и объясни состав результата. Не называй эскизную оценку проектным расчётом.",
  "equipment_selection": "Сравни только переданные модели и характеристики каталога. Не придумывай характеристики, цены или наличие.",
  "refrigerant_lines": "Помоги проверить трассу и дозаправку хладагента. Диаметр трубы и заправку бери только из данных точной модели; если их нет, перечисли недостающие данные и не угадывай.",
  "ventilation": "Проверь расход, кратность, приток, вытяжку и сечение по переданным данным. Укажи принятые допущения и необходимость сверки с нормами проекта.",
  "installation": "Подготовь перечень работ и вопросов для монтажника. Не выдумывай расценки, длины, материалы и технические параметры.",
  "diagnose": "Составь безопасную последовательность диагностики HVAC. Не предлагай опасные действия с электричеством или хладагентом; направляй к квалифицированному специалисту.",
  "calculate": "Проверь арифметику и объясни расчёт по входным данным, но не подменяй расчётный движок приложения.",
  "analyze": "Проанализируй только переданные данные и обозначь неизвестное.",
  "audit": "Найди несогласованности в переданных данных и предложи проверяемые исправления.",
  "pdf_catalog_extract": "Извлеки из переданного текста и/или изображения страницы PDF только явно указанные товары. Верни JSON с полями summary, products и warnings. Для каждого товара укажи brand, model, sku, type, series, description, category_code, subcategory_code, specs (все явно указанные характеристики с единицами), sale_price, currency, quantity (только число, если оно явно указано), availability (текст наличия), source_page, documents [{title,url}], confidence и короткую цитату evidence. Используй только коды из списка. Если классификация сомнительна — оставь код пустым. Не придумывай характеристики, цены, наличие, ссылки и числа; верни не более 12 товаров из этого фрагмента.",
  "catalog_classify": "Подбери код существующей категории только из переданного списка. Объясни совпадающие признаки и неопределённость; не создавай новые категории.",
  "catalog_enrich": "Подготовь краткое русское описание карточки только из переданных характеристик. Не добавляй факты, стандарты, цены или преимущества без источника.",
  "duplicate_review": "Сравни модель с найденными похожими карточками. Раздели точные совпадения, вероятные дубли и разные модели; не объединяй их автоматически.",
  "spec_compare": "Сопоставь переданные модели по одинаковым характеристикам и единицам. Покажи отсутствующие и несопоставимые значения, не рассчитывай характеристики догадкой.",
  "commissioning": "Составь проверяемый чек-лист пусконаладки HVAC по переданным схемам и данным. Отметь точки измерений и требования к квалифицированному персоналу.",
  "maintenance_plan": "Собери план обслуживания на основе переданных моделей, условий и регламента производителя. Не выдумывай периодичность, если её нет в источнике.",
  "energy_audit": "Найди подтверждённые данными причины энергопотребления и варианты проверки. Не обещай экономию без измерений и исходного режима.",
  "work_order": "Сформируй задание бригаде по переданному проекту: зона, работы, оборудование, материалы, контроль и вопросы. Не придумывай объёмы или цены.",
  "quote_audit": "Проверь смету и КП на пропуски, единицы, арифметику и расхождения только по переданным строкам. Не меняй цены и не дополняй их догадками.",
  "refrigerant_diagnosis": "Составь безопасный алгоритм диагностики холодильного контура по измерениям и модели. Не назначай дозаправку по одному давлению и не советуй опасные действия.",
  "site_rewrite": "Отредактируй текст для сайта компании климатической инженерии. Сохрани подтверждённые факты, смысл и числовые данные; не добавляй обещаний или неподтверждённых услуг. Верни отредактированный текст и краткий список правок.",
  "site_seo": "Подготовь SEO-заголовок, описание и варианты поисковых запросов только на основе входного материала. Не добавляй характеристики, цены, адреса или услуги, которых нет во входных данных.",
  "site_faq": "Составь полезные вопросы и ответы для страницы сайта только на основе переданного текста. Не выдумывай цены, сроки, гарантии или технические свойства; неизвестное обозначь как вопрос менеджеру.",
  "site_headline": "Предложи варианты заголовка, подзаголовка и текста кнопки для указанного блока сайта. Сохрани фактические ограничения и не обещай неподтверждённый результат.",
  "catalog_description": "Подготовь понятное описание карточки HVAC-товара только из переданных полей. Не придумывай преимущества, совместимость, цену, наличие, нормы или характеристики.",
  "catalog_specs": "Нормализуй переданные характеристики: сохрани исходные значения и единицы, приведи одинаковые названия к единому виду, отметь противоречия и не конвертируй без точных исходных данных.",
  "catalog_category": "Предложи наиболее подходящий путь категории из списка. Если уверенность недостаточна, верни несколько вариантов и явно попроси ручную проверку. Не создавай новые категории автоматически.",
  "order_reply": "Составь вежливый черновик ответа клиенту по заявке. Не подтверждай цену, наличие, сроки, скидки или выполнение работ, если они явно не указаны; оставь менеджеру вопросы для уточнения.",
  "order_summary": "Сделай короткую сводку заявки: запрос клиента, оборудование, количество, контакты только как переданы, недостающие данные и следующий шаг. Не дополняй отсутствующие данные догадками.",
  "admin_settings_advice": "Помоги подобрать настройки проекта по описанной цели. Раздели рекомендации на конкретные поля, предложенные значения и возможные последствия. Не утверждай, что изменил проект; ничего не сохраняй автоматически.",
  "admin_diagnostic": "Разбери переданные диагностические сообщения: сгруппируй подтверждённые ошибки, влияние на сайт и безопасные шаги проверки. Не заявляй, что выполнил исправление, и не угадывай причину без данных.",
  "site_accessibility": "Проверь переданный контент с точки зрения понятности и текстовой доступности: предложи короткие фразы, ясные названия ссылок и осмысленные альтернативные подписи только по доступным данным. Не делай заявлений о фактическом WCAG-соответствии без проверки интерфейса.",
  "site_translate": "Переведи переданный текст на указанный целевой язык. Сохрани числа, артикулы, единицы измерения, ссылки и технические обозначения. Не добавляй новые факты; пометь неоднозначные отраслевые термины.",
  "site_outline": "Предложи структурированный план страницы: заголовки, порядок блоков и назначение каждого блока. Опирайся только на заданную цель и исходные факты, помечай места, где контент нужно предоставить отдельно.",
  "catalog_import_mapping": "Сопоставь заголовки исходного файла с переданными полями каталога. Для каждого поля верни исходную колонку, уверенность и причину; не придумывай отсутствующие столбцы и выдели неоднозначные соответствия.",
  "catalog_taxonomy_review": "Проверь переданное дерево категорий на повторы, смешение уровней, несогласованные названия и очевидно неуместные ветки. Предложи исправленное дерево только как черновик и явно укажи, какие товары потребуют ручного перемещения.",
  "pdf_import_triage": "Разбери предупреждения PDF-импорта. Сгруппируй ошибки извлечения текста, OCR, изображений, категорий и дубликатов; укажи страницы и только безопасные следующие действия. Не заявляй, что восстановил исходные данные."
}
SYSTEM_INSTRUCTION = (
  "Ты русскоязычный технический помощник HVAC. Не выдумывай факты, цены, "
  "характеристики и нормы; помечай неизвестное. Верни краткий JSON-объект "
  "с полями резюме, шаги, допущения, предупреждения, рекомендации."
)
CHAT_SYSTEM_INSTRUCTION = (
  "Ты русскоязычный технический ИИ-помощник по климатическому оборудованию, "
  "инженерным системам, проектированию, монтажу и сервису. Отвечай естественно, "
  "структурируй длинные ответы, задавай уточняющие вопросы при нехватке данных. "
  "Не выдумывай характеристики, цены, нормы и факты. Для фото описывай только "
  "то, что действительно видно, и отмечай неопределённость."
)
CHAT_HISTORY_LIMIT = 12
CHAT_MESSAGE_LIMIT = 6000
CHAT_TOTAL_TEXT_LIMIT = 18000
CHAT_IMAGE_LIMIT_BYTES = 3 * 1024 * 1024
CHAT_TOTAL_IMAGE_LIMIT_BYTES = 6 * 1024 * 1024
CHAT_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
CHAT_RESPONSE_LIMIT_BYTES = 24000
SECRET_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
MAX_RESPONSE_BYTES = 9000
CACHE_TTL = timedelta(hours=24)
CACHE_FAILURE_TTL = timedelta(minutes=2)
USAGE_LIMIT = 120
USAGE_RETAIN = 80
RATE_WINDOW_SECONDS = 300
RATE_LIMIT = 10
DEFAULT_PROVIDER_OPTIONS = {
  "temperature": None,
  "top_p": None,
  "frequency_penalty": None,
  "presence_penalty": None,
  "max_tokens": 0,
  "timeout_seconds": 0
}
PROVIDER_API_KEY_OPTION = "_api_key"


class ProviderError(Exception):
  pass


def _current_user():
  user = anvil.users.get_user()
  if user is not None:
    Core._ensure_core_data(user)
  return user


def _endpoint_error(endpoint, local=False, resolve_host=False):
  if not isinstance(endpoint, str) or len(endpoint) > 500:
    return "Адрес API должен быть HTTPS-ссылкой не длиннее 500 символов."
  try:
    parts = urlsplit(endpoint.strip())
    hostname = parts.hostname
    port = parts.port
  except ValueError:
    return "Проверьте адрес API."
  normalized_host = (hostname or "").rstrip(".").casefold()
  if not hostname or parts.username or parts.password or parts.fragment or parts.query:
    return "API должен иметь адрес без учётных данных и фрагмента URL."
  if not local and port is not None and port not in (443, 8443):
    return "Укажите стандартный порт HTTPS или порт локальной модели."
  if not local and (
    parts.scheme != "https" or normalized_host == "localhost"
    or normalized_host.endswith((".local", ".internal"))
  ):
    return "Внешний API должен использовать публичный HTTPS-адрес."
  if local and parts.scheme not in ("http", "https"):
    return "Локальный endpoint должен использовать HTTP или HTTPS."
  try:
    address = ipaddress.ip_address(normalized_host)
  except ValueError:
    address = None
  if local:
    internal_host = (
      normalized_host in ("localhost", "ollama", "llama.cpp", "vllm", "host.docker.internal")
      or normalized_host.endswith((".local", ".internal"))
      or (address is not None and (
        address.is_private or address.is_loopback or address.is_link_local
      ))
    )
    if not internal_host:
      return "Локальный адрес API должен указывать на внутреннюю сеть или локальную модель."
  elif address is not None and not address.is_global:
    return "Внешний API не может использовать локальный или служебный IP-адрес."
  elif resolve_host and address is None and not Config.is_public_host(hostname, port or 443):
    return "Внешний API не может разрешаться в локальный или служебный IP-адрес."
  return None


def _json_size(value):
  try:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
  except (TypeError, ValueError):
    return None


def _validate_json_value(value, depth=0, max_string=2000, max_items=30):
  if depth > 5:
    return False
  if value is None or isinstance(value, (bool, int)):
    return True
  if isinstance(value, float):
    return value == value and abs(value) != float("inf")
  if isinstance(value, str):
    return len(value) <= max_string
  if isinstance(value, list):
    return len(value) <= max_items and all(
      _validate_json_value(item, depth + 1, max_string, max_items) for item in value
    )
  if isinstance(value, dict):
    return len(value) <= 24 and all(
      isinstance(key, str) and 0 < len(key) <= 64
      and _validate_json_value(item, depth + 1, max_string, max_items)
      for key, item in value.items()
    )
  return False


def _provider_api_key(row):
  if row is None:
    return ""
  value = row["api_key"]
  if isinstance(value, str) and value:
    return value
  options = row["options"]
  if not isinstance(options, dict):
    return ""
  value = options.get(PROVIDER_API_KEY_OPTION, "")
  return value if isinstance(value, str) else ""


def _provider_record(row):
  options = _normalize_provider_options(row["options"]) if row is not None else dict(DEFAULT_PROVIDER_OPTIONS)
  return {
    "id": row.get_id() if row is not None else None,
    "slot": row["slot"] if row is not None else "",
    "slot_title": _provider_title(row["slot"]) if row is not None else "",
    "provider": row["provider"] if row is not None else "openai_compatible",
    "model": row["model"] if row is not None else "",
    "endpoint": row["endpoint"] if row is not None else "",
    "secret_ref": row["secret_ref"] if row is not None else "",
    "has_api_key": bool(_provider_api_key(row)),
    "enabled": bool(row["enabled"]) if row is not None else False,
    "priority": row["priority"] if row is not None else 50,
    "options": options
  }


def _provider_title(slot):
  if slot in SLOT_TITLES:
    return SLOT_TITLES[slot]
  if isinstance(slot, str) and slot.startswith("api_"):
    return slot[4:].replace("_", " ").strip().title() or "API-подключение"
  return str(slot or "Провайдер")


def _ordered_provider_rows(rows=None):
  rows = list(app_tables.ai_providers.search(enabled=True)) if rows is None else list(rows)
  return sorted(rows, key=lambda row: (
    row["priority"] if isinstance(row["priority"], (int, float)) else 1000,
    row["slot"] or ""
  ))


def _normalize_provider_options(raw):
  if not isinstance(raw, dict):
    return dict(DEFAULT_PROVIDER_OPTIONS)
  values = dict(DEFAULT_PROVIDER_OPTIONS)
  float_ranges = {
    "temperature": (0, 2),
    "top_p": (0, 1),
    "frequency_penalty": (-2, 2),
    "presence_penalty": (-2, 2)
  }
  for name, (minimum, maximum) in float_ranges.items():
    value = raw.get(name)
    if value is None or isinstance(value, bool):
      continue
    try:
      value = float(value)
    except (TypeError, ValueError, OverflowError):
      continue
    if math.isfinite(value) and minimum <= value <= maximum:
      values[name] = value
  tokens = raw.get("max_tokens", 0)
  try:
    tokens = int(tokens or 0)
  except (TypeError, ValueError, OverflowError):
    tokens = 0
  if not isinstance(raw.get("max_tokens", 0), bool) and (
    tokens == 0 or 100 <= tokens <= 4000
  ):
    values["max_tokens"] = tokens
  timeout = raw.get("timeout_seconds", 0)
  try:
    timeout = int(timeout or 0)
  except (TypeError, ValueError, OverflowError):
    timeout = 0
  if not isinstance(raw.get("timeout_seconds", 0), bool) and (
    timeout == 0 or 5 <= timeout <= 30
  ):
    values["timeout_seconds"] = timeout
  return values


def _validate_provider_options(raw):
  if raw is None:
    raw = {}
  if not isinstance(raw, dict):
    return None, "Проверьте дополнительные параметры модели."
  unknown = set(raw) - set(DEFAULT_PROVIDER_OPTIONS)
  if unknown:
    return None, "Передан неизвестный параметр модели."

  float_ranges = (
    ("temperature", "Температура", 0, 2),
    ("top_p", "Top P", 0, 1),
    ("frequency_penalty", "Штраф частоты", -2, 2),
    ("presence_penalty", "Штраф новизны", -2, 2)
  )
  float_values = {}
  for name, title, minimum, maximum in float_ranges:
    raw_value = raw.get(name)
    if raw_value is None or raw_value == "":
      float_values[name] = None
      continue
    if isinstance(raw_value, bool):
      return None, "{}: укажите число от {} до {}.".format(title, minimum, maximum)
    try:
      value = float(str(raw_value).strip().replace(",", "."))
    except (TypeError, ValueError, OverflowError):
      return None, "{}: укажите число от {} до {}.".format(title, minimum, maximum)
    if not math.isfinite(value) or not minimum <= value <= maximum:
      return None, "{}: укажите число от {} до {}.".format(title, minimum, maximum)
    float_values[name] = value

  try:
    max_tokens = int(raw.get("max_tokens") or 0)
  except (TypeError, ValueError, OverflowError):
    return None, "Максимум токенов должен быть 0 или целым числом от 100 до 4000."
  if isinstance(raw.get("max_tokens"), bool) or not (
    max_tokens == 0 or 100 <= max_tokens <= 4000
  ):
    return None, "Максимум токенов должен быть 0 или целым числом от 100 до 4000."

  try:
    timeout = int(raw.get("timeout_seconds") or 0)
  except (TypeError, ValueError, OverflowError):
    return None, "Тайм-аут должен быть 0 или целым числом от 5 до 30 секунд."
  if isinstance(raw.get("timeout_seconds"), bool) or not (
    timeout == 0 or 5 <= timeout <= 30
  ):
    return None, "Тайм-аут должен быть 0 или целым числом от 5 до 30 секунд."

  return {
    **float_values,
    "max_tokens": max_tokens,
    "timeout_seconds": timeout
  }, None


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_ai_providers():
  rows = {}
  for row in app_tables.ai_providers.search():
    slot = row["slot"]
    if slot in SLOTS:
      rows[slot] = row
  custom_rows = [row for row in app_tables.ai_providers.search()
                 if isinstance(row["slot"], str) and row["slot"].startswith("api_")]
  custom_rows.sort(key=lambda row: (
    row["priority"] if isinstance(row["priority"], (int, float)) else 1000,
    row["slot"]
  ))
  custom_records = []
  for row in custom_rows:
    custom_records.append(_provider_record(row))
  return {
    "ok": True,
    "providers": [
      _provider_record(rows.get(slot)) | {"slot": slot, "slot_title": SLOT_TITLES[slot],
                                         "priority": PRIORITIES[slot]}
      for slot in SLOTS
    ] + custom_records
  }


@anvil.server.callable(require_user=True)
def get_ai_status():
  if _current_user() is None:
    return {"ok": False, "message": "Войдите в систему."}
  enabled_slots = {row["slot"]: row for row in _ordered_provider_rows()}
  status_rows = [
    {"slot": slot, "title": SLOT_TITLES[slot],
     "configured": bool(enabled_slots.get(slot) and enabled_slots[slot]["model"]),
     "model": enabled_slots[slot]["model"] if enabled_slots.get(slot) else ""}
    for slot in SLOTS
  ]
  for slot, row in enabled_slots.items():
    if slot not in SLOTS:
      status_rows.append({
        "slot": slot, "title": _provider_title(slot),
        "configured": bool(row["model"]), "model": row["model"] or ""
      })
  return {
    "ok": True,
    "providers": status_rows,
    "local_note": "Модели обращаются к внешнему провайдеру через сервер приложения; локальная модель требует отдельной инфраструктуры."
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_ai_provider(slot, provider, model, endpoint, secret_ref, enabled,
                     api_key="", clear_api_key=False, options=None, priority=None):
  is_custom = isinstance(slot, str) and re.fullmatch(r"api_[a-z0-9_-]{1,40}", slot)
  if not isinstance(slot, str) or (slot not in SLOTS and not is_custom):
    return {"ok": False, "message": "Выберите существующее API-подключение."}
  if provider != "openai_compatible":
    return {"ok": False, "message": "Поддерживается только совместимый API чата."}
  if not isinstance(model, str) or len(model.strip()) > 120:
    return {"ok": False, "message": "Проверьте название модели."}
  if not isinstance(endpoint, str):
    return {"ok": False, "message": "Проверьте адрес API."}
  if not isinstance(secret_ref, str) or len(secret_ref) > 80:
    return {"ok": False, "message": "Проверьте имя секрета Anvil."}
  if not isinstance(enabled, bool):
    return {"ok": False, "message": "Проверьте состояние AI-слота."}
  if not isinstance(api_key, str) or len(api_key) > 500:
    return {"ok": False, "message": "Проверьте ключ API: максимум 500 символов."}
  if any(ord(char) < 32 or ord(char) == 127 for char in api_key):
    return {"ok": False, "message": "Ключ API содержит недопустимые управляющие символы."}
  if not isinstance(clear_api_key, bool):
    return {"ok": False, "message": "Проверьте параметр удаления ключа."}

  model = model.strip()
  endpoint = endpoint.strip()
  secret_ref = secret_ref.strip()
  api_key = api_key.strip()
  if clear_api_key and api_key:
    return {"ok": False, "message": "Введите новый ключ или отметьте удаление ключа, но не оба действия."}
  row = app_tables.ai_providers.get(slot=slot)
  if row is None and is_custom:
    return {"ok": False, "message": "API-подключение не найдено. Добавьте его через кнопку «Добавить API»."}
  if options is None:
    provider_options = _normalize_provider_options(row["options"] if row is not None else {})
  else:
    provider_options, options_error = _validate_provider_options(options)
    if options_error:
      return {"ok": False, "message": options_error}
  stored_key = _provider_api_key(row)
  if clear_api_key:
    stored_key = ""
  elif api_key:
    stored_key = api_key
  if enabled:
    error = _endpoint_error(
      endpoint, local=(slot == "local"), resolve_host=(slot != "local")
    )
    if error:
      return {"ok": False, "message": error}
    if not model:
      return {"ok": False, "message": "Укажите модель для включённого слота."}
    if slot != "local" and not (stored_key or secret_ref):
      return {"ok": False, "message": "Введите ключ API или задайте прежнее имя секрета."}
    if slot == "local" and (secret_ref or stored_key):
      return {"ok": False, "message": "Локальный endpoint не использует ключ внешнего API."}
  if secret_ref and not stored_key:
    if not SECRET_REF_RE.fullmatch(secret_ref):
      return {"ok": False, "message": "Имя секрета содержит недопустимые символы."}
    secret_value = Config.get_secret(secret_ref)
    if not isinstance(secret_value, str) or not secret_value:
      return {"ok": False, "message": "Секрет не найден в Anvil Secrets."}

  stored_options = _normalize_provider_options(provider_options)
  stored_options.pop(PROVIDER_API_KEY_OPTION, None)

  if priority is None:
    priority_value = (
      row["priority"] if row is not None and isinstance(row["priority"], (int, float))
      else PRIORITIES.get(slot, 50)
    )
  else:
    if isinstance(priority, bool):
      return {"ok": False, "message": "Порядок подключения должен быть числом от 0 до 10000."}
    try:
      priority_value = int(priority)
    except (TypeError, ValueError, OverflowError):
      return {"ok": False, "message": "Порядок подключения должен быть числом от 0 до 10000."}
    if not 0 <= priority_value <= 10000:
      return {"ok": False, "message": "Порядок подключения должен быть числом от 0 до 10000."}

  values = {
    "slot": slot, "provider": provider, "model": model, "endpoint": endpoint,
    "secret_ref": secret_ref, "api_key": stored_key,
    "options": stored_options,
    "enabled": enabled,
    "priority": priority_value, "updated_at": datetime.now(timezone.utc)
  }
  if row is None:
    app_tables.ai_providers.add_row(**values)
  else:
    row.update(**values)
  return {"ok": True, "message": "Настройки API-подключения сохранены."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def test_ai_provider(slot):
  if not isinstance(slot, str) or not (slot in SLOTS or re.fullmatch(r"api_[a-z0-9_-]{1,40}", slot)):
    return {"ok": False, "message": "Выберите существующее API-подключение."}
  row = app_tables.ai_providers.get(slot=slot)
  if row is None:
    return {"ok": False, "message": "Сначала сохраните настройки API-подключения."}
  if not row["model"] or not row["endpoint"]:
    return {"ok": False, "message": "Перед проверкой сохраните адрес API и модель."}
  if not _provider_api_key(row) and not row["secret_ref"]:
    return {"ok": False, "message": "Добавьте ключ API или имя секрета Anvil."}

  test_options = _normalize_provider_options(row["options"])
  test_options.update({"temperature": 0, "max_tokens": 24, "timeout_seconds": 12})
  provider = {
    "slot": row["slot"], "provider": row["provider"], "model": row["model"],
    "endpoint": row["endpoint"], "secret_ref": row["secret_ref"],
    "api_key": _provider_api_key(row), "options": test_options
  }
  user = _current_user()
  try:
    _call_provider(
      provider, "analyze", {},
      chat_history=[{"role": "user", "content": "Reply with OK.", "image_data": None}]
    )
  except ProviderError as error:
    Core.log_audit(
      actor=user, action="ai.provider_test_failed", entity_type="ai_provider",
      entity_id=slot, details={"model": row["model"], "message": str(error)[:240]},
      created_at=datetime.now(timezone.utc)
    )
    return {"ok": False, "message": "Проверка не пройдена: {}".format(str(error))}

  Core.log_audit(
    actor=user, action="ai.provider_test_succeeded", entity_type="ai_provider",
    entity_id=slot, details={"model": row["model"]},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "message": "Подключение работает. Ответ получен от выбранной модели."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def create_ai_provider(title):
  if not isinstance(title, str):
    return {"ok": False, "message": "Введите название API-подключения."}
  normalized = re.sub(r"[^a-z0-9]+", "_", title.strip().casefold()).strip("_")
  if not normalized or len(normalized) > 40:
    return {"ok": False, "message": "Название должно содержать до 40 латинских букв или цифр."}
  slot = "api_" + normalized
  if app_tables.ai_providers.get(slot=slot) is not None:
    return {"ok": False, "message": "Подключение с таким названием уже существует."}
  rows = list(app_tables.ai_providers.search())
  priority = max(
    [row["priority"] for row in rows if isinstance(row["priority"], (int, float))]
    or [40]
  ) + 10
  now = datetime.now(timezone.utc)
  app_tables.ai_providers.add_row(
    slot=slot, provider="openai_compatible", model="", endpoint="",
    secret_ref="", options=dict(DEFAULT_PROVIDER_OPTIONS), enabled=False,
    priority=priority, updated_at=now
  )
  return {"ok": True, "slot": slot, "message": "API добавлено. Укажите endpoint, модель и ключ, затем включите подключение."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def delete_ai_provider(slot):
  if not isinstance(slot, str) or not slot.startswith("api_"):
    return {"ok": False, "message": "Системные слоты ИИ удалять нельзя."}
  row = app_tables.ai_providers.get(slot=slot)
  if row is None:
    return {"ok": False, "message": "API-подключение не найдено."}
  row.delete()
  return {"ok": True, "message": "API-подключение удалено."}


def _consume_rate_limit(user, now, limit=RATE_LIMIT):
  user_hash = hashlib.sha256(str(user.get_id()).encode("utf-8")).hexdigest()[:24]
  key = "ai.rate." + user_hash
  bucket = int(now.timestamp()) // RATE_WINDOW_SECONDS
  row = app_tables.system_settings.get(key=key)
  value = row["value"] if row is not None else {}
  if not isinstance(value, dict):
    value = {}
  count = value.get("count", 0) if value.get("bucket") == bucket else 0
  if count >= limit:
    return False
  values = {"bucket": bucket, "count": count + 1}
  if row is None:
    app_tables.system_settings.add_row(
      key=key, value=values, updated_at=now, updated_by=user
    )
  else:
    row.update(value=values, updated_at=now, updated_by=user)
  return True


def _cached_result(user, request_hash, now):
  row = app_tables.ai_usage.get(actor=user, request_hash=request_hash)
  if row is None or row["response"] is None:
    return None
  ttl = CACHE_TTL if row["status"] == "success" else CACHE_FAILURE_TTL
  if row["status"] not in ("success", "unavailable"):
    return None
  if row["created_at"] is None or now - row["created_at"] > ttl:
    return None
  if not isinstance(row["response"], dict):
    return None
  if row["status"] == "success":
    return {"ok": True, "cached": True, "provider": "cache", "result": row["response"]}
  return {
    "ok": False, "cached": True,
    "message": row["response"].get("message", "Поставщики ИИ временно недоступны."),
    "details": row["response"].get("details", [])
  }


def _request_cache_key(user, operation, payload, by_slot):
  provider_context = []
  for slot, row in sorted(
    by_slot.items(), key=lambda item: (
      item[1]["priority"] if isinstance(item[1]["priority"], (int, float)) else 1000,
      item[0]
    )
  ):
    secret_ref = row["secret_ref"] or ""
    key_value = _provider_api_key(row)
    if not key_value and secret_ref:
      key_value = Config.get_secret(secret_ref) or ""
    secret_hash = hashlib.sha256(key_value.encode("utf-8")).hexdigest() if isinstance(key_value, str) and key_value else ""
    provider_context.append({
      "slot": slot, "provider": row["provider"], "model": row["model"],
      "endpoint": row["endpoint"], "secret_ref": secret_ref,
      "secret_hash": secret_hash, "priority": row["priority"],
      "options": _normalize_provider_options(row["options"])
    })
  context = {
    "version": 3, "instruction": SYSTEM_INSTRUCTION,
    "operation_instruction": OPERATION_INSTRUCTIONS.get(operation, "Выполни задачу только по переданным данным."),
    "user": str(user.get_id()), "operation": operation,
    "payload": payload, "providers": provider_context
  }
  encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, allow_nan=False)
  return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _provider_content_text(content):
  if isinstance(content, str):
    text = content.strip()
    return text or None
  if isinstance(content, dict):
    for key in ("text", "output_text", "generated_text", "answer", "content"):
      value = content.get(key)
      if isinstance(value, str) and value.strip():
        return value.strip()
    for key in ("content", "output", "response", "result", "parts", "message", "data", "generations"):
      value = content.get(key)
      if isinstance(value, (dict, list)):
        text = _provider_content_text(value)
        if text:
          return text
    return None
  if isinstance(content, list):
    parts = []
    for block in content:
      if isinstance(block, str):
        if block.strip():
          parts.append(block.strip())
        continue
      if not isinstance(block, dict):
        continue
      text = block.get("text") or block.get("output_text")
      if isinstance(text, str) and text.strip():
        parts.append(text.strip())
        continue
      if block.get("type") in ("tool_use", "function_call"):
        value = block.get("input", block.get("arguments"))
        if isinstance(value, str):
          parts.append(value.strip())
        elif isinstance(value, dict):
          parts.append(json.dumps(value, ensure_ascii=False))
        continue
      nested = block.get("content", block.get("parts", block.get("output")))
      if isinstance(nested, (dict, list)):
        text = _provider_content_text(nested)
        if text:
          parts.append(text)
    return "\n".join(parts).strip() if parts else None
  return None


def _provider_response_content(response):
  if not isinstance(response, dict):
    raise ProviderError("Поставщик вернул ответ не в формате объекта.")
  choices = response.get("choices")
  if isinstance(choices, list) and choices and isinstance(choices[0], dict):
    choice = choices[0]
    message = choice.get("message")
    if isinstance(message, dict):
      content = message.get("content")
      if content is not None:
        return content
      refusal = message.get("refusal")
      if isinstance(refusal, str) and refusal.strip():
        return refusal
      tool_calls = message.get("tool_calls")
      if isinstance(tool_calls, list):
        arguments = []
        for call in tool_calls:
          function = call.get("function", {}) if isinstance(call, dict) else {}
          value = function.get("arguments") if isinstance(function, dict) else None
          if isinstance(value, str):
            arguments.append(value)
        if arguments:
          return "\n".join(arguments)
    delta = choice.get("delta")
    if isinstance(delta, dict) and delta.get("content") is not None:
      return delta["content"]
    if isinstance(choice.get("text"), str):
      return choice["text"]
  candidates = response.get("candidates")
  if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
    candidate_content = candidates[0].get("content")
    if candidate_content is not None:
      return candidate_content
  for key in (
    "output_text", "generated_text", "text", "content", "output",
    "response", "result", "answer", "message", "generations", "data"
  ):
    if key in response and response[key] is not None:
      return response[key]
  raise ProviderError("Поставщик вернул ответ без текстового содержимого.")


def _provider_usage_tokens(response):
  usage = response.get("usage", {}) if isinstance(response, dict) else {}
  if not isinstance(usage, dict):
    return 0
  tokens = usage.get("total_tokens")
  if tokens is None:
    prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
    prompt_tokens = prompt_tokens if isinstance(prompt_tokens, (int, float)) and not isinstance(prompt_tokens, bool) else 0
    completion_tokens = completion_tokens if isinstance(completion_tokens, (int, float)) and not isinstance(completion_tokens, bool) else 0
    tokens = prompt_tokens + completion_tokens
  if isinstance(tokens, bool) or not isinstance(tokens, (int, float)) or tokens < 0:
    return 0
  return int(tokens)


def _parse_provider_response(response, structured=True, max_response_bytes=MAX_RESPONSE_BYTES,
                             max_items=30, max_string=2000):
  content = _provider_response_content(response)
  content_is_text_block = isinstance(content, dict) and (
    content.get("type") in ("text", "output_text")
    or isinstance(content.get("text"), str)
    or isinstance(content.get("output_text"), str)
  )
  if structured and isinstance(content, dict) and not content_is_text_block:
    result = content
  else:
    text = _provider_content_text(content)
    if text is None and not structured and isinstance(content, (dict, list)):
      text = json.dumps(content, ensure_ascii=False)
    if text is None:
      raise ProviderError("Поставщик вернул ответ в неподдерживаемом формате.")
    if not text.strip():
      raise ProviderError("Поставщик вернул пустой ответ.")
    if not structured:
      result = text
    else:
      text = text.strip()
      if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
          text = "\n".join(lines[1:-1]).strip()
      try:
        result = json.loads(text)
      except json.JSONDecodeError:
        raise ProviderError("Поставщик не вернул корректный JSON.")
  if structured:
    if not isinstance(result, dict) or not _validate_json_value(
      result, max_items=max_items, max_string=max_string
    ):
      raise ProviderError("Ответ должен быть небольшим JSON-объектом.")
    result_size = _json_size(result)
    if result_size is None or result_size > max_response_bytes:
      raise ProviderError("Ответ поставщика превышает допустимый размер.")
  else:
    if not isinstance(result, str):
      raise ProviderError("Поставщик вернул ответ в неподдерживаемом формате.")
    if len(result.encode("utf-8")) > CHAT_RESPONSE_LIMIT_BYTES:
      raise ProviderError("Ответ поставщика превышает допустимый размер.")
  return result, _provider_usage_tokens(response)


def _call_provider(row, operation, payload, chat_history=None, image_data=None):
  endpoint_error = _endpoint_error(
    row["endpoint"], local=(row["slot"] == "local"),
    resolve_host=(row["slot"] != "local")
  )
  if endpoint_error:
    raise ProviderError(endpoint_error)
  secret_ref = row["secret_ref"] or ""
  headers = {"Content-Type": "application/json"}
  secret_value = _provider_api_key(row)
  if not secret_value and secret_ref:
    secret_value = Config.get_secret(secret_ref)
  if secret_value:
    if not isinstance(secret_value, str) or not secret_value:
      raise ProviderError("Ключ поставщика не настроен.")
    headers["Authorization"] = "Bearer " + secret_value

  options = _normalize_provider_options(row["options"])
  messages: list[dict[str, Any]]
  if chat_history is None:
    user_content = json.dumps(
      {"operation": operation, "input": payload},
      ensure_ascii=False, allow_nan=False
    )
    if image_data:
      user_content = [
        {"type": "text", "text": user_content},
        {"type": "image_url", "image_url": {"url": image_data}}
      ]
    messages = [
      {"role": "system", "content": SYSTEM_INSTRUCTION + " " + OPERATION_INSTRUCTIONS.get(operation, "Выполни задачу только по переданным данным.")},
      {"role": "user", "content": user_content}
    ]
    structured = True
  else:
    mode_instruction = OPERATION_INSTRUCTIONS.get(operation, "")
    system_message = CHAT_SYSTEM_INSTRUCTION
    if mode_instruction:
      system_message += " " + mode_instruction
    messages = [{"role": "system", "content": system_message}]
    for entry in chat_history:
      content = entry["content"]
      image_data = entry.get("image_data")
      if image_data:
        content = [
          {"type": "text", "text": content or "Посмотри это изображение."},
          {"type": "image_url", "image_url": {"url": image_data}}
        ]
      messages.append({"role": entry["role"], "content": content})
    structured = False

  request_body = {
    "model": row["model"],
    "messages": messages,
    "max_tokens": options["max_tokens"] or (
      3500 if operation == "pdf_catalog_extract" else
      1800 if chat_history is not None else 700
    )
  }
  if options["temperature"] is not None:
    request_body["temperature"] = options["temperature"]
  for option_name in ("top_p", "frequency_penalty", "presence_penalty"):
    if options[option_name] is not None:
      request_body[option_name] = options[option_name]
  timeout = options["timeout_seconds"] or (
    30 if chat_history is not None else
    30 if operation == "pdf_catalog_extract" else 6
  )
  try:
    response = anvil.http.request(
      row["endpoint"], method="POST", json=True,
      headers=headers, data=request_body,
      timeout=timeout
    )
  except anvil.http.HttpError as error:
    raise ProviderError("Поставщик вернул HTTP {}.".format(error.status))
  if operation == "pdf_catalog_extract" and chat_history is None:
    return _parse_provider_response(
      response, structured=structured, max_response_bytes=24000,
      max_items=250, max_string=4000
    )
  return _parse_provider_response(response, structured=structured)


def _write_usage(user, request_hash, operation, provider, response, tokens, status, now):
  row = app_tables.ai_usage.get(actor=user, request_hash=request_hash)
  values = {
    "actor": user, "operation": operation, "request_hash": request_hash,
    "provider": provider, "response": response or {}, "tokens": tokens,
    "status": status, "created_at": now
  }
  if row is None:
    row = app_tables.ai_usage.add_row(**values)
  else:
    row.update(**values)
  rows = list(app_tables.ai_usage.search(order_by("created_at"))[:USAGE_LIMIT + 1])
  if len(rows) > USAGE_LIMIT:
    for old_row in rows[:len(rows) - USAGE_RETAIN]:
      old_row.delete()


@anvil.server.callable(require_user=True)
def ai_operator(operation, payload):
  user = _current_user()
  return _run_ai_operation(user, operation, payload)


def _run_ai_operation(user, operation, payload, input_limit=3500,
                      max_string=2000, max_items=30, image_data=None):
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(operation, str) or operation not in OPERATIONS:
    return {"ok": False, "message": "Выберите поддерживаемый сценарий ИИ-помощника."}
  if not isinstance(payload, dict) or not _validate_json_value(
    payload, max_string=max_string, max_items=max_items
  ):
    return {"ok": False, "message": "Контекст должен быть небольшим JSON-объектом."}
  payload_size = _json_size(payload)
  if payload_size is None or payload_size > input_limit:
    return {"ok": False, "message": "Контекст превышает допустимый размер."}
  if image_data is not None and (
    not isinstance(image_data, str)
    or len(image_data) > 4 * 1024 * 1024
    or not re.fullmatch(r"data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+", image_data)
  ):
    return {"ok": False, "message": "Изображение страницы имеет неверный формат или слишком велико."}

  now = datetime.now(timezone.utc)
  providers = _ordered_provider_rows()
  by_slot = {row["slot"]: row for row in providers}
  request_hash = _request_cache_key(user, operation, payload, by_slot)
  cached = _cached_result(user, request_hash, now)
  if cached is not None:
    return cached
  request_limit = 1200 if operation == "pdf_catalog_extract" else RATE_LIMIT
  if not _consume_rate_limit(user, now, limit=request_limit):
    return {"ok": False, "message": "Достигнут лимит ИИ для этого периода. Повторите позже."}

  failures = []
  for provider in providers:
    slot = provider["slot"]
    if provider["provider"] != "openai_compatible":
      failures.append("{}: неподдерживаемый адаптер".format(_provider_title(slot)))
      continue
    try:
      result, tokens = _call_provider(
        provider, operation, payload, image_data=image_data
      )
    except ProviderError as error:
      failures.append("{}: {}".format(_provider_title(slot), str(error)))
      continue
    _write_usage(user, request_hash, operation, slot, result, tokens, "success", now)
    return {"ok": True, "cached": False, "provider": slot, "result": result}

  unavailable = {
    "message": "Подключённые поставщики ИИ недоступны. Проверьте модель, ключ и адрес API в настройках ИИ.",
    "details": failures[:4]
  }
  _write_usage(
    user, request_hash, operation, "local", unavailable, 0,
    "unavailable", now
  )
  return {"ok": False, "cached": False, **unavailable}


def _prepare_chat_history(history):
  if not isinstance(history, list) or not history or len(history) > CHAT_HISTORY_LIMIT:
    return None, "История чата должна содержать не более 12 сообщений."
  normalized = []
  previous_role = None
  total_text = 0
  total_image_bytes = 0
  for index, message in enumerate(history):
    if not isinstance(message, dict):
      return None, "В истории чата обнаружено некорректное сообщение."
    role = message.get("role")
    content = message.get("content", "")
    image = message.get("image")
    if role not in ("user", "assistant") or (index == 0 and role != "user"):
      return None, "История должна начинаться с сообщения пользователя."
    if role == previous_role:
      return None, "Сообщения пользователя и ИИ должны идти по очереди."
    if not isinstance(content, str) or len(content) > CHAT_MESSAGE_LIMIT:
      return None, "Текст сообщения должен быть не длиннее 6 000 символов."
    total_text += len(content)
    if total_text > CHAT_TOTAL_TEXT_LIMIT:
      return None, "История чата слишком длинная. Начните новый диалог."
    if role == "assistant" and image is not None:
      return None, "Изображения можно прикреплять только к сообщению пользователя."

    image_data = None
    if image is not None:
      mime_type = getattr(image, "content_type", None)
      size = getattr(image, "length", None)
      if mime_type not in CHAT_IMAGE_TYPES:
        return None, "Поддерживаются изображения JPEG, PNG и WebP."
      if not isinstance(size, int) or size < 1 or size > CHAT_IMAGE_LIMIT_BYTES:
        return None, "Размер одного изображения не должен превышать 3 МБ."
      raw_image = image.get_bytes()
      if len(raw_image) != size:
        size = len(raw_image)
      total_image_bytes += size
      if size > CHAT_IMAGE_LIMIT_BYTES or total_image_bytes > CHAT_TOTAL_IMAGE_LIMIT_BYTES:
        return None, "Общий размер изображений в запросе не должен превышать 6 МБ."
      encoded = base64.b64encode(raw_image).decode("ascii")
      image_data = "data:{};base64,{}".format(mime_type, encoded)
    if not content.strip() and image_data is None:
      return None, "Пустые сообщения отправлять нельзя."
    normalized.append({
      "role": role,
      "content": content.strip(),
      "image_data": image_data
    })
    previous_role = role
  if normalized[-1]["role"] != "user":
    return None, "Последнее сообщение должно быть сообщением пользователя."
  return normalized, None


@anvil.server.callable(require_user=True)
def ai_chat(history, operation="chat"):
  user = _current_user()
  if user is None:
    return {"ok": False, "message": "Войдите в систему."}
  if not isinstance(operation, str) or (
    operation != "chat" and operation not in OPERATION_INSTRUCTIONS
  ):
    return {"ok": False, "message": "Выберите режим ответа из списка."}
  safe_history, history_error = _prepare_chat_history(history)
  if history_error or safe_history is None:
    return {"ok": False, "message": history_error}

  now = datetime.now(timezone.utc)
  if not _consume_rate_limit(user, now):
    return {"ok": False, "message": "Лимит: 10 запросов за 5 минут. Повторите позже."}
  providers = _ordered_provider_rows()
  request_fingerprint = [
    {
      "role": entry["role"],
      "content": entry["content"],
      "image": hashlib.sha256(entry["image_data"].encode("ascii")).hexdigest()
        if entry["image_data"] else ""
    }
    for entry in safe_history
  ]
  request_hash = hashlib.sha256(json.dumps(
    {
      "actor": str(user.get_id()),
      "operation": operation,
      "history": request_fingerprint,
      "requested_at": now.isoformat()
    }, ensure_ascii=False, sort_keys=True
  ).encode("utf-8")).hexdigest()

  failures = []
  for provider in providers:
    slot = provider["slot"]
    if provider["provider"] != "openai_compatible":
      failures.append("{}: неподдерживаемый адаптер".format(_provider_title(slot)))
      continue
    try:
      answer, tokens = _call_provider(
        provider, operation, {}, chat_history=safe_history
      )
    except ProviderError as error:
      failures.append("{}: {}".format(_provider_title(slot), str(error)))
      continue
    _write_usage(
      user, request_hash, "chat", slot, {"text": answer}, tokens, "success", now
    )
    return {
      "ok": True,
      "text": answer,
      "provider": slot,
      "tokens": tokens
    }

  unavailable = {
    "message": "Подключённые поставщики ИИ недоступны. Проверьте модель, ключ и адрес API в настройках ИИ.",
    "details": failures[:4]
  }
  _write_usage(
    user, request_hash, "chat", "local", unavailable, 0, "unavailable", now
  )
  return {"ok": False, **unavailable}


@anvil.server.callable(require_user=True)
@Core.permission_guard("import.manage")
def ai_extract_catalog_pdf(document_text, categories):
  user = Core.require_permission("import.manage")
  return _extract_catalog_pdf_for_user(user, document_text, categories)


def extract_pdf_page_for_import(user, document_text, categories, image_data=None):
  """Internal worker entry point; the import creator is rechecked server-side."""
  if user is None or not Core.has_permission(user, "import.manage"):
    return {"ok": False, "message": "Недостаточно прав для извлечения PDF."}
  return _extract_catalog_pdf_for_user(
    user, document_text, categories, image_data=image_data
  )


def _extract_catalog_pdf_for_user(user, document_text, categories, image_data=None):
  if (
    not isinstance(document_text, str) or not document_text.strip()
    or len(document_text) > 12000
  ):
    return {"ok": False, "message": "Текст PDF должен содержать до 12 000 символов."}
  if not isinstance(categories, list) or len(categories) > 250:
    return {"ok": False, "message": "Список категорий каталога слишком велик."}
  safe_categories = []
  for item in categories:
    if not isinstance(item, dict):
      return {"ok": False, "message": "Некорректный список категорий."}
    code, title = item.get("code"), item.get("title")
    parent_code = item.get("parent_code") or ""
    if (
      not isinstance(code, str) or not isinstance(title, str)
      or not isinstance(parent_code, str)
    ):
      return {"ok": False, "message": "Некорректные коды категорий."}
    if len(code) > 100 or len(title) > 160 or len(parent_code) > 100:
      return {"ok": False, "message": "Слишком длинное название категории."}
    safe_categories.append({
      "code": code, "title": title, "parent_code": parent_code
    })
  payload = {"document_text": document_text, "categories": safe_categories}
  if image_data:
    payload["image_sha256"] = hashlib.sha256(
      image_data.encode("ascii")
    ).hexdigest()
  return _run_ai_operation(
    user, "pdf_catalog_extract",
    payload, input_limit=65000, max_string=12000, max_items=250,
    image_data=image_data
  )
