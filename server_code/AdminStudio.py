"""Admin settings studio, configurable dashboard widgets and site extensions."""

from datetime import datetime, timedelta, timezone
import json
import math
import re
import secrets
from typing import Any, cast

import anvil.server
from anvil.tables import app_tables, query as q

import Core
import AI
import Config


STATE_KEY = "admin_studio_v1"


def _field(key, label, kind, default, hint="", choices=(), core_key=None,
           minimum=None, maximum=None):
  return {
    "key": key, "label": label, "type": kind, "default": default,
    "hint": hint, "choices": list(choices), "core_key": core_key,
    "minimum": minimum, "maximum": maximum
  }


def _text(key, label, default="", hint="", maximum=180, kind="text"):
  return _field(key, label, kind, default, hint, maximum=maximum)


def _toggle(key, label, default=False, hint=""):
  return _field(key, label, "bool", default, hint)


def _number(key, label, default, minimum=0, maximum=1000, hint=""):
  return _field(key, label, "number", default, hint,
                minimum=minimum, maximum=maximum)


def _select(key, label, default, choices, hint=""):
  return _field(key, label, "select", default, hint,
                [(label, value) for label, value in choices])


def _core(key, label, kind, default, choices=(), hint=""):
  return _field(key, label, kind, default, hint, choices, core_key=key)


def _section(code, group, title, description, *fields):
  return {
    "id": code, "group": group, "title": title,
    "description": description, "fields": list(fields)
  }


_THEMES = [
  ("Стальной синий", "blue"), ("Графитовый", "graphite"),
  ("Арктический лёд", "ice"), ("Тёмный янтарь", "amber"),
  ("Красный титан", "crimson"), ("Ночная сталь", "violet")
]
_ON_OFF = [("Включено", "on"), ("Выключено", "off")]
_DENSITY = [("Компактно", "compact"), ("Стандартно", "standard"),
            ("Свободно", "spacious")]


# 64 editable settings modules, organized around the actual site and its
# existing catalogue, CMS, CRM, engineering and user-management features.
SETTINGS_SECTIONS = [
  _section("site.identity", "Сайт", "Профиль сайта",
    "Публичное имя и базовые данные компании.",
    _core("organization_name", "Название компании", "text", "ЭКО-КЛИМАТ"),
    _text("site.tagline", "Короткий слоган", "Климат под инженерным контролем"),
    _text("site.canonical_url", "Основной адрес сайта", "", "Например, https://example.ru", 240, "url")),
  _section("site.contacts", "Сайт", "Контакты",
    "Контакты, которые показываются посетителям сайта.",
    _core("contact_email", "Публичная почта", "text", ""),
    _core("contact_phone", "Телефон", "text", "+79257873848"),
    _core("contact_address", "Адрес", "text", "")),
  _section("site.locale", "Сайт", "Язык и регион",
    "Язык интерфейса и отображение значений.",
    _select("site.locale", "Язык сайта", "ru", [("Русский", "ru"), ("English", "en")]),
    _select("site.date_format", "Формат даты", "dmy", [("ДД.ММ.ГГГГ", "dmy"), ("ГГГГ-ММ-ДД", "ymd")]),
    _select("site.timezone", "Часовой пояс", "Europe/Moscow", [("Москва", "Europe/Moscow"), ("UTC", "UTC") ])),
  _section("site.currency", "Сайт", "Валюта и цены",
    "Валюта по умолчанию и вид цены в карточках.",
    _core("currency", "Валюта сайта", "select", "RUB", [("Рубли · RUB", "RUB"), ("Доллары · USD", "USD"), ("Евро · EUR", "EUR")] ),
    _toggle("pricing.show_from", "Показывать «от» перед ценой", True),
    _toggle("pricing.show_currency", "Показывать обозначение валюты", True)),
  _section("site.appearance", "Сайт", "Оформление сайта",
    "Цветовая тема и визуальная плотность публичной части.",
    _core("site_theme", "Цветовая тема", "select", "blue", _THEMES),
    _select("site.density", "Плотность блоков", "standard", _DENSITY),
    _toggle("site.motion", "Анимация переходов", True)),
  _section("site.typography", "Сайт", "Типографика",
    "Размеры и начертания для читаемости сайта.",
    _select("site.type_scale", "Размер текста", "normal", [("Компактный", "small"), ("Обычный", "normal"), ("Крупный", "large")]),
    _toggle("site.heading_serif", "Акцентный шрифт заголовков", False)),
  _section("site.header", "Сайт", "Шапка сайта",
    "Управление контактной полосой и быстрыми кнопками.",
    _toggle("header.show_phone", "Показывать телефон в шапке", True),
    _toggle("header.sticky", "Закреплять шапку при прокрутке", False),
    _toggle("header.show_account", "Показывать вход и профиль", True)),
  _section("site.navigation", "Сайт", "Меню сайта",
    "Основные ссылки и поведение меню.",
    _toggle("navigation.catalog", "Показывать каталог", True),
    _toggle("navigation.news", "Показывать новости", True),
    _toggle("navigation.projects", "Показывать проекты авторизованным", True)),
  _section("site.footer", "Сайт", "Подвал сайта",
    "Контакты, подпись и служебные блоки нижней части страниц.",
    _text("footer.caption", "Подпись компании", "КЛИМАТИЧЕСКАЯ ИНЖЕНЕРИЯ"),
    _toggle("footer.show_contacts", "Показывать контакты", True),
    _toggle("footer.show_copyright", "Показывать строку авторских прав", True)),
  _section("site.home.hero", "Сайт", "Главная · первый экран",
    "Заголовок и кнопки главного экрана.",
    _text("home.hero_title", "Заголовок", "Климатические системы с инженерным подходом", maximum=120),
    _text("home.hero_button", "Текст основной кнопки", "Подобрать оборудование", maximum=48),
    _text("home.hero_url", "Адрес основной кнопки", "#catalog", maximum=240)),
  _section("site.home.blocks", "Сайт", "Главная · блоки",
    "Какие информационные блоки показывать на главной.",
    _toggle("home.show_catalog", "Показывать витрину каталога", True),
    _toggle("home.show_gallery", "Показывать галерею работ", True),
    _toggle("home.show_news", "Показывать последние новости", True)),
  _section("site.pages", "Сайт", "Страницы и CMS",
    "Предпочтения редактора страниц и публикаций.",
    _select("cms.default_status", "Статус новой страницы", "draft", [("Черновик", "draft"), ("Опубликована", "published")]),
    _number("cms.preview_width", "Ширина предпросмотра, px", 1180, 640, 1920)),
  _section("site.news", "Сайт", "Новости и статьи",
    "Отображение новостей и карточек публикаций.",
    _number("news.page_size", "Публикаций на странице", 12, 4, 48),
    _toggle("news.show_dates", "Показывать дату публикации", True)),
  _section("site.gallery", "Сайт", "Галерея работ",
    "Вид галереи и число карточек.",
    _number("gallery.page_size", "Карточек на странице", 12, 4, 48),
    _select("gallery.card_ratio", "Формат карточек", "landscape", [("Горизонтальный", "landscape"), ("Квадратный", "square") ])),
  _section("site.seo", "Сайт", "SEO сайта",
    "Общие поисковые заголовки и описание.",
    _text("seo.site_title", "Заголовок по умолчанию", "ЭКО-КЛИМАТ · климатическая инженерия", maximum=160),
    _text("seo.site_description", "Описание сайта", "", maximum=300, kind="textarea"),
    _toggle("seo.include_brand", "Добавлять название компании в заголовки", True)),
  _section("site.seo.catalog", "Сайт", "SEO каталога",
    "Заголовки и индексирование страниц каталога.",
    _text("seo.catalog_title", "Шаблон заголовка каталога", "{category} · оборудование Hisense", maximum=160),
    _toggle("seo.index_catalog", "Разрешить индексацию каталога", True)),
  _section("site.social.preview", "Сайт", "Предпросмотр в соцсетях",
    "Текст и изображение ссылки при публикации.",
    _text("social.og_title", "Заголовок карточки", "ЭКО-КЛИМАТ", maximum=120),
    _text("social.og_description", "Описание карточки", "", maximum=240, kind="textarea")),
  _section("site.urls", "Сайт", "Адреса страниц",
    "Правила ссылок и канонические адреса.",
    _select("urls.trailing_slash", "Завершающий слеш", "keep", [("Сохранять", "keep"), ("Убирать", "remove")]),
    _toggle("urls.canonical", "Использовать основной адрес сайта", True)),
  _section("site.privacy", "Сайт", "Приватность и cookies",
    "Настройки уведомления о cookies и приватности.",
    _toggle("privacy.cookie_notice", "Показывать уведомление о cookies", False),
    _text("privacy.notice_text", "Текст уведомления", "", maximum=300, kind="textarea")),
  _section("catalog.general", "Каталог", "Каталог · общие правила",
    "Видимость и стандартная выдача каталога.",
    _toggle("catalog.public", "Показывать каталог посетителям", True),
    _number("catalog.page_size", "Товаров на странице", 24, 8, 96)),
  _section("catalog.categories", "Каталог", "Категории",
    "Порядок и вид карточек категорий.",
    _select("catalog.category_order", "Сортировка категорий", "manual", [("Вручную", "manual"), ("По алфавиту", "title"), ("По количеству товаров", "products")]),
    _toggle("catalog.hide_empty_categories", "Скрывать пустые категории", True)),
  _section("catalog.cards", "Каталог", "Карточки товаров",
    "Количество элементов и состав карточки каталога.",
    _toggle("catalog.card_show_model", "Показывать модель", True),
    _toggle("catalog.card_show_availability", "Показывать наличие", True),
    _toggle("catalog.card_show_order", "Показывать кнопку заказа", True)),
  _section("catalog.filters", "Каталог", "Фильтры каталога",
    "Включение основных фильтров каталога.",
    _toggle("catalog.filter_category", "Фильтр по категории", True),
    _toggle("catalog.filter_brand", "Фильтр по бренду", True),
    _toggle("catalog.filter_price", "Фильтр по цене", True)),
  _section("catalog.sort", "Каталог", "Сортировка товаров",
    "Доступные способы сортировки списка.",
    _select("catalog.default_sort", "Сортировка по умолчанию", "name", [("По названию", "name"), ("Сначала новые", "newest"), ("Сначала дешевле", "price_asc")]),
    _toggle("catalog.allow_sort_price", "Разрешить сортировку по цене", True)),
  _section("catalog.product.main", "Каталог", "Карточка товара · основное",
    "Поля и порядок основных сведений товара.",
    _toggle("product.show_sku", "Показывать артикул", True),
    _toggle("product.show_brand", "Показывать бренд", True),
    _toggle("product.show_category", "Показывать категорию", True)),
  _section("catalog.product.description", "Каталог", "Карточка товара · описание",
    "Отображение описания и характеристик.",
    _toggle("product.show_description", "Показывать описание", True),
    _toggle("product.show_specs", "Показывать характеристики", True),
    _number("product.spec_limit", "Характеристик в кратком блоке", 8, 1, 30)),
  _section("catalog.product.images", "Каталог", "Изображения товаров",
    "Галерея карточки и подписи изображений.",
    _number("product.gallery_limit", "Изображений в галерее", 12, 1, 30),
    _toggle("product.image_zoom", "Увеличивать главное изображение", True)),
  _section("catalog.stock", "Каталог", "Наличие и склад",
    "Текст и логика отображения остатков.",
    _select("stock.out_of_stock_label", "Подпись при отсутствии", "request", [("Под заказ", "request"), ("Нет в наличии", "none"), ("Уточнить", "ask")]),
    _toggle("stock.show_quantity", "Показывать точное количество", False)),
  _section("catalog.price", "Каталог", "Цены каталога",
    "Формат и доступность цены.",
    _select("price.display_mode", "Вид цены", "exact", [("Точная цена", "exact"), ("По запросу", "request"), ("От минимальной", "from")]),
    _number("price.decimals", "Знаков после запятой", 0, 0, 2)),
  _section("catalog.search", "Каталог", "Поиск по товарам",
    "Минимальная длина запроса и область поиска.",
    _number("search.minimum_length", "Минимум символов", 2, 1, 8),
    _toggle("search.include_sku", "Искать по артикулу", True),
    _toggle("search.include_specs", "Искать по характеристикам", True)),
  _section("catalog.compatibility", "Каталог", "Совместимость оборудования",
    "Настройки таблиц совместимости.",
    _toggle("compatibility.public", "Показывать совместимость посетителям", True),
    _toggle("compatibility.show_confidence", "Показывать уровень проверки", True)),
  _section("catalog.import", "Каталог", "Импорт каталога",
    "Правила проверки и обновления товаров при импорте.",
    _select("import.duplicate_mode", "Совпадающий артикул", "update", [("Обновить товар", "update"), ("Пропустить", "skip"), ("Сообщить об ошибке", "error")]),
    _toggle("import.allow_new_categories", "Создавать новые категории", True)),
  _section("catalog.export", "Каталог", "Экспорт каталога",
    "Формат и объём выгрузок каталога.",
    _select("export.default_format", "Формат по умолчанию", "csv", [("CSV", "csv"), ("JSON", "json")]),
    _toggle("export.include_images", "Включать ссылки на изображения", True)),
  _section("catalog.media", "Каталог", "Медиа-библиотека",
    "Ограничения загрузки и поведение медиа-каталога.",
    _number("media.max_images_per_product", "Изображений на товар", 12, 1, 30),
    _select("media.default_format", "Формат загрузки", "keep", [("Сохранять исходный", "keep"), ("WebP", "webp") ])),
  _section("catalog.brands", "Каталог", "Бренды",
    "Отображение брендов и их сортировка.",
    _select("brands.order", "Порядок брендов", "title", [("По названию", "title"), ("Вручную", "manual")]),
    _toggle("brands.show_logos", "Показывать логотипы брендов", False)),
  _section("orders.general", "Заказы", "Заявки каталога",
    "Приём заявок и обязательность контакта.",
    _toggle("orders.accept_public", "Принимать новые заявки", True),
    _toggle("orders.require_phone", "Запрашивать телефон", True),
    _toggle("orders.require_email", "Запрашивать email", False)),
  _section("orders.statuses", "Заказы", "Статусы обработки",
    "Настройка стандартного статуса и отображения этапов.",
    _select("orders.initial_status", "Статус новой заявки", "new", [("Новая", "new"), ("В обработке", "processing")]),
    _toggle("orders.show_status_public", "Показывать статус клиенту", False)),
  _section("orders.messages", "Заказы", "Сообщения клиенту",
    "Текст подтверждения после отправки заявки.",
    _text("orders.success_title", "Заголовок подтверждения", "Заявка отправлена", maximum=100),
    _text("orders.success_message", "Текст подтверждения", "Мы свяжемся с вами для уточнения деталей.", maximum=300, kind="textarea")),
  _section("orders.routing", "Заказы", "Маршрутизация заявок",
    "Каналы и правила передачи новых заявок.",
    _select("orders.owner_team", "Ответственная группа", "sales", [("Продажи", "sales"), ("Сервис", "service")]),
    _toggle("orders.notify_admin", "Уведомлять администратора", True)),
  _section("forms.leads", "Формы", "Формы заявок",
    "Поля и проверка пользовательских заявок.",
    _toggle("forms.lead_comment", "Поле комментария", True),
    _number("forms.message_limit", "Максимум символов в комментарии", 1200, 100, 5000)),
  _section("forms.contact", "Формы", "Форма контакта",
    "Контактные поля и тексты формы связи.",
    _toggle("forms.contact_email", "Запрашивать email", True),
    _toggle("forms.contact_phone", "Запрашивать телефон", True)),
  _section("forms.validation", "Формы", "Проверка форм",
    "Строгая проверка обязательных полей и сообщений.",
    _toggle("forms.trim_input", "Удалять пробелы по краям", True),
    _text("forms.error_message", "Общий текст ошибки", "Проверьте заполнение полей.", maximum=180)),
  _section("content.blocks", "Контент", "Блоки страниц",
    "Стандартное поведение редактора блоков CMS.",
    _select("content.default_block", "Новый блок", "text", [("Текст", "text"), ("Изображение", "image"), ("Кнопка", "button")]),
    _toggle("content.show_drafts_admin", "Показывать черновики редакторам", True)),
  _section("content.richtext", "Контент", "Редактор текста",
    "Поддерживаемые элементы контента.",
    _toggle("content.rich_links", "Разрешить ссылки", True),
    _toggle("content.rich_tables", "Разрешить таблицы", True),
    _toggle("content.rich_html", "Разрешить ограниченный HTML", False)),
  _section("content.media", "Контент", "Изображения контента",
    "Подписи, размеры и поведение изображений в страницах.",
    _toggle("content.image_alt_required", "Требовать альтернативный текст", True),
    _select("content.image_fit", "Вписывание изображения", "cover", [("Заполнять блок", "cover"), ("Показывать целиком", "contain") ])),
  _section("notifications.center", "Уведомления", "Центр уведомлений",
    "Какие события выводить в панели уведомлений.",
    _toggle("notifications.new_order", "Новые заявки", True),
    _toggle("notifications.import_errors", "Ошибки импорта", True)),
  _section("notifications.email", "Уведомления", "Почтовые уведомления",
    "Адрес и тип писем. Секреты почты хранятся в сервисе Anvil.",
    _text("notifications.email_from", "Публичный адрес отправителя", "", maximum=160),
    _toggle("notifications.email_order", "Письмо о новой заявке", False)),
  _section("notifications.telegram", "Уведомления", "Telegram",
    "Канал для уведомлений о работе каталога.",
    _toggle("notifications.telegram_orders", "Отправлять новые заявки", False),
    _toggle("notifications.telegram_imports", "Отправлять итоги импорта", False)),
  _section("social.links", "Интеграции", "Социальные каналы",
    "Ссылки, которые показываются в публичных блоках.",
    _toggle("social.show_links", "Показывать социальные ссылки", True),
    _select("social.link_style", "Вид ссылок", "icons", [("Иконки", "icons"), ("Текст", "text"), ("Иконки и текст", "both") ])),
  _section("users.registration", "Пользователи", "Регистрация",
    "Поведение создания пользовательских профилей.",
    _toggle("users.public_registration", "Разрешить самостоятельную регистрацию", True),
    _toggle("users.confirm_email", "Требовать подтверждение email", True)),
  _section("users.roles", "Пользователи", "Роли и доступ",
    "Общие настройки назначений ролей.",
    _toggle("users.allow_moderator", "Использовать роль модератора", True),
    _toggle("users.audit_role_changes", "Записывать смену ролей в журнал", True)),
  _section("users.security", "Пользователи", "Безопасность входа",
    "Защитные ограничения пользовательской авторизации.",
    _number("users.session_hours", "Срок сессии, часы", 24, 1, 720),
    _toggle("users.notify_login", "Записывать успешный вход", True)),
  _section("users.profile", "Пользователи", "Профиль пользователя",
    "Дополнительные данные в кабинете пользователя.",
    _toggle("users.profile_phone", "Показывать телефон в профиле", True),
    _toggle("users.profile_company", "Показывать компанию", True)),
  _section("ai.operator", "ИИ и интеграции", "ИИ-помощник",
    "Настройки доступности существующего AI-оператора.",
    _toggle("ai.public_operator", "Показывать помощника на сайте", True),
    _number("ai.reply_limit", "Максимальный размер ответа", 1800, 200, 5000)),
  _section("ai.providers", "ИИ и интеграции", "Поставщики AI",
    "Параметры интерфейса для существующих серверных провайдеров.",
    _toggle("ai.allow_provider_fallback", "Разрешить резервного провайдера", True),
    _toggle("ai.show_provider_status", "Показывать статус провайдера в админке", True)),
  _section("ai.usage", "ИИ и интеграции", "Использование AI",
    "Срок хранения и отображение статистики.",
    _number("ai.history_days", "Дней статистики", 30, 1, 365),
    _toggle("ai.hide_response_logs", "Скрывать содержимое ответов в журналах", True)),
  _section("engineering.projects", "Проекты", "Инженерные проекты",
    "Вид списка проектов и отображение статусов.",
    _select("projects.default_view", "Представление списка", "cards", [("Карточки", "cards"), ("Таблица", "table")]),
    _toggle("projects.show_archived", "Показывать архивные проекты", False)),
  _section("engineering.calculations", "Проекты", "Расчёты",
    "Точность и детализация результатов расчётов.",
    _number("calculations.precision", "Знаков после запятой", 2, 0, 5),
    _toggle("calculations.show_formula", "Показывать применённую формулу", True)),
  _section("engineering.installation", "Проекты", "Монтажные расчёты",
    "Отображение состава монтажной сметы.",
    _toggle("installation.show_materials", "Показывать материалы", True),
    _toggle("installation.show_labor", "Показывать работы", True)),
  _section("crm.clients", "Рабочие процессы", "Клиенты CRM",
    "Представление списка и обязательность данных клиента.",
    _select("crm.client_view", "Вид списка клиентов", "table", [("Таблица", "table"), ("Карточки", "cards")]),
    _toggle("crm.require_contact", "Требовать контакт для клиента", False)),
  _section("crm.tasks", "Рабочие процессы", "Задачи CRM",
    "Приоритеты и отображение задач.",
    _select("crm.task_default_priority", "Приоритет новой задачи", "normal", [("Обычный", "normal"), ("Высокий", "high"), ("Срочный", "urgent")]),
    _toggle("crm.show_completed", "Показывать завершённые задачи", True)),
  _section("crm.service", "Рабочие процессы", "Сервис и обслуживание",
    "Сроки и статусы сервисных записей.",
    _number("service.reminder_days", "Напоминать за дней", 3, 0, 30),
    _toggle("service.show_history", "Показывать историю обслуживания", True)),
  _section("crm.quotes", "Рабочие процессы", "Коммерческие предложения",
    "Срок действия и представление предложений.",
    _number("quotes.validity_days", "Срок действия, дней", 14, 1, 180),
    _toggle("quotes.show_vat", "Показывать НДС отдельной строкой", False)),
  _section("import.defaults", "Импорт и экспорт", "Импорт · сопоставление",
    "Настройки сопоставления входных полей.",
    _toggle("import.match_sku_first", "Сопоставлять товары сначала по артикулу", True),
    _toggle("import.keep_unmapped", "Сохранять неизвестные поля в отчёте", True)),
  _section("import.review", "Импорт и экспорт", "Импорт · проверка",
    "Параметры предпросмотра и обработки ошибочных строк.",
    _number("import.preview_rows", "Строк в предпросмотре", 50, 5, 250),
    _select("import.error_mode", "Ошибочные строки", "skip", [("Пропустить", "skip"), ("Остановить импорт", "stop")])),
  _section("backup.policy", "Импорт и экспорт", "Резервные копии",
    "Параметры ручного резервного копирования.",
    _toggle("backup.include_media", "Включать метаданные медиа", True),
    _number("backup.retention_count", "Хранить копий, шт.", 10, 1, 100)),
  _section("audit.policy", "Система", "Журнал действий",
    "Состав и представление журнала администратора.",
    _number("audit.rows_per_page", "Событий на странице", 40, 10, 200),
    _toggle("audit.include_settings", "Записывать изменения настроек", True)),
  _section("dashboard.widgets", "Система", "Виджеты Dashboard",
    "Выбор блоков и их размера на рабочем столе.",
    _number("dashboard.max_columns", "Колонок на широком экране", 4, 1, 6),
    _select("dashboard.density", "Размер карточек", "standard", _DENSITY)),
  _section("system.health", "Система", "Диагностика",
    "Частота проверки и отображение предупреждений.",
    _toggle("system.show_health", "Показывать состояние модулей", True),
    _toggle("system.show_schema_warnings", "Показывать предупреждения схемы", True)),
  _section("system.performance", "Система", "Производительность",
    "Размер списков и интенсивность обновления.",
    _number("system.page_size", "Размер списков по умолчанию", 50, 10, 200),
    _select("system.refresh_interval", "Интервал обновления", "manual", [("Вручную", "manual"), ("30 секунд", "30"), ("1 минута", "60") ])),
  _section("system.integrations", "Система", "Подключения",
    "Состояние интеграций и видимость подключения.",
    _toggle("integrations.show_status", "Показывать состояние интеграций", True),
    _toggle("integrations.allow_external_links", "Разрешить внешние ссылки", True)),
  _section("system.extensions", "Система", "Плагины и расширения",
    "Управление собственными браузерными модулями CSS и JavaScript.",
    _toggle("extensions.allow_css", "Разрешить CSS-модули", True),
    _toggle("extensions.allow_javascript", "Разрешить JavaScript-модули", True)),
  _section("system.modules", "Система", "Модули проекта",
    "Состав модулей, подключённых к текущему проекту.",
    _select("modules.default_visibility", "Видимость новых модулей", "admin", [("Только администратор", "admin"), ("Все сотрудники", "staff")]),
    _toggle("modules.audit_changes", "Записывать включение и выключение модулей", True)),
  _section("system.ui", "Система", "Интерфейс админки",
    "Плотность панели, подписи и поведение редакторов.",
    _select("admin.density", "Плотность интерфейса", "standard", _DENSITY),
    _toggle("admin.confirm_deletions", "Подтверждать удаление", True)),
  _section("system.search", "Система", "Поиск по проекту",
    "Области поиска и количество результатов.",
    _number("admin.search_limit", "Результатов на раздел", 10, 3, 50),
    _toggle("admin.search_products", "Искать товары", True)),
  _section("system.accessibility", "Система", "Доступность интерфейса",
    "Контрастность, клавиатурная навигация и подписи.",
    _toggle("admin.high_contrast", "Повышенный контраст", False),
    _toggle("admin.focus_outlines", "Показывать фокус клавиатуры", True)),
  _section("system.localization", "Система", "Язык админки",
    "Формат чисел и подписей рабочей области.",
    _select("admin.language", "Язык панели", "ru", [("Русский", "ru"), ("English", "en")]),
    _toggle("admin.compact_dates", "Короткий формат дат", True)),
  _section("system.danger", "Система", "Опасные операции",
    "Дополнительные ограничения для массовых действий.",
    _toggle("system.confirm_bulk", "Подтверждать массовые операции", True),
    _toggle("system.require_reason", "Запрашивать причину удаления", False)),
  _section("system.custom", "Система", "Пользовательские настройки",
    "Значения расширений проекта и пользовательских модулей.",
    _text("custom.module_namespace", "Пространство имён модулей", "eco", "Только латинские буквы, цифры и дефис.", 40),
    _toggle("custom.show_disabled", "Показывать отключённые модули", True)),
  _section("site.maintenance", "Сайт", "Режим обслуживания",
    "Переключатель технического режима и пояснение посетителям.",
    _toggle("site.maintenance_mode", "Включить режим обслуживания", False),
    _text("site.maintenance_message", "Сообщение посетителям", "Сайт временно обновляется.", maximum=240)),
  _section("site.accessibility", "Сайт", "Доступность сайта",
    "Подписи изображений и увеличение интерактивных элементов.",
    _toggle("site.accessible_alt", "Проверять подписи изображений", True),
    _select("site.accessible_scale", "Размер интерфейса", "normal", [("Обычный", "normal"), ("Увеличенный", "large") ])),
  _section("catalog.related", "Каталог", "Связанные товары",
    "Количество и вид рекомендаций в карточке товара.",
    _number("product.related_limit", "Связанных товаров", 4, 0, 12),
    _toggle("product.related_same_category", "Сначала та же категория", True)),
  _section("catalog.archive", "Каталог", "Архив товаров",
    "Отображение неактивных позиций в рабочих списках.",
    _toggle("catalog.show_inactive_admin", "Показывать неактивные в админке", True),
    _toggle("catalog.allow_restore", "Разрешить восстановление товара", True)),
  _section("orders.retention", "Заказы", "История заявок",
    "Сроки хранения и доступ к завершённым заявкам.",
    _number("orders.history_days", "Период истории, дней", 365, 30, 3650),
    _toggle("orders.show_closed", "Показывать закрытые по умолчанию", False)),
  _section("content.preview", "Контент", "Предпросмотр публикаций",
    "Режим предварительного просмотра страниц и публикаций.",
    _select("content.preview_mode", "Режим предпросмотра", "desktop", [("Компьютер", "desktop"), ("Телефон", "mobile")]),
    _toggle("content.preview_show_drafts", "Разрешить предпросмотр черновиков", True)),
  _section("media.policy", "Каталог", "Правила медиа",
    "Размер изображений и требование заполнения подписи.",
    _number("media.max_size_mb", "Максимальный размер, МБ", 12, 1, 40),
    _toggle("media.require_alt", "Требовать текст подписи", False)),
  _section("integrations.webhooks", "Интеграции", "Веб-подключения",
    "Общие параметры внешних адресов и обработчиков.",
    _toggle("integrations.webhook_enabled", "Разрешить существующие обработчики", True),
    _number("integrations.timeout_seconds", "Тайм-аут, сек.", 10, 2, 60)),
  _section("integrations.api", "Интеграции", "API и внешние сервисы",
    "Безопасные параметры подключения. Секреты и ключи задаются только в Anvil Secrets или редакторе API.",
    _toggle("api.enabled", "Разрешить внешние API", True),
    _number("api.timeout_seconds", "Тайм-аут API, сек.", 30, 5, 120),
    _number("api.retry_count", "Повторных попыток", 2, 0, 5),
    _toggle("api.log_requests", "Записывать результат запроса в журнал", False),
    _toggle("api.reject_insecure", "Запрещать HTTP без HTTPS", True)),
  _section("integrations.media.storage", "Интеграции", "Хранилище изображений",
    "Определяет, куда отправляются изображения из PDF/XLSX и каталога. Ключи хранятся только на сервере.",
    _select("media.storage_primary", "Основное хранилище", "auto", [
      ("Автоматически · Cloudinary → ImageKit", "auto"),
      ("Cloudinary", "cloudinary"), ("ImageKit", "imagekit"),
      ("Не загружать во внешнее облако", "none")
    ]),
    _select("media.storage_fallback", "Резервное хранилище", "imagekit", [
      ("ImageKit", "imagekit"), ("Cloudinary", "cloudinary"),
      ("Без резерва", "none")
    ]),
    _toggle("media.external_uploads", "Загружать изображения во внешнее облако", True),
    _toggle("media.dedupe_by_checksum", "Не загружать одинаковые файлы повторно", True),
    _toggle("media.keep_local_copy", "Сохранять копию в Anvil Files", False),
    _number("media.upload_retries", "Повторов загрузки", 2, 0, 5),
    _text("media.folder_prefix", "Папка в облаке", "catalog/imports", maximum=80)),
  _section("ai.models", "ИИ и интеграции", "Модели и режимы AI",
    "Выбор поведения AI Studio и импорта. Конкретные API, модели и ключи редактируются в разделе «Настроить модели и API».",
    _select("ai.default_slot", "Основная модель", "primary", [
      ("Основной провайдер", "primary"), ("Резервный 1", "secondary"),
      ("Резервный 2", "third"), ("Локальная модель", "local")
    ]),
    _select("ai.fallback_slot", "Резервная модель", "secondary", [
      ("Резервный 1", "secondary"), ("Резервный 2", "third"),
      ("Основной провайдер", "primary"), ("Без резерва", "none")
    ]),
    _toggle("ai.vision_enabled", "Разрешить анализ изображений", True),
    _toggle("ai.catalog_drafts", "Разрешить черновики каталога", True),
    _toggle("ai.pdf_ocr", "Использовать AI/OCR для PDF", True),
    _number("ai.max_request_seconds", "Максимальное время запроса, сек.", 30, 5, 120)),
  _section("projects.objects", "Проекты", "Объекты и помещения",
    "Представление инженерных объектов и помещений.",
    _toggle("projects.show_objects", "Показывать объекты", True),
    _toggle("projects.show_rooms", "Показывать помещения", True)),
  _section("projects.systems", "Проекты", "Системы и оборудование",
    "Состав карточек систем и узлов.",
    _toggle("projects.show_components", "Показывать компоненты системы", True),
    _toggle("projects.show_connections", "Показывать связи оборудования", True)),
  _section("operations.estimates", "Рабочие процессы", "Сметы и предложения",
    "Формат и точность сметных значений.",
    _number("estimates.precision", "Знаков после запятой", 2, 0, 4),
    _toggle("estimates.show_source", "Показывать источник цены", True)),
  _section("operations.service", "Рабочие процессы", "Сервисные заявки",
    "Сроки и видимость обслуживания.",
    _number("service.default_reminder", "Напоминание, дней", 3, 0, 60),
    _toggle("service.show_status_public", "Показывать статус заявки клиенту", False)),
  _section("security.permissions", "Пользователи", "Права доступа",
    "Поведение проверки прав в интерфейсе управления.",
    _toggle("security.hide_forbidden_sections", "Скрывать разделы без прав", True),
    _toggle("security.audit_denied_actions", "Записывать отказанные действия", True)),
  _section("security.sessions", "Пользователи", "Сессии пользователей",
    "Отображение сеансов в пользовательском профиле.",
    _toggle("security.show_last_login", "Показывать дату последнего входа", True),
    _number("security.max_sessions", "Сеансов пользователя", 5, 1, 20)),
  _section("system.updates", "Система", "Версия и обновления",
    "Информация о версии и диагностике обновлений.",
    _toggle("system.show_version", "Показывать версию приложения", True),
    _toggle("system.update_notices", "Показывать сообщения об обновлении", True)),
  _section("system.data", "Система", "Работа с данными",
    "Настройки списков, предпросмотра и действий с данными.",
    _number("system.data_preview_limit", "Строк в предпросмотре", 100, 10, 500),
    _toggle("system.data_confirm_overwrite", "Подтверждать перезапись данных", True)),
  _section("system.widgets", "Система", "Виджеты и рабочий стол",
    "Дополнительные параметры выбранных виджетов.",
    _toggle("dashboard.show_empty", "Показывать виджеты с нулевыми значениями", False),
    _toggle("dashboard.show_descriptions", "Показывать пояснения виджетов", True)),
  _section("system.extensions.safety", "Система", "Безопасность расширений",
    "Ограничения размера и публичности браузерных расширений.",
    _number("extensions.max_active", "Активных расширений", 12, 1, 40),
    _toggle("extensions.show_public_warning", "Показывать предупреждение о публичном JS", True)),
  _section("system.backups", "Система", "Восстановление",
    "Параметры безопасного восстановления резервной копии.",
    _toggle("backup.confirm_restore", "Подтверждать восстановление", True),
    _toggle("backup.keep_current_copy", "Сохранять копию перед восстановлением", True)),
  _section("system.diagnostics", "Система", "Системная диагностика",
    "Уровень подробности системных сообщений.",
    _select("diagnostics.detail", "Подробность", "standard", [("Кратко", "brief"), ("Стандартно", "standard"), ("Подробно", "detailed")]),
    _toggle("diagnostics.check_media", "Проверять связи изображений", True)),
  _section("system.widgets.layout", "Система", "Макет Dashboard",
    "Размер и плотность сетки виджетов.",
    _number("dashboard.card_min_width", "Минимальная ширина карточки, px", 180, 120, 360),
    _select("dashboard.mobile_layout", "Телефон", "single", [("Одна колонка", "single"), ("Две колонки", "double")])),
  _section("import.pdf.pipeline", "Импорт и экспорт", "PDF · обработка каталога",
    "Ограничения и поведение фонового импорта PDF. Секреты облака и ИИ задаются только в Anvil.",
    _number("pdf.max_file_size_mb", "Максимальный размер PDF, МБ", 50, 1, 50),
    _number("pdf.max_pages", "Максимум страниц", 2000, 1, 2000),
    _number("pdf.pages_per_batch", "Страниц за один пакет", 10, 1, 50,
            "Пакеты сохраняют checkpoint и автоматически продолжаются фоновыми задачами."),
    _number("pdf.max_products", "Товаров в одном черновике", 1000, 1, 1000),
    _toggle("pdf.ocr_enabled", "Распознавать сканированные страницы через ИИ", True),
    _toggle("pdf.auto_cloud_media", "Загружать извлечённые изображения в облако", True),
    _number("pdf.max_images", "Изображений из одного файла", 300, 1, 300),
    _number("pdf.max_image_size_mb", "Размер одного изображения, МБ", 8, 1, 8),
    _number("pdf.max_total_image_size_mb", "Общий объём изображений, МБ", 30, 1, 30),
    _number("pdf.ai_chunk_chars", "Размер текстового фрагмента ИИ", 8500, 1000, 10500),
    _toggle("pdf.retain_source_for_review", "Хранить PDF до утверждения черновика", False),
    _toggle("pdf.resume_from_checkpoint", "Возобновлять обработку с checkpoint", True)),
  _section("ai.tools.content", "ИИ · инструменты", "ИИ · сайт и контент",
    "Выберите редакторы сайта, которые будут доступны в AI Studio.",
    _toggle("ai_tool.site_rewrite", "Редактор текста сайта", True),
    _toggle("ai_tool.site_seo", "SEO-заголовки и описание", True),
    _toggle("ai_tool.site_faq", "Создание FAQ по материалу", True),
    _toggle("ai_tool.site_headline", "Заголовки и кнопки блоков", True),
    _toggle("ai_tool.site_accessibility", "Проверка доступности контента", True),
    _toggle("ai_tool.site_translate", "Черновой перевод контента", True),
    _toggle("ai_tool.site_outline", "План структуры страницы", True)),
  _section("ai.tools.catalog", "ИИ · инструменты", "ИИ · каталог и товары",
    "ИИ помогает редактировать товарные карточки и подготовить данные к проверке.",
    _toggle("ai_tool.catalog_description", "Описание карточки товара", True),
    _toggle("ai_tool.catalog_specs", "Нормализация характеристик", True),
    _toggle("ai_tool.catalog_category", "Подбор категории каталога", True),
    _toggle("ai_tool.duplicate_review", "Проверка возможных дублей", True),
    _toggle("ai_tool.catalog_import_mapping", "Сопоставление полей импорта", True),
    _toggle("ai_tool.catalog_taxonomy_review", "Проверка дерева категорий", True)),
  _section("ai.tools.operations", "ИИ · инструменты", "ИИ · заявки и инженерные работы",
    "Инструменты готовят черновики для ручной проверки сотрудником.",
    _toggle("ai_tool.order_reply", "Черновик ответа клиенту", True),
    _toggle("ai_tool.order_summary", "Сводка заявки клиента", True),
    _toggle("ai_tool.commissioning", "Чек-лист пусконаладки", True),
    _toggle("ai_tool.quote_audit", "Проверка сметы и предложения", True),
    _toggle("ai_tool.admin_settings_advice", "Помощник по настройкам проекта", True),
    _toggle("ai_tool.admin_diagnostic", "Разбор системной диагностики", True),
    _toggle("ai_tool.pdf_import_triage", "Разбор ошибок импорта PDF", True))
]


def _widget(widget_id, label, group, description, table, kind="count",
            filters=None, default=False):
  return {
    "id": widget_id, "label": label, "group": group,
    "description": description, "table": table, "kind": kind,
    "filters": filters or {}, "default": default
  }


# A selectable catalog of 62 compact dashboard widgets. Counts are computed
# only for selected widgets, so activating more cards is an explicit choice.
WIDGET_CATALOG = [
  _widget("products_total", "Товары каталога", "Каталог", "Все записи товаров.", "products", default=True),
  _widget("products_active", "Активные товары", "Каталог", "Позиции, доступные в витрине.", "products", filters={"active": True}, default=True),
  _widget("products_inactive", "Скрытые товары", "Каталог", "Неактивные позиции в каталоге.", "products", filters={"active": False}),
  _widget("products_missing_images", "Без изображения", "Каталог", "Активные позиции без медиа.", "products", "missing_images", default=True),
  _widget("products_missing_description", "Без описания", "Каталог", "Активные позиции без описания.", "products", "missing_description"),
  _widget("categories_total", "Категории", "Каталог", "Все категории каталога.", "catalog_categories", default=True),
  _widget("categories_active", "Активные категории", "Каталог", "Категории, показанные посетителям.", "catalog_categories", filters={"active": True}),
  _widget("brands_total", "Бренды", "Каталог", "Бренды каталога.", "brands"),
  _widget("product_specs", "Характеристики", "Каталог", "Сохранённые характеристики товаров.", "product_specs"),
  _widget("product_prices", "Цены", "Каталог", "Записи с ценами каталога.", "product_prices"),
  _widget("stock_rows", "Остатки", "Каталог", "Позиции складского учёта.", "product_stock"),
  _widget("stock_low", "Низкий остаток", "Каталог", "Количество достигло минимального уровня.", "product_stock", "low_stock"),
  _widget("product_images", "Изображения товаров", "Медиа", "Записи медиа каталога.", "product_media"),
  _widget("media_objects", "Медиафайлы", "Медиа", "Метаданные файлов проекта.", "media_objects"),
  _widget("orders_total", "Все заявки каталога", "Заказы", "Сохранённые заявки на товары.", "catalog_orders"),
  _widget("orders_new", "Новые заявки", "Заказы", "Ожидают первого ответа.", "catalog_orders", filters={"status": "new"}, default=True),
  _widget("orders_processing", "В обработке", "Заказы", "Заявки, которые уже обрабатываются.", "catalog_orders", filters={"status": "processing"}),
  _widget("orders_completed", "Завершённые заявки", "Заказы", "Заявки со статусом завершения.", "catalog_orders", filters={"status": "completed"}),
  _widget("orders_cancelled", "Отменённые заявки", "Заказы", "Отменённые заявки каталога.", "catalog_orders", filters={"status": "cancelled"}),
  _widget("cms_pages", "Страницы CMS", "Контент", "Страницы в редакторе.", "cms_pages", default=True),
  _widget("cms_published", "Опубликованные страницы", "Контент", "Публичные страницы сайта.", "cms_pages", filters={"status": "published"}, default=True),
  _widget("cms_drafts", "Черновики страниц", "Контент", "Страницы, ожидающие публикации.", "cms_pages", filters={"status": "draft"}),
  _widget("cms_modules", "Блоки CMS", "Контент", "Сохранённые блоки страниц.", "cms_modules"),
  _widget("gallery_items", "Работы в галерее", "Контент", "Записи галереи проектов.", "gallery_items"),
  _widget("compatibility_rules", "Правила совместимости", "Каталог", "Сопоставления оборудования.", "compatibility"),
  _widget("crm_clients", "Клиенты CRM", "Рабочие процессы", "Клиентские карточки.", "crm_clients", default=True),
  _widget("crm_contacts", "Контакты", "Рабочие процессы", "Контакты клиентских карточек.", "crm_contacts"),
  _widget("crm_tasks_open", "Открытые задачи", "Рабочие процессы", "Задачи, требующие выполнения.", "crm_tasks", filters={"status": "open"}, default=True),
  _widget("crm_tasks_progress", "Задачи в работе", "Рабочие процессы", "Задачи со статусом выполнения.", "crm_tasks", filters={"status": "in_progress"}),
  _widget("crm_tasks_done", "Завершённые задачи", "Рабочие процессы", "Выполненные задачи CRM.", "crm_tasks", filters={"status": "done"}),
  _widget("quotes_total", "Коммерческие предложения", "Рабочие процессы", "Все предложения.", "quotes"),
  _widget("quotes_sent", "На согласовании", "Рабочие процессы", "Отправленные предложения.", "quotes", filters={"status": "sent"}),
  _widget("quotes_accepted", "Согласованные", "Рабочие процессы", "Принятые предложения.", "quotes", filters={"status": "accepted"}),
  _widget("estimates", "Сметы", "Рабочие процессы", "Сохранённые расчётные сметы.", "estimates"),
  _widget("estimate_lines", "Строки смет", "Рабочие процессы", "Позиции в сметах.", "estimate_lines"),
  _widget("service_total", "Сервисные записи", "Рабочие процессы", "Все работы по обслуживанию.", "service"),
  _widget("service_progress", "Сервис в работе", "Рабочие процессы", "Текущие сервисные работы.", "service", filters={"status": "in_progress"}),
  _widget("projects_total", "Проекты", "Проекты", "Инженерные проекты.", "projects", default=True),
  _widget("objects_total", "Объекты", "Проекты", "Адреса и объекты клиентов.", "objects"),
  _widget("systems_total", "Системы", "Проекты", "Проектируемые HVAC-системы.", "systems"),
  _widget("components_total", "Компоненты систем", "Проекты", "Узлы и оборудование в системах.", "system_components"),
  _widget("connections_total", "Связи систем", "Проекты", "Соединения инженерных компонентов.", "system_connections"),
  _widget("bom_total", "Спецификации материалов", "Проекты", "Строки ведомостей материалов.", "bom"),
  _widget("calculations_total", "Расчёты", "Проекты", "Сохранённые инженерные расчёты.", "calculations"),
  _widget("formulas_total", "Формулы", "Проекты", "Доступные расчётные формулы.", "formulas"),
  _widget("rooms_total", "Помещения", "Проекты", "Помещения инженерных объектов.", "rooms"),
  _widget("users_total", "Пользователи", "Пользователи", "Все учётные записи.", "users", default=True),
  _widget("users_enabled", "Активные пользователи", "Пользователи", "Учётные записи с доступом.", "users", filters={"enabled": True}),
  _widget("roles_total", "Роли доступа", "Пользователи", "Настроенные роли проекта.", "roles"),
  _widget("ai_providers", "Провайдеры AI", "Интеграции", "Настроенные модели и подключения.", "ai_providers"),
  _widget("ai_providers_enabled", "Активные провайдеры", "Интеграции", "Подключения, доступные оператору.", "ai_providers", filters={"enabled": True}),
  _widget("ai_usage_week", "AI-запросы за 7 дней", "Интеграции", "Недавняя активность AI-оператора.", "ai_usage", "recent", default=True),
  _widget("ai_usage_errors", "Ошибки AI", "Интеграции", "Запросы, завершившиеся ошибкой.", "ai_usage", filters={"status": "error"}),
  _widget("imports_total", "Импорты", "Импорт и экспорт", "Пакетные запуски импорта.", "imports"),
  _widget("imports_errors", "Ошибки импорта", "Импорт и экспорт", "Записи журнала импорта с ошибкой.", "import_logs", filters={"status": "error"}),
  _widget("audit_week", "События за 7 дней", "Система", "Недавние действия администраторов.", "audit_logs", "recent", default=True),
  _widget("audit_total", "Журнал действий", "Система", "Сохранённая история изменений.", "audit_logs"),
  _widget("settings_total", "Настройки системы", "Система", "Сохранённые системные параметры.", "system_settings"),
  _widget("stock_empty", "Нулевой остаток", "Каталог", "Позиции с нулевым остатком.", "product_stock", "zero_stock"),
  _widget("media_without_source", "Медиа без источника", "Медиа", "Файлы без указания источника.", "media_objects", "missing_source"),
  _widget("catalog_orders_today", "Заявки сегодня", "Заказы", "Новые заявки, полученные сегодня.", "catalog_orders", "today"),
  _widget("new_products_week", "Новые товары за 7 дней", "Каталог", "Недавно обновлённые позиции каталога.", "products", "updated_week")
]

_WIDGET_BY_ID = {widget["id"]: widget for widget in WIDGET_CATALOG}
_DEFAULT_WIDGET_IDS = [widget["id"] for widget in WIDGET_CATALOG if widget["default"]]
_SECTION_BY_ID = {section["id"]: section for section in SETTINGS_SECTIONS}

AI_TOOL_CATALOG = [
  {"id": "site_rewrite", "operation": "site_rewrite", "key": "ai_tool.site_rewrite",
   "group": "Сайт и контент", "title": "Редактор текста сайта",
   "description": "Редактирует текст, сохраняя факты и числа.",
   "input_hint": "Вставьте текст и укажите желаемый тон или длину."},
  {"id": "site_seo", "operation": "site_seo", "key": "ai_tool.site_seo",
   "group": "Сайт и контент", "title": "SEO-редактор",
   "description": "Готовит мета-заголовок и описание из исходного материала.",
   "input_hint": "Вставьте текст страницы и её основную тему."},
  {"id": "site_faq", "operation": "site_faq", "key": "ai_tool.site_faq",
   "group": "Сайт и контент", "title": "Создание FAQ",
   "description": "Составляет вопросы и ответы только по переданному содержимому.",
   "input_hint": "Вставьте материал страницы или статьи."},
  {"id": "site_headline", "operation": "site_headline", "key": "ai_tool.site_headline",
   "group": "Сайт и контент", "title": "Заголовки и кнопки",
   "description": "Предлагает варианты заголовков, подзаголовка и текста кнопки.",
   "input_hint": "Опишите блок, аудиторию и цель кнопки."},
  {"id": "site_accessibility", "operation": "site_accessibility", "key": "ai_tool.site_accessibility",
   "group": "Сайт и контент", "title": "Проверка доступности контента",
   "description": "Находит сложные формулировки и предлагает понятные текстовые улучшения.",
   "input_hint": "Вставьте текст или подписи элементов страницы."},
  {"id": "site_translate", "operation": "site_translate", "key": "ai_tool.site_translate",
   "group": "Сайт и контент", "title": "Черновой перевод",
   "description": "Переводит переданный фрагмент, сохраняя числа и технические обозначения.",
   "input_hint": "Укажите целевой язык и вставьте текст."},
  {"id": "site_outline", "operation": "site_outline", "key": "ai_tool.site_outline",
   "group": "Сайт и контент", "title": "План страницы",
   "description": "Предлагает иерархию заголовков и блоков из цели страницы.",
   "input_hint": "Опишите страницу, аудиторию и подтверждённые факты."},
  {"id": "catalog_description", "operation": "catalog_description", "key": "ai_tool.catalog_description",
   "group": "Каталог", "title": "Описание карточки товара",
   "description": "Собирает описание из названия и характеристик товара.",
   "input_hint": "Передайте модель, описание производителя и характеристики."},
  {"id": "catalog_specs", "operation": "catalog_specs", "key": "ai_tool.catalog_specs",
   "group": "Каталог", "title": "Нормализация характеристик",
   "description": "Находит повторяющиеся названия, несовпадающие единицы и пробелы.",
   "input_hint": "Вставьте список характеристик с исходными значениями."},
  {"id": "catalog_category", "operation": "catalog_category", "key": "ai_tool.catalog_category",
   "group": "Каталог", "title": "Подбор категории",
   "description": "Предлагает категорию по описанию, не создавая её автоматически.",
   "input_hint": "Опишите товар и перечислите допустимые категории."},
  {"id": "duplicate_review", "operation": "duplicate_review", "key": "ai_tool.duplicate_review",
   "group": "Каталог", "title": "Проверка возможных дублей",
   "description": "Сравнивает кандидатов и разделяет точные и вероятные совпадения.",
   "input_hint": "Вставьте модель и список похожих карточек."},
  {"id": "catalog_import_mapping", "operation": "catalog_import_mapping", "key": "ai_tool.catalog_import_mapping",
   "group": "Каталог", "title": "Сопоставление колонок импорта",
   "description": "Предлагает соответствия колонок файла полям каталога и отмечает неоднозначности.",
   "input_hint": "Вставьте заголовки файла и список доступных полей каталога."},
  {"id": "catalog_taxonomy_review", "operation": "catalog_taxonomy_review", "key": "ai_tool.catalog_taxonomy_review",
   "group": "Каталог", "title": "Проверка дерева категорий",
   "description": "Находит похожие названия и спорные уровни вложенности без изменения данных.",
   "input_hint": "Вставьте дерево категорий и опишите типы оборудования."},
  {"id": "order_reply", "operation": "order_reply", "key": "ai_tool.order_reply",
   "group": "Заявки и продажи", "title": "Черновик ответа клиенту",
   "description": "Создаёт ответ, оставляя неподтверждённые сведения для уточнения.",
   "input_hint": "Вставьте текст заявки и известные сведения о товаре."},
  {"id": "order_summary", "operation": "order_summary", "key": "ai_tool.order_summary",
   "group": "Заявки и продажи", "title": "Сводка заявки",
   "description": "Выделяет потребность, недостающие данные и следующий шаг.",
   "input_hint": "Вставьте заявку без секретных данных клиента."},
  {"id": "commissioning", "operation": "commissioning", "key": "ai_tool.commissioning",
   "group": "Инженерные работы", "title": "Чек-лист пусконаладки",
   "description": "Готовит список проверок по переданным моделям и проекту.",
   "input_hint": "Опишите систему, оборудование и условия объекта."},
  {"id": "quote_audit", "operation": "quote_audit", "key": "ai_tool.quote_audit",
   "group": "Инженерные работы", "title": "Проверка сметы",
   "description": "Ищет пропуски, единицы и арифметические расхождения.",
   "input_hint": "Вставьте строки сметы и исходные количества/цены."},
  {"id": "admin_settings_advice", "operation": "admin_settings_advice", "key": "ai_tool.admin_settings_advice",
   "group": "Администрирование", "title": "Помощник по настройкам",
   "description": "Составляет безопасный план настроек и объясняет последствия каждого изменения.",
   "input_hint": "Опишите нужный результат и текущие ограничения проекта."},
  {"id": "admin_diagnostic", "operation": "admin_diagnostic", "key": "ai_tool.admin_diagnostic",
   "group": "Администрирование", "title": "Разбор диагностики",
   "description": "Группирует ошибки и предлагает проверяемые шаги по переданному журналу.",
   "input_hint": "Вставьте текст ошибки и связанный фрагмент журнала."},
  {"id": "pdf_import_triage", "operation": "pdf_import_triage", "key": "ai_tool.pdf_import_triage",
   "group": "Администрирование", "title": "Разбор ошибок PDF-импорта",
   "description": "Разбирает предупреждения и ошибки черновика, не меняя его автоматически.",
   "input_hint": "Вставьте сообщения PDF-импорта и краткое описание источника."}
]
_AI_TOOL_BY_ID = {item["id"]: item for item in AI_TOOL_CATALOG}


def _state():
  row = app_tables.system_settings.get(key=STATE_KEY)
  value = row["value"] if row is not None else None
  if not isinstance(value, dict):
    return {}
  return dict(value)


def get_admin_studio_setting(key, default=None):
  """Read a non-secret Studio setting for trusted server modules."""
  state = _state()
  values = state.get("settings", {})
  return values.get(key, default) if isinstance(values, dict) else default


def get_public_navigation_settings():
  """Return only the public boolean options that control the site navigation."""
  values = _state().get("settings", {})
  if not isinstance(values, dict):
    values = {}
  defaults = {
    "catalog": True, "news": True, "projects": True, "account": True
  }
  keys = {
    "catalog": "navigation.catalog", "news": "navigation.news",
    "projects": "navigation.projects", "account": "header.show_account"
  }
  return {
    name: values.get(key) if isinstance(values.get(key), bool) else defaults[name]
    for name, key in keys.items()
  }


def _admin_ai_tools(state=None):
  state = state or _state()
  settings = state.get("settings", {})
  if not isinstance(settings, dict):
    settings = {}
  return [dict(item) for item in AI_TOOL_CATALOG
          if settings.get(item["key"], True) is not False]


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_admin_ai_tools():
  Core.require_admin_user()
  return {
    "ok": True, "tools": _admin_ai_tools(),
    "available_count": len(AI_TOOL_CATALOG)
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def run_admin_ai_tool(tool_id, source_text):
  actor = Core.require_admin_user()
  if not isinstance(tool_id, str) or tool_id not in _AI_TOOL_BY_ID:
    return {"ok": False, "message": "Выберите инструмент из списка."}
  tool = _AI_TOOL_BY_ID[tool_id]
  if tool not in _admin_ai_tools():
    return {"ok": False, "message": "Этот AI-инструмент отключён в настройках."}
  if not isinstance(source_text, str) or not source_text.strip():
    return {"ok": False, "message": "Добавьте исходный текст или данные для обработки."}
  if len(source_text) > 1900:
    return {"ok": False, "message": "Для одного запуска доступно до 1900 символов."}
  result = cast(Any, AI)._run_ai_operation(
    actor, tool["operation"], {"request": source_text.strip()},
    input_limit=2200, max_string=1900, max_items=8
  )
  if not result.get("ok"):
    Core.log_audit(
      actor=actor, action="ai.admin_tool.failed", entity_type="ai_tool",
      entity_id=tool_id, details={"status": "unavailable"},
      created_at=datetime.now(timezone.utc)
    )
    return {"ok": False, "message": result.get("message", "AI-инструмент не выполнил запрос."),
            "details": result.get("details", [])}
  answer = result.get("result")
  if isinstance(answer, str):
    answer_text = answer
  else:
    answer_text = json.dumps(answer, ensure_ascii=False, indent=2, allow_nan=False)
  Core.log_audit(
    actor=actor, action="ai.admin_tool.completed", entity_type="ai_tool",
    entity_id=tool_id, details={"provider": result.get("provider", "")},
    created_at=datetime.now(timezone.utc)
  )
  return {"ok": True, "answer": answer_text,
          "provider": result.get("provider", "")}


def _save_state(state, actor, action, details):
  now = datetime.now(timezone.utc)
  row = app_tables.system_settings.get(key=STATE_KEY)
  if row is None:
    app_tables.system_settings.add_row(
      key=STATE_KEY, value=state, updated_at=now, updated_by=actor
    )
  else:
    row.update(value=state, updated_at=now, updated_by=actor)
  Core.log_audit(
    actor=actor, action=action, entity_type="admin_studio",
    entity_id=STATE_KEY, details=details, created_at=now
  )


def _enabled_modules(state):
  stored = state.get("modules", {})
  if not isinstance(stored, dict):
    stored = {}
  return stored


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_admin_studio():
  state = _state()
  values = state.get("settings", {})
  if not isinstance(values, dict):
    values = {}
  modules = _enabled_modules(state)
  core = Core.get_system_settings()
  if core is None:
    raise anvil.server.PermissionDenied("Для просмотра настроек войдите как администратор.")
  sections = []
  for section in SETTINGS_SECTIONS:
    item = dict(section)
    item["enabled"] = modules.get(section["id"], True)
    item["fields"] = []
    for definition in section["fields"]:
      field = dict(definition)
      key = field["key"]
      if field["core_key"]:
        field["value"] = core.get(field["core_key"], field["default"])
      else:
        field["value"] = values.get(key, field["default"])
      item["fields"].append(field)
    sections.append(item)

  active_widgets = state.get("widgets", _DEFAULT_WIDGET_IDS)
  if not isinstance(active_widgets, list):
    active_widgets = list(_DEFAULT_WIDGET_IDS)
  selected_sizes = state.get("widget_sizes", {})
  if not isinstance(selected_sizes, dict):
    selected_sizes = {}
  widgets = []
  for definition in WIDGET_CATALOG:
    widget = dict(definition)
    widget["active"] = widget["id"] in active_widgets
    size = selected_sizes.get(widget["id"], "normal")
    widget["size"] = size if size in ("small", "normal", "wide") else "normal"
    widgets.append(widget)
  return {
    "ok": True, "sections": sections, "widgets": widgets,
    "extensions": state.get("extensions", [])
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_admin_media_storage_status():
  """Return safe, non-secret diagnostics for the configured image storage."""
  state = _state()
  values = state.get("settings", {})
  if not isinstance(values, dict):
    values = {}
  primary = values.get("media.storage_primary", "auto")
  fallback = values.get("media.storage_fallback", "imagekit")
  external_enabled = values.get("media.external_uploads", True) is not False
  cloudinary_ready = bool(
    Config.get_secret("CLOUDINARY_CLOUD_NAME") and
    Config.get_secret("CLOUDINARY_API_KEY") and
    Config.get_secret("CLOUDINARY_API_SECRET")
  )
  imagekit_ready = bool(Config.get_secret("IMAGEKIT_PRIVATE_KEY"))
  if not external_enabled or primary == "none":
    route = "Внешняя загрузка отключена"
  elif primary == "cloudinary":
    route = "Cloudinary" + (" → " + fallback if fallback != "none" else "")
  elif primary == "imagekit":
    route = "ImageKit" + (" → " + fallback if fallback != "none" else "")
  else:
    route = "Cloudinary → ImageKit"
  ready_names = []
  if cloudinary_ready:
    ready_names.append("Cloudinary")
  if imagekit_ready:
    ready_names.append("ImageKit")
  return {
    "ok": True,
    "primary": primary,
    "fallback": fallback,
    "route": route,
    "external_enabled": external_enabled,
    "cloudinary_ready": cloudinary_ready,
    "imagekit_ready": imagekit_ready,
    "ready": ready_names,
    "dedupe": values.get("media.dedupe_by_checksum", True) is not False,
    "secret_note": "Ключи не передаются в браузер. Настройте их в Anvil Secrets."
  }


def _validate_value(field, value):
  kind = field["type"]
  if kind == "bool":
    if not isinstance(value, bool):
      return None, "Проверьте значение «{}».".format(field["label"])
    return value, None
  if kind == "select":
    allowed = [choice[1] for choice in field["choices"]]
    if value not in allowed:
      return None, "Выберите допустимое значение для «{}».".format(field["label"])
    return value, None
  if kind == "number":
    if isinstance(value, bool):
      return None, "Укажите число для «{}».".format(field["label"])
    try:
      number = float(value)
    except (TypeError, ValueError):
      return None, "Укажите число для «{}».".format(field["label"])
    if not math.isfinite(number) or number < field["minimum"] or number > field["maximum"]:
      return None, "Значение «{}» должно быть от {} до {}.".format(
        field["label"], field["minimum"], field["maximum"]
      )
    return int(number) if number.is_integer() else number, None
  maximum = 2000 if kind == "textarea" else 500
  if not isinstance(value, str) or len(value) > maximum:
    return None, "Проверьте текст поля «{}» (до {} символов).".format(
      field["label"], maximum
    )
  value = value.strip()
  if kind == "url" and value:
    if not (value.startswith("https://") or value.startswith("/_/theme/")):
      return None, "В поле «{}» укажите HTTPS-ссылку или путь к ресурсу темы.".format(
        field["label"]
      )
  return value, None


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_admin_studio_section(section_id, values, enabled=True):
  if not isinstance(section_id, str):
    return {"ok": False, "message": "Раздел настроек не найден."}
  section = _SECTION_BY_ID.get(section_id)
  if section is None:
    return {"ok": False, "message": "Раздел настроек не найден."}
  if not isinstance(values, dict) or not isinstance(enabled, bool):
    return {"ok": False, "message": "Проверьте параметры раздела."}
  definitions = {field["key"]: field for field in section["fields"]}
  if set(values) - set(definitions):
    return {"ok": False, "message": "В запросе есть неизвестные настройки."}

  checked = {}
  for key, raw_value in values.items():
    value, error = _validate_value(definitions[key], raw_value)
    if error:
      return {"ok": False, "message": error}
    checked[key] = value

  actor = Core.require_admin_user()
  core_values = Core.get_system_settings()
  if core_values is None:
    raise anvil.server.PermissionDenied("Для изменения настроек войдите как администратор.")
  has_core_values = False
  for key, value in checked.items():
    core_key = definitions[key]["core_key"]
    if core_key:
      core_values[core_key] = value
      has_core_values = True
  if has_core_values:
    result = Core.save_system_settings(core_values)
    if not result["ok"]:
      return result

  state = _state()
  saved_settings = state.get("settings", {})
  if not isinstance(saved_settings, dict):
    saved_settings = {}
  for key, value in checked.items():
    if not definitions[key]["core_key"]:
      saved_settings[key] = value
  state["settings"] = saved_settings
  modules = _enabled_modules(state)
  modules[section_id] = enabled
  state["modules"] = modules
  if any(key in checked for key in (
    "extensions.allow_css", "extensions.allow_javascript"
  )):
    state["extension_revision"] = int(state.get("extension_revision", 0)) + 1
  _save_state(
    state, actor, "settings.studio.section_update",
    {"section": section_id, "keys": list(checked), "enabled": enabled}
  )
  return {"ok": True, "message": "Настройки раздела сохранены."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_admin_dashboard_widgets(widget_settings):
  if not isinstance(widget_settings, list) or len(widget_settings) > len(WIDGET_CATALOG):
    return {"ok": False, "message": "Некорректный список виджетов."}
  known = set(_WIDGET_BY_ID)
  active = []
  sizes = {}
  seen = set()
  allowed_sizes = {"small", "normal", "wide"}
  for item in widget_settings:
    if not isinstance(item, dict):
      return {"ok": False, "message": "Проверьте настройки каждого виджета."}
    widget_id = item.get("id")
    size = item.get("size", "normal")
    enabled = item.get("active", False)
    if not isinstance(widget_id, str) or widget_id not in known or widget_id in seen:
      return {"ok": False, "message": "Найден неизвестный или повторный виджет."}
    if not isinstance(size, str) or size not in allowed_sizes or not isinstance(enabled, bool):
      return {"ok": False, "message": "Проверьте размер и состояние виджета."}
    seen.add(widget_id)
    sizes[widget_id] = size
    if enabled:
      active.append(widget_id)
  if not active:
    return {"ok": False, "message": "Оставьте включённым хотя бы один виджет."}

  actor = Core.require_admin_user()
  state = _state()
  state["widgets"] = active
  state["widget_sizes"] = sizes
  _save_state(
    state, actor, "settings.studio.widgets_update", {"active": len(active)}
  )
  return {"ok": True, "message": "Рабочий стол обновлён: виджетов {}.".format(len(active))}


def _count_rows(table_name, filters=None, cache=None):
  filters = filters or {}
  cache_key = (
    table_name,
    tuple(sorted((key, repr(value)) for key, value in filters.items()))
  )
  if cache is not None and cache_key in cache:
    return cache[cache_key]
  table = getattr(app_tables, table_name, None)
  if table is None:
    if cache is not None:
      cache[cache_key] = None
    return None
  value = len(table.search(q.fetch_only(), **filters))
  if cache is not None:
    cache[cache_key] = value
  return value


def _product_image_ids(cache=None):
  if cache is not None and "product_image_ids" in cache:
    return cache["product_image_ids"]
  table = getattr(app_tables, "product_media", None)
  if table is None:
    if cache is not None:
      cache["product_image_ids"] = None
    return None
  image_ids = {
    row["product"].get_id()
    for row in table.search(q.fetch_only("product", "file_id", "url"))
    if row["product"] is not None and (row["file_id"] or row["url"])
  }
  if cache is not None:
    cache["product_image_ids"] = image_ids
  return image_ids


def _special_widget_value(definition, cache=None):
  if cache is None:
    cache = {}
  kind = definition["kind"]
  if kind in ("missing_images", "missing_description"):
    if "active_products" not in cache:
      table = getattr(app_tables, "products", None)
      cache["active_products"] = None if table is None else list(table.search(
        q.fetch_only("identity_key", "description"), active=True,
        identity_key=q.not_(q.ilike("demo|%"))
      ))
    products = cache["active_products"]
    if products is None:
      return None
    if kind == "missing_description":
      return sum(1 for row in products if not (row["description"] or "").strip())
    image_ids = _product_image_ids(cache)
    if image_ids is None:
      return None
    return sum(1 for row in products if row.get_id() not in image_ids)
  if kind in ("low_stock", "zero_stock"):
    if "stock_rows" not in cache:
      table = getattr(app_tables, "product_stock", None)
      cache["stock_rows"] = None if table is None else list(
        table.search(q.fetch_only("quantity", "minimum_stock"))
      )
    rows = cache["stock_rows"]
    if rows is None:
      return None
    if kind == "zero_stock":
      return sum(1 for row in rows if (row["quantity"] or 0) <= 0)
    return sum(
      1 for row in rows
      if row["minimum_stock"] is not None
      and (row["quantity"] or 0) <= row["minimum_stock"]
    )
  if kind == "recent":
    return _count_rows(definition["table"], {
      "created_at": q.greater_than(datetime.now(timezone.utc) - timedelta(days=7))
    }, cache)
  if kind == "today":
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return _count_rows(definition["table"], {"created_at": q.greater_than(start)}, cache)
  if kind == "updated_week":
    return _count_rows(definition["table"], {
      "updated_at": q.greater_than(datetime.now(timezone.utc) - timedelta(days=7))
    }, cache)
  if kind == "missing_source":
    cache_key = ("missing_source", definition["table"])
    if cache_key not in cache:
      table = getattr(app_tables, definition["table"], None)
      cache[cache_key] = None if table is None else sum(
        1 for row in table.search(q.fetch_only("source")) if not row["source"]
      )
    return cache[cache_key]
  return _count_rows(definition["table"], definition["filters"], cache)


def _admin_dashboard_widget_data(cache=None):
  state = _state()
  selected = state.get("widgets", _DEFAULT_WIDGET_IDS)
  if not isinstance(selected, list):
    selected = list(_DEFAULT_WIDGET_IDS)
  selected = [widget_id for widget_id in selected
              if isinstance(widget_id, str) and widget_id in _WIDGET_BY_ID]
  if not selected:
    selected = list(_DEFAULT_WIDGET_IDS)
  results = []
  count_cache = cache if isinstance(cache, dict) else {}
  for widget_id in selected:
    definition = _WIDGET_BY_ID[widget_id]
    value = _special_widget_value(definition, count_cache)
    item = {
      "id": widget_id, "label": definition["label"],
      "group": definition["group"], "description": definition["description"],
      "value": value if value is not None else "—",
      "available": value is not None
    }
    results.append(item)
  return {"widgets": results, "available_count": len(results)}


@anvil.server.callable(require_user=True)
@Core.staff_guard
def get_admin_dashboard_widgets():
  Core.require_staff_user()
  return {"ok": True, **_admin_dashboard_widget_data()}


def _clean_extensions(value):
  if not isinstance(value, list) or len(value) > 40:
    return None
  cleaned = []
  used_ids = set()
  for item in value:
    if not isinstance(item, dict):
      return None
    extension_id = item.get("id") or secrets.token_hex(8)
    title = item.get("title")
    kind = item.get("kind")
    description = item.get("description", "")
    code = item.get("code")
    enabled = item.get("enabled", False)
    if (
      not isinstance(extension_id, str)
      or not re.match(r"^[a-f0-9]{16}$", extension_id)
      or extension_id in used_ids
      or not isinstance(title, str) or not title.strip() or len(title.strip()) > 80
      or kind not in ("css", "javascript")
      or not isinstance(description, str) or len(description) > 240
      or not isinstance(code, str) or not code.strip() or len(code) > 12000
      or not isinstance(enabled, bool)
    ):
      return None
    used_ids.add(extension_id)
    cleaned.append({
      "id": extension_id, "title": title.strip(), "kind": kind,
      "description": description.strip(), "code": code,
      "enabled": enabled
    })
  return cleaned


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_admin_studio_extensions(extensions):
  cleaned = _clean_extensions(extensions)
  if cleaned is None:
    return {
      "ok": False,
      "message": "Проверьте название, тип и код. Допустимы CSS или JavaScript до 12 000 символов."
    }
  state = _state()
  settings = state.get("settings", {})
  max_active = settings.get("extensions.max_active", 12) if isinstance(settings, dict) else 12
  if isinstance(max_active, bool) or not isinstance(max_active, (int, float)) or not math.isfinite(max_active):
    max_active = 12
  max_active = max(1, min(int(max_active), 40))
  if sum(1 for item in cleaned if item["enabled"]) > max_active:
    return {
      "ok": False,
      "message": "Ограничение активных модулей — {}. Измените лимит в настройках расширений.".format(max_active)
    }
  actor = Core.require_admin_user()
  state["extensions"] = cleaned
  state["extension_revision"] = int(state.get("extension_revision", 0)) + 1
  _save_state(
    state, actor, "settings.studio.extensions_update",
    {"count": len(cleaned), "active": sum(1 for item in cleaned if item["enabled"])}
  )
  return {"ok": True, "message": "Расширения сохранены.", "extensions": cleaned}


@anvil.server.callable
def get_public_site_extensions():
  state = _state()
  settings = state.get("settings", {})
  if isinstance(settings, dict):
    if settings.get("extensions.allow_css") is False:
      allow_css = False
    else:
      allow_css = True
    allow_js = settings.get("extensions.allow_javascript") is not False
  else:
    allow_css = True
    allow_js = True
  extensions = state.get("extensions", [])
  if not isinstance(extensions, list):
    extensions = []
  public_items = []
  max_active = settings.get("extensions.max_active", 12) if isinstance(settings, dict) else 12
  if isinstance(max_active, bool) or not isinstance(max_active, (int, float)) or not math.isfinite(max_active):
    max_active = 12
  max_active = max(1, min(int(max_active), 40))
  for item in extensions:
    if not isinstance(item, dict) or not item.get("enabled"):
      continue
    if len(public_items) >= max_active:
      break
    if item.get("kind") == "css" and allow_css:
      public_items.append({"id": item["id"], "kind": "css", "code": item["code"]})
    elif item.get("kind") == "javascript" and allow_js:
      public_items.append({"id": item["id"], "kind": "javascript", "code": item["code"]})
  return {"revision": state.get("extension_revision", 0), "extensions": public_items}
