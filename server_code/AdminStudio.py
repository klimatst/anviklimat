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
import HisenseCatalogSync


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


def _number(key, label, default, minimum: Any = 0, maximum: Any = 1000, hint=""):
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
  ("01 · GRAPHITE BRUTAL · Чёрная сталь", "graphite"),
  ("02 · CARBON FIRE · Янтарный металл", "carbon-amber"),
  ("03 · CARBON RED · Красный титан", "carbon-red"),
  ("04 · ARCTIC PRO · Светлый лёд", "arctic-light"),
  ("05 · TITANIUM PRO · Светлый металл", "titanium-light")
]
_ON_OFF = [("Включено", "on"), ("Выключено", "off")]
_DENSITY = [("Компактно", "compact"), ("Стандартно", "standard"),
            ("Свободно", "spacious")]


# 107 editable settings sections, organized around the actual site and its
# existing catalogue, CMS, CRM, engineering and user-management features.
SETTINGS_SECTIONS = [
  _section("site.identity", "Сайт", "Профиль сайта",
    "Публичное имя и базовые данные компании.",
    _core("organization_name", "Название компании", "text", "КЛИМАЭКО"),
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
    _core("site_theme", "Цветовая тема", "select", "graphite", _THEMES),
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
  _section("engineering.installation.pricing", "Проекты", "Монтаж · цены и тарифы",
    "Редактор тарифов в формате проекта Lovable: валюта и 15 отдельных расценок работ. Материалы и цены товарного каталога остаются в едином редакторе каталога.",
    _core("currency", "Валюта цен", "select", "RUB", [("Рубли · RUB", "RUB"), ("Доллары · USD", "USD"), ("Евро · EUR", "EUR")]),
    _number("installation.pricing.acStandard", "Стандартный монтаж кондиционера, ₽", 8500, 0, 10000000),
    _number("installation.pricing.acPremium", "Сложный монтаж кондиционера, ₽", 12000, 0, 10000000),
    _number("installation.pricing.vrfMainRoute", "Магистраль VRV/VRF, ₽/м", 2800, 0, 1000000),
    _number("installation.pricing.vrfBranch", "Ответвление VRV/VRF, ₽", 4200, 0, 10000000),
    _number("installation.pricing.outdoorUnit", "Монтаж наружного блока, ₽", 6500, 0, 10000000),
    _number("installation.pricing.indoorUnit", "Монтаж внутреннего блока, ₽", 3500, 0, 10000000),
    _number("installation.pricing.commissioning", "Пусконаладка, ₽", 6500, 0, 10000000),
    _number("installation.pricing.pressureTest", "Опрессовка азотом, ₽", 3200, 0, 10000000),
    _number("installation.pricing.vacuum", "Вакуумирование, ₽", 1800, 0, 10000000),
    _number("installation.pricing.refrigerantCharge", "Дозаправка хладагентом, ₽/кг", 1200, 0, 1000000),
    _number("installation.pricing.electricalConnection", "Электрическое подключение, ₽", 2800, 0, 10000000),
    _number("installation.pricing.condensatePumpInstall", "Монтаж дренажной помпы, ₽", 4500, 0, 10000000),
    _number("installation.pricing.coreDrilling", "Алмазное бурение / проходка, ₽", 1800, 0, 10000000),
    _number("installation.pricing.liftHour", "Подъёмник / автовышка · час, ₽", 6500, 0, 10000000),
    _number("installation.pricing.scaffoldShift", "Леса / высота · смена, ₽", 4200, 0, 10000000)),
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
    "Максимальный размер изображения для ручной загрузки и импорта.",
    _number("media.max_size_mb", "Максимальный размер, МБ", 12, 1, 40)),
  _section("integrations.webhooks", "Интеграции", "Веб-подключения",
    "Общие параметры внешних адресов и обработчиков.",
    _toggle("integrations.webhook_enabled", "Разрешить существующие обработчики", True),
    _number("integrations.timeout_seconds", "Тайм-аут, сек.", 10, 2, 60)),
  _section("integrations.api", "Интеграции", "API и внешние сервисы",
    "Главный переключатель публичного API проекта. Адреса моделей, ключи и параметры подключений редактируются в разделе «Провайдеры и ключи».",
    _toggle("api.enabled", "Включить внешний API проекта", True)),
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
    _number("media.upload_retries", "Повторов загрузки", 2, 0, 5),
    _text("media.folder_prefix", "Папка в облаке", "catalog/imports", maximum=80)),
  _section("ventilation.page", "Вентиляция", "Вентиляция · страница и SEO",
    "Тексты, видимость блоков и SEO отдельной страницы расчёта вентиляции.",
    _text("ventilation.page_title", "Заголовок страницы", "Расчёт вентиляции", maximum=160),
    _text("ventilation.page_description", "Описание страницы", "Предварительный расчёт стоимости оборудования и монтажа вентиляции.", maximum=400),
    _text("ventilation.seo_title", "SEO Title", "Расчёт вентиляции · оборудование и монтаж", maximum=160),
    _text("ventilation.seo_description", "SEO Description", "Рассчитайте воздухообмен, оборудование и ориентировочную стоимость монтажа вентиляции.", maximum=300),
    _text("ventilation.seo_keywords", "SEO Keywords", "вентиляция, расчёт вентиляции, монтаж вентиляции, воздуховоды", maximum=300),
    _text("ventilation.primary_button", "Текст основной кнопки", "Рассчитать стоимость", maximum=80),
    _toggle("ventilation.show_types", "Показывать виды вентиляции", True),
    _toggle("ventilation.show_process", "Показывать этапы монтажа", True),
    _toggle("ventilation.show_faq", "Показывать FAQ", True),
    _toggle("ventilation.show_media", "Показывать изображения", True)),
  _section("ventilation.fields", "Вентиляция", "Вентиляция · поля и ограничения",
    "Подписи, единицы, обязательность, порядок и допустимые значения исходных данных. Дополнительные поля добавляются JSON-списком в разделе «Пользовательские поля».",
    _text("ventilation.label_area", "Подпись площади", "Площадь помещения", maximum=100),
    _text("ventilation.label_length", "Подпись длины", "Длина помещения", maximum=100),
    _text("ventilation.label_width", "Подпись ширины", "Ширина помещения", maximum=100),
    _text("ventilation.label_height", "Подпись высоты", "Высота потолка", maximum=100),
    _text("ventilation.label_people", "Подпись людей", "Количество людей", maximum=100),
    _text("ventilation.label_duct_length", "Подпись длины воздуховодов", "Длина воздуховодов", maximum=120),
    _text("ventilation.label_branches", "Подпись ответвлений", "Количество ответвлений", maximum=120),
    _select("ventilation.unit_area", "Единица площади", "м²", [("м²", "м²"), ("ft²", "ft²")]),
    _select("ventilation.unit_volume", "Единица объёма", "м³", [("м³", "м³"), ("ft³", "ft³")]),
    _select("ventilation.unit_flow", "Единица расхода", "м³/ч", [("м³/ч", "м³/ч"), ("л/с", "л/с")]),
    _number("ventilation.area_min", "Минимальная площадь", 10, 0.1, 100000),
    _number("ventilation.area_max", "Максимальная площадь", 5000, 1, 1000000),
    _number("ventilation.height_min", "Минимальная высота", 2, 0.5, 30),
    _number("ventilation.height_max", "Максимальная высота", 7, 1, 100),
    _number("ventilation.people_min", "Минимум людей", 1, 0, 100000),
    _number("ventilation.people_max", "Максимум людей", 5000, 1, 1000000),
    _number("ventilation.default_area", "Площадь по умолчанию", 120, 0.1, 100000),
    _number("ventilation.default_height", "Высота по умолчанию", 2.75, 0.5, 30),
    _number("ventilation.default_people", "Людей по умолчанию", 25, 0, 100000)),
  _section("ventilation.rules", "Вентиляция", "Вентиляция · формулы и коэффициенты",
    "Числовые нормы и правила расчёта. Изменения применяются сервером без изменения программного кода.",
    _number("ventilation.people_airflow", "Расход на человека, м³/ч", 40, 0, 1000),
    _number("ventilation.default_air_changes", "Кратность по умолчанию, 1/ч", 2.5, 0, 50),
    _number("ventilation.supply_factor", "Поправка притока", 1.0, 0, 10),
    _number("ventilation.exhaust_factor", "Поправка вытяжки", 1.0, 0, 10),
    _number("ventilation.fan_reserve_percent", "Резерв производительности, %", 15, 0, 200),
    _number("ventilation.duct_velocity", "Скорость в воздуховоде, м/с", 4, 0.1, 30),
    _number("ventilation.rounding_step", "Шаг округления цены, ₽", 10, 1, 100000),
    _number("ventilation.duct_rounding_step", "Шаг округления размера, мм", 5, 1, 100),
    _number("ventilation.heat_capacity", "Коэффициент тепла", 0.335, 0, 10),
    _number("ventilation.recovery_default", "Рекуперация по умолчанию, %", 70, 0, 100),
    _number("ventilation.cooling_capacity_per_unit", "Холодопроизводительность одного блока, кВт", 8, 0.1, 1000),
    _text("ventilation.formula_notes", "Пояснение формул", "V = S × H; Q = max(V × n, N × q); сечение = Q / (3600 × v).", maximum=600)),
  _section("ventilation.prices", "Вентиляция", "Вентиляция · цены и тарифы",
    "Все цены предварительной сметы редактируются здесь. Валюта — рубли; значения не используются другими калькуляторами.",
    _number("ventilation.price_equipment_base", "Базовая стоимость оборудования, ₽", 20000, 0, 100000000),
    _number("ventilation.price_automation", "Автоматика и электрика, ₽", 40000, 0, 100000000),
    _number("ventilation.price_ducts_m2", "Воздуховоды за погонный метр, ₽", 155, 0, 1000000),
    _number("ventilation.price_grille", "Одна решётка, ₽", 480, 0, 1000000),
    _number("ventilation.price_diffuser", "Один диффузор, ₽", 650, 0, 1000000),
    _number("ventilation.price_fan", "Один вентилятор, ₽", 18000, 0, 100000000),
    _number("ventilation.price_recovery", "Рекуператор, ₽", 85000, 0, 100000000),
    _number("ventilation.price_filter", "Фильтр, ₽", 6500, 0, 10000000),
    _number("ventilation.price_silencer", "Шумоглушитель, ₽", 8500, 0, 10000000),
    _number("ventilation.price_valve", "Клапан, ₽", 3200, 0, 10000000),
    _number("ventilation.price_cooling", "Охлаждающий блок, ₽", 45000, 0, 100000000),
    _number("ventilation.price_materials_percent", "Расходные материалы, %", 15, 0, 100),
    _number("ventilation.installation_percent", "Монтаж оборудования, %", 50, 0, 300),
    _number("ventilation.duct_installation_percent", "Монтаж воздуховодов, %", 80, 0, 300),
    _number("ventilation.commissioning_percent", "Пусконаладка, % от монтажа", 10, 0, 100),
    _number("ventilation.additional_percent", "Дополнительные расходы, %", 3, 0, 100)),
  _section("ventilation.types", "Вентиляция", "Вентиляция · типы и оборудование",
    "Добавляйте, отключайте и редактируйте типы помещений и систем через JSON. Поля name, code, air_changes и factor обязательны для расчёта.",
    _text("ventilation.room_types_json", "Типы помещений · JSON", '[{"code":"office","name":"Офисы","air_changes":2.5,"factor":1.5},{"code":"shop","name":"Магазины и ТЦ","air_changes":1.5,"factor":1.2},{"code":"production","name":"Производства","air_changes":2.5,"factor":1.0},{"code":"residential","name":"Квартиры и дома","air_changes":2.0,"factor":1.5}]', maximum=12000, kind="textarea"),
    _text("ventilation.system_types_json", "Типы вентиляции · JSON", '[{"code":"supply_exhaust","name":"Приточно-вытяжная","description":"Одновременно подаёт и удаляет воздух, поддерживая баланс потоков.","mode":"balanced","share":1.0,"enabled":true,"features":[]},{"code":"supply","name":"Приточная","description":"Подаёт наружный воздух с фильтрацией и подготовкой по проекту.","mode":"supply","share":0.6,"enabled":true,"features":[]},{"code":"exhaust","name":"Вытяжная","description":"Удаляет загрязнённый воздух, запахи и избыток влаги.","mode":"exhaust","share":0.4,"enabled":true,"features":[]},{"code":"recovery","name":"С рекуперацией","description":"Передаёт тепло удаляемого воздуха приточному потоку.","mode":"balanced","share":1.0,"enabled":true,"features":["recovery"]},{"code":"cooling","name":"С охлаждением","description":"Добавляет охлаждающий блок в предварительную смету системы.","mode":"balanced","share":1.0,"enabled":true,"features":["cooling"]}]', maximum=12000, kind="textarea"),
    _text("ventilation.equipment_json", "Оборудование · JSON", '[{"code":"fan","name":"Вентилятор","price_key":"ventilation.price_fan","enabled":true},{"code":"recovery","name":"Рекуператор","price_key":"ventilation.price_recovery","enabled":true},{"code":"cooling","name":"Охлаждающий блок","price_key":"ventilation.price_cooling","enabled":true},{"code":"filter","name":"Фильтр","price_key":"ventilation.price_filter","enabled":true},{"code":"silencer","name":"Шумоглушитель","price_key":"ventilation.price_silencer","enabled":true},{"code":"valve","name":"Клапан","price_key":"ventilation.price_valve","enabled":true},{"code":"grille","name":"Решётка","price_key":"ventilation.price_grille","enabled":true},{"code":"diffuser","name":"Диффузор","price_key":"ventilation.price_diffuser","enabled":true},{"code":"automation","name":"Автоматика","price_key":"ventilation.price_automation","enabled":true}]', maximum=12000, kind="textarea"),
    _text("ventilation.custom_fields_json", "Пользовательские поля · JSON", '[]', maximum=12000, kind="textarea"),
    _text("ventilation.custom_units_json", "Пользовательские единицы · JSON", '[]', maximum=8000, kind="textarea")),
  _section("ventilation.results", "Вентиляция", "Вентиляция · результаты и порядок",
    "Управляйте подписями, единицами, видимостью и порядком карточек. Итоговая стоимость всегда выделяется вверху страницы.",
    _text("ventilation.result_schema_json", "Схема результатов · JSON", '[{"key":"volume","label":"Объём помещения","unit":"м³","visible":true,"order":10},{"key":"air_exchange","label":"Необходимый воздухообмен","unit":"м³/ч","visible":true,"order":20},{"key":"supply","label":"Приточный расход","unit":"м³/ч","visible":true,"order":30},{"key":"exhaust","label":"Вытяжной расход","unit":"м³/ч","visible":true,"order":40},{"key":"fan","label":"Производительность установки","unit":"м³/ч","visible":true,"order":50},{"key":"cooling_capacity","label":"Расчётная холодопроизводительность","unit":"кВт","visible":true,"order":55},{"key":"recovery_power","label":"Тепловая мощность рекуперации","unit":"кВт","visible":true,"order":57},{"key":"duct","label":"Сечение воздуховода","unit":"мм","visible":true,"order":60},{"key":"equipment_cost","label":"Оборудование","unit":"₽","visible":true,"order":70},{"key":"installation_cost","label":"Монтаж","unit":"₽","visible":true,"order":80},{"key":"additional_cost","label":"Дополнительные расходы","unit":"₽","visible":true,"order":85},{"key":"total","label":"Итого","unit":"₽","visible":true,"order":90}]', maximum=16000, kind="textarea"),
    _toggle("ventilation.show_breakdown", "Показывать расшифровку", True),
    _toggle("ventilation.show_prices", "Показывать цены по строкам", True),
    _toggle("ventilation.show_units", "Показывать единицы измерения", True)),
  _section("ventilation.content", "Вентиляция", "Вентиляция · тексты и FAQ",
    "Редактируйте блоки страницы, преимущества, этапы и вопросы без изменения кода.",
    _text("ventilation.advantages_json", "Преимущества · JSON", '[{"title":"Расчёт по параметрам объекта","text":"Учитываются площадь, высота, люди и выбранный тип системы."},{"title":"Прозрачная смета","text":"Оборудование, воздуховоды, монтаж и дополнительные расходы показаны отдельно."}]', maximum=12000, kind="textarea"),
    _text("ventilation.process_json", "Этапы работ · JSON", '[{"title":"Осмотр","text":"Уточнение назначения зон и ограничений объекта."},{"title":"Проектирование","text":"Подбор оборудования и трасс по расчётным расходам."},{"title":"Монтаж и запуск","text":"Установка, автоматика, проверка и наладка."}]', maximum=12000, kind="textarea"),
    _text("ventilation.faq_json", "FAQ · JSON", '[{"question":"Что входит в систему вентиляции?","answer":"Оборудование, фильтры, автоматика, воздуховоды и воздухораспределители по проекту."},{"question":"Почему цена уточняется после обследования?","answer":"На итог влияют трассы, проходки, высотные работы, шумовые требования и строительная готовность."}]', maximum=12000, kind="textarea"),
    _text("ventilation.images_json", "Изображения страницы · JSON", '[]', maximum=12000, kind="textarea")),
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
,
  _section("design.visual.system", "Дизайн", "Visual Design System",
    "Центральное управление визуальным языком всего продукта.",
    _select("design.visual.preset", "Визуальный характер", "engineering", [("Engineering Premium", "engineering"), ("Industrial Pro", "industrial"), ("Luxury Minimal", "luxury"), ("Technical Dark", "technical")]),
    _select("design.visual.radius", "Радиус интерфейса", "medium", [("Sharp", "sharp"), ("Compact", "compact"), ("Medium", "medium"), ("Soft", "soft")]),
    _select("design.visual.depth", "Глубина поверхностей", "premium", [("Flat", "flat"), ("Balanced", "balanced"), ("Premium", "premium")]),
    _toggle("design.visual.micro_details", "Инженерные микроэлементы", True),
    _toggle("design.visual.glow", "Акцентное свечение", True)),
  _section("design.layout", "Дизайн", "Layout Studio",
    "Управление сеткой, шириной контента и плотностью страниц.",
    _number("design.layout.max_width", "Максимальная ширина, px", 1440, 960, 2200),
    _number("design.layout.page_gap", "Межсекционный интервал, px", 32, 8, 100),
    _select("design.layout.grid", "Сетка", "12", [("8 колонок", "8"), ("12 колонок", "12"), ("16 колонок", "16")]),
    _toggle("design.layout.full_bleed", "Разрешить full-width блоки", True),
    _toggle("design.layout.sticky_actions", "Закреплять основные действия", True)),
  _section("design.components", "Дизайн", "Component Studio",
    "Единые правила кнопок, карточек, таблиц, badges и состояний.",
    _select("design.components.buttons", "Стиль кнопок", "premium", [("Minimal", "minimal"), ("Premium", "premium"), ("Industrial", "industrial")]),
    _select("design.components.cards", "Стиль карточек", "elevated", [("Flat", "flat"), ("Elevated", "elevated"), ("Glass", "glass")]),
    _select("design.components.badges", "Стиль статусов", "solid", [("Outline", "outline"), ("Soft", "soft"), ("Solid", "solid")]),
    _toggle("design.components.hover_lift", "Подъём карточек при наведении", True),
    _toggle("design.components.image_zoom", "Увеличение изображений", True)),
  _section("design.hero", "Дизайн", "Hero & Landing Studio",
    "Редактор поведения первых экранов и промо-секций.",
    _select("design.hero.layout", "Композиция Hero", "split", [("Split", "split"), ("Centered", "centered"), ("Asymmetric", "asymmetric")]),
    _select("design.hero.visual", "Визуальный режим", "engineering", [("Engineering", "engineering"), ("Editorial", "editorial"), ("Minimal", "minimal")]),
    _toggle("design.hero.show_metrics", "Показывать ключевые показатели", True),
    _toggle("design.hero.show_grid", "Показывать инженерную сетку", True),
    _toggle("design.hero.parallax", "Лёгкий parallax", False)),
  _section("design.motion", "Дизайн", "Motion Studio",
    "Единая система анимаций и переходов.",
    _select("design.motion.level", "Интенсивность", "medium", [("Off", "off"), ("Subtle", "subtle"), ("Medium", "medium"), ("Cinematic", "cinematic")]),
    _select("design.motion.page_transition", "Переход страниц", "fade-up", [("None", "none"), ("Fade", "fade"), ("Fade Up", "fade-up"), ("Scale", "scale")]),
    _number("design.motion.duration", "Базовая длительность, ms", 280, 80, 900),
    _toggle("design.motion.stagger", "Последовательная анимация сеток", True),
    _toggle("design.motion.reduced_motion", "Уважать reduced-motion", True)),
  _section("design.mobile", "Дизайн", "Mobile Experience",
    "Отдельные правила мобильного интерфейса.",
    _select("design.mobile.navigation", "Мобильная навигация", "drawer", [("Drawer", "drawer"), ("Bottom Bar", "bottom"), ("Compact Header", "header")]),
    _select("design.mobile.cards", "Карточки на мобильном", "single", [("1 колонка", "single"), ("2 колонки", "double")]),
    _toggle("design.mobile.compact_tables", "Компактные таблицы", True),
    _toggle("design.mobile.sticky_cta", "Закреплённый CTA", True)),
  _section("content.visual-editor", "Контент", "Visual Page Builder",
    "Расширенный конструктор контентных секций.",
    _toggle("content.builder.sections", "Разрешить секции", True),
    _toggle("content.builder.reorder", "Перетаскивание секций", True),
    _toggle("content.builder.preview", "Live Preview", True),
    _toggle("content.builder.duplicate", "Дублирование блоков", True),
    _toggle("content.builder.templates", "Шаблоны блоков", True)),
  _section("seo.advanced", "SEO", "SEO Control Center",
    "Расширенное управление поисковой оптимизацией.",
    _toggle("seo.advanced.schema", "Structured Data", True),
    _toggle("seo.advanced.breadcrumbs", "Breadcrumb Schema", True),
    _toggle("seo.advanced.sitemap", "Автоматическая карта сайта", True),
    _toggle("seo.advanced.canonical", "Автоматические canonical", True),
    _toggle("seo.advanced.noindex_drafts", "Noindex для черновиков", True)),
  _section("performance.control", "Система", "Performance Control",
    "Управление скоростью и загрузкой ресурсов.",
    _toggle("performance.lazy_images", "Lazy Load изображений", True),
    _toggle("performance.webp", "Предпочитать WebP", True),
    _toggle("performance.preload_hero", "Preload главного изображения", True),
    _toggle("performance.minimize_motion", "Уменьшать motion на слабых устройствах", True),
    _number("performance.image_quality", "Качество изображений, %", 84, 50, 100)),
  _section("security.control", "Безопасность", "Security Control Center",
    "Центральные политики безопасности.",
    _toggle("security.require_2fa", "Требовать 2FA для администраторов", False),
    _toggle("security.session_limit", "Ограничивать длительность сессии", True),
    _number("security.session_hours", "Сессия, часов", 12, 1, 168),
    _toggle("security.audit_sensitive", "Расширенный аудит", True),
    _toggle("security.block_repeated_failures", "Защита от повторных попыток входа", True)),
  _section("workflow.automation", "Рабочие процессы", "Workflow Automation",
    "Автоматизация типовых операций команды.",
    _toggle("workflow.auto_assign", "Автоматически назначать ответственного", False),
    _toggle("workflow.order_notifications", "Автоуведомления по заявкам", True),
    _toggle("workflow.task_reminders", "Напоминания по задачам", True),
    _toggle("workflow.status_history", "История изменения статусов", True)),
  _section("dashboard.pro", "Dashboard", "Command Center Dashboard",
    "Профессиональный рабочий стол администратора.",
    _select("dashboard.pro.density", "Плотность Dashboard", "dense", [("Compact", "compact"), ("Balanced", "balanced"), ("Dense", "dense")]),
    _toggle("dashboard.pro.kpi", "KPI-панели", True),
    _toggle("dashboard.pro.activity", "Лента активности", True),
    _toggle("dashboard.pro.health", "System Health", True),
    _toggle("dashboard.pro.quick_actions", "Быстрые действия", True),
    _toggle("dashboard.pro.realtime", "Realtime-индикаторы", True)),
  _section("system.diagnostics.pro", "Система", "Advanced Diagnostics",
    "Глубокая диагностика приложения.",
    _toggle("diagnostics.runtime", "Проверять runtime", True),
    _toggle("diagnostics.data_integrity", "Проверять целостность данных", True),
    _toggle("diagnostics.catalog", "Проверять каталог", True),
    _toggle("diagnostics.images", "Проверять изображения", True),
    _toggle("diagnostics.calculators", "Проверять калькуляторы", True),
    _toggle("diagnostics.links", "Проверять внутренние ссылки", True)),
  _section("admin.workspace", "Система", "Admin Workspace",
    "Персонализация рабочего пространства администратора.",
    _select("admin.workspace.theme", "Тема панели", "inherit", [("Как сайт", "inherit"), ("Graphite", "graphite"), ("Arctic", "arctic"), ("Titanium", "titanium")]),
    _select("admin.workspace.sidebar", "Sidebar", "expanded", [("Expanded", "expanded"), ("Compact", "compact"), ("Auto", "auto")]),
    _toggle("admin.workspace.command_palette", "Command Palette", True),
    _toggle("admin.workspace.keyboard_shortcuts", "Горячие клавиши", True),
    _toggle("admin.workspace.breadcrumbs", "Breadcrumbs", True)),
  _section("admin.branding", "Система", "Admin Branding",
    "Фирменное оформление Control Center.",
    _text("admin.branding.title", "Название панели", "КЛИМАЭКО CONTROL CENTER", maximum=80),
    _text("admin.branding.subtitle", "Подзаголовок", "ENGINEERING MANAGEMENT PLATFORM", maximum=120),
    _toggle("admin.branding.status", "Показывать System Status", True),
    _toggle("admin.branding.version", "Показывать версию", True)),

  _section("erp.sales", "ERP", "Продажи · воронка",
    "Управление этапами продаж, ответственными, сроками и коммерческими предложениями.",
    _text("erp.sales.stages_json", "Этапы воронки · JSON", '[{"code":"lead","name":"Новый лид"},{"code":"qualification","name":"Квалификация"},{"code":"proposal","name":"Коммерческое предложение"},{"code":"negotiation","name":"Переговоры"},{"code":"won","name":"Сделка выиграна"},{"code":"lost","name":"Сделка проиграна"}]', maximum=12000, kind="textarea"),
    _toggle("erp.sales.auto_stage", "Автоматически менять этап по действиям", True),
    _toggle("erp.sales.deadline_alerts", "Контролировать просроченные сделки", True)),
  _section("erp.inventory", "ERP", "Склад · остатки и контроль",
    "Центральные правила складского контроля каталога.",
    _toggle("erp.inventory.low_stock_alerts", "Уведомлять о низком остатке", True),
    _toggle("erp.inventory.zero_stock_alerts", "Уведомлять о нулевом остатке", True),
    _toggle("erp.inventory.reserve_orders", "Резервировать товар при заявке", False),
    _number("erp.inventory.default_reserve_days", "Срок резерва, дней", 3, 1, 90)),
  _section("erp.procurement", "ERP", "Закупки и поставки",
    "Контроль потребности, поставщиков и сроков поставки.",
    _toggle("erp.procurement.enabled", "Включить закупочный контур", True),
    _toggle("erp.procurement.supplier_tracking", "Учитывать поставщиков", True),
    _toggle("erp.procurement.delivery_tracking", "Контролировать сроки поставки", True),
    _number("erp.procurement.alert_days", "Предупреждать за дней", 3, 0, 60)),
  _section("erp.finance", "ERP", "Финансы и маржинальность",
    "Управление финансовыми показателями без доступа к секретам платёжных систем.",
    _toggle("erp.finance.margin", "Показывать маржинальность", True),
    _toggle("erp.finance.cost_price", "Учитывать себестоимость", True),
    _toggle("erp.finance.tax", "Учитывать налог", False),
    _number("erp.finance.default_tax_percent", "Налог по умолчанию, %", 20, 0, 100)),
  _section("erp.analytics", "ERP", "BI · аналитика бизнеса",
    "Ключевые показатели продаж, каталога, сервиса и эффективности команды.",
    _toggle("erp.analytics.sales", "Аналитика продаж", True),
    _toggle("erp.analytics.catalog", "Аналитика каталога", True),
    _toggle("erp.analytics.service", "Аналитика сервиса", True),
    _toggle("erp.analytics.team", "Аналитика команды", True)),
  _section("erp.documents", "ERP", "Документы и шаблоны",
    "Правила подготовки смет, КП, актов и внутренних документов.",
    _toggle("erp.documents.quotes", "Коммерческие предложения", True),
    _toggle("erp.documents.estimates", "Сметы", True),
    _toggle("erp.documents.service", "Сервисные документы", True),
    _toggle("erp.documents.versioning", "Версионировать документы", True)),
  _section("erp.team", "ERP", "Команда и роли",
    "Роли, зоны ответственности и контроль доступа к операциям.",
    _toggle("erp.team.role_scopes", "Ограничивать доступ по ролям", True),
    _toggle("erp.team.audit_actions", "Аудит действий сотрудников", True),
    _toggle("erp.team.assignment", "Назначение ответственных", True)),
  _section("cms.workflow", "CMS", "Контент · workflow",
    "Полный цикл подготовки контента: черновик, проверка, публикация и архив.",
    _toggle("cms.workflow.review", "Обязательная проверка перед публикацией", True),
    _toggle("cms.workflow.versioning", "Хранить версии страниц", True),
    _toggle("cms.workflow.scheduled", "Отложенная публикация", True),
    _toggle("cms.workflow.archive", "Архивировать старые версии", True)),
  _section("cms.blocks", "CMS", "Контент · библиотека блоков",
    "Управление переиспользуемыми секциями и шаблонами сайта.",
    _toggle("cms.blocks.reusable", "Переиспользуемые блоки", True),
    _toggle("cms.blocks.templates", "Шаблоны страниц", True),
    _toggle("cms.blocks.preview", "Предпросмотр перед публикацией", True),
    _toggle("cms.blocks.duplicate", "Дублирование блоков", True))
]


SECRET_CATALOG = [
  {"name": "CLOUDINARY_CLOUD_NAME", "provider": "Cloudinary", "label": "Имя облака", "hint": "Cloudinary Product Environment / cloud name", "kind": "text"},
  {"name": "CLOUDINARY_API_KEY", "provider": "Cloudinary", "label": "API-ключ", "hint": "Публичный API-ключ Cloudinary", "kind": "secret"},
  {"name": "CLOUDINARY_API_SECRET", "provider": "Cloudinary", "label": "API-секрет", "hint": "Секретный API Secret из Cloudinary. Key Name не подходит.", "kind": "secret"},
  {"name": "IMAGEKIT_PRIVATE_KEY", "provider": "ImageKit", "label": "Private key", "hint": "Секретный ключ загрузки ImageKit", "kind": "secret"},
  {"name": "IMAGEKIT_PUBLIC_KEY", "provider": "ImageKit", "label": "Public key", "hint": "Публичный ключ ImageKit", "kind": "text"},
  {"name": "IMAGEKIT_URL_ENDPOINT", "provider": "ImageKit", "label": "URL endpoint", "hint": "HTTPS endpoint CDN ImageKit", "kind": "url"},
  {"name": "GITHUB_CATALOG_TOKEN", "provider": "GitHub", "label": "Токен публикации фото каталога", "hint": "Fine-grained token с правом Contents: Read and write для репозитория каталога. Хранится как секрет Anvil.", "kind": "secret"},
  {"name": "OPENROUTER_API_KEY", "provider": "AI", "label": "OpenRouter API key", "hint": "Ключ провайдера моделей AI", "kind": "secret"},
  {"name": "OPENAI_API_KEY", "provider": "AI", "label": "OpenAI API key", "hint": "Ключ OpenAI для совместимого API", "kind": "secret"},
  {"name": "ANTHROPIC_API_KEY", "provider": "AI", "label": "Anthropic API key", "hint": "Ключ Anthropic для интеграции", "kind": "secret"},
  {"name": "TELEGRAM_BOT_TOKEN", "provider": "Уведомления", "label": "Telegram bot token", "hint": "Токен Telegram-бота", "kind": "secret"},
  {"name": "SMTP_USERNAME", "provider": "Почта", "label": "SMTP username", "hint": "Пользователь SMTP", "kind": "text"},
  {"name": "SMTP_PASSWORD", "provider": "Почта", "label": "SMTP password", "hint": "Пароль SMTP", "kind": "secret"},
  {"name": "GOOGLE_MAPS_API_KEY", "provider": "Карты", "label": "Google Maps API key", "hint": "Ключ карт и геокодирования", "kind": "secret"},
  {"name": "SENTRY_DSN", "provider": "Диагностика", "label": "Sentry DSN", "hint": "Адрес сбора ошибок", "kind": "url"},
  {"name": "WEBHOOK_SIGNING_SECRET", "provider": "Интеграции", "label": "Webhook signing secret", "hint": "Подпись входящих webhook", "kind": "secret"},
  {"name": "ERP_API_KEY", "provider": "ERP", "label": "ERP API key", "hint": "Ключ учётной системы", "kind": "secret"},
  {"name": "ERP_API_URL", "provider": "ERP", "label": "ERP API URL", "hint": "HTTPS адрес ERP API", "kind": "url"},
  {"name": "PAYMENT_API_KEY", "provider": "Оплата", "label": "Payment API key", "hint": "Ключ платёжного сервиса", "kind": "secret"},
  {"name": "PAYMENT_API_SECRET", "provider": "Оплата", "label": "Payment API secret", "hint": "Секрет платёжного сервиса", "kind": "secret"},
  {"name": "SEARCH_API_KEY", "provider": "Поиск", "label": "Search API key", "hint": "Ключ внешнего поиска", "kind": "secret"}
]
_SECRET_BY_NAME = {item["name"]: item for item in SECRET_CATALOG}


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
    route = "Cloudinary" + (" → " + fallback if fallback not in ("none", "cloudinary") else "")
  ready_names = []
  if cloudinary_ready:
    ready_names.append("Cloudinary")
  if imagekit_ready:
    ready_names.append("ImageKit")
  ready_text = ", ".join(ready_names) or "нет настроенного облака"
  cloudinary_required = (
    "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"
  )
  missing_cloudinary = [
    name for name in cloudinary_required if not Config.get_secret(name)
  ]
  media_counts = {}
  external_media_count = _count_rows("media_objects", cache=media_counts)
  product_media_count = _count_rows("product_media", cache=media_counts)
  manual_media_note = (
    "Ручные фото карточек хранятся в Data Table product_media (Anvil Media), "
    "записей: {}. "
  ).format(product_media_count if product_media_count is not None else "—")
  if not external_enabled or primary == "none":
    destination = manual_media_note + "Загрузка фото PDF/XLSX во внешнее облако отключена."
  else:
    destination = (
      manual_media_note +
      "Фото PDF/XLSX отправляются по маршруту {}. URL и контрольные суммы: "
      "Data Table media_objects, записей: {}. Доступно: {}."
    ).format(
      route,
      external_media_count if external_media_count is not None else "—",
      ready_text
    )
  return {
    "ok": True,
    "primary": primary,
    "fallback": fallback,
    "route": route,
    "external_enabled": external_enabled,
    "cloudinary_ready": cloudinary_ready,
    "cloudinary_missing": missing_cloudinary,
    "imagekit_ready": imagekit_ready,
    "ready": ready_names,
    "dedupe": values.get("media.dedupe_by_checksum", True) is not False,
    "destination": destination,
    "credentials": (
      "Cloudinary: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, "
      "CLOUDINARY_API_SECRET. ImageKit: IMAGEKIT_PRIVATE_KEY. "
      "Product Environment у Cloudinary используется как cloud name; Key Name не является API secret. "
      "Добавьте нужные ключи в этой панели или в Anvil → Services → Secrets. "
      "Ключи не передаются в браузер."
    )
  }


def _admin_secret_status(item):
  name = item["name"]
  managed = bool(Config.get_managed_secret(name))
  native = False
  try:
    import anvil.secrets as secrets_service
  except ImportError:
    secrets_service = None
  if secrets_service is not None:
    try:
      native = bool(secrets_service.get_secret(name))
    except secrets_service.SecretError:
      native = False
  source = "Панельное хранилище" if managed else ("Anvil Secrets" if native else "Не настроен")
  return {
    **item,
    "configured": managed or native,
    "source": source,
    "display": "Настроен · значение скрыто" if managed or native else "Не настроен"
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_admin_secrets():
  Core.require_admin_user()
  return {
    "ok": True,
    "secrets": [_admin_secret_status(item) for item in SECRET_CATALOG],
    "policy": "Значения шифруются ключом приложения и никогда не возвращаются в браузер."
  }


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_admin_secret(secret_name, secret_value):
  actor = Core.require_admin_user()
  item = _SECRET_BY_NAME.get(secret_name)
  if item is None:
    return {"ok": False, "message": "Выберите секрет из разрешённого списка."}
  if item["kind"] == "url" and not (
    isinstance(secret_value, str) and secret_value.startswith("https://")
  ):
    return {"ok": False, "message": "URL секрета должен начинаться с https://."}
  result = Config.set_managed_secret(secret_name, secret_value, actor=actor)
  if result["ok"]:
    Core.log_audit(
      actor=actor, action="settings.secret.saved", entity_type="secret",
      entity_id=secret_name, details={"provider": item["provider"]},
      created_at=datetime.now(timezone.utc)
    )
  return result


@anvil.server.callable(require_user=True)
@Core.admin_guard
def clear_admin_secret(secret_name):
  actor = Core.require_admin_user()
  if secret_name not in _SECRET_BY_NAME:
    return {"ok": False, "message": "Выберите секрет из разрешённого списка."}
  result = Config.clear_managed_secret(secret_name, actor=actor)
  if result["ok"]:
    Core.log_audit(
      actor=actor, action="settings.secret.cleared", entity_type="secret",
      entity_id=secret_name, details={}, created_at=datetime.now(timezone.utc)
    )
  return result


@anvil.server.callable(require_user=True)
@Core.admin_guard
def test_admin_secret_group(provider):
  Core.require_admin_user()
  names = [item["name"] for item in SECRET_CATALOG if item["provider"] == provider]
  if not names:
    return {"ok": False, "message": "Группа подключения не найдена."}
  statuses = [_admin_secret_status(_SECRET_BY_NAME[name]) for name in names]
  configured = sum(1 for item in statuses if item["configured"])
  required = {
    "Cloudinary": {"CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"},
    "ImageKit": {"IMAGEKIT_PRIVATE_KEY"},
    "AI": {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
  }.get(provider, set())
  configured_names = {item["name"] for item in statuses if item["configured"]}
  ready = required.issubset(configured_names) if provider == "Cloudinary" else bool(
    required.intersection(configured_names)
  )
  missing = sorted(required - configured_names)
  return {
    "ok": True, "provider": provider, "configured": configured,
    "total": len(statuses), "ready": ready, "missing": missing,
    "message": "Подключение готово к использованию по наличию ключей." if ready
      else "Не настроены: {}.".format(", ".join(missing) or "обязательный ключ")
  }


_VENTILATION_JSON_ARRAYS = {
  "ventilation.room_types_json": "rooms",
  "ventilation.system_types_json": "systems",
  "ventilation.equipment_json": "equipment",
  "ventilation.custom_fields_json": "fields",
  "ventilation.custom_units_json": "units",
  "ventilation.result_schema_json": "results",
  "ventilation.advantages_json": "advantages",
  "ventilation.process_json": "process",
  "ventilation.faq_json": "faq",
  "ventilation.images_json": "images"
}
_VENTILATION_RESULT_KEYS = {
  "volume", "air_exchange", "supply", "exhaust", "fan", "duct",
  "cooling_capacity", "recovery_power", "equipment_cost", "installation_cost",
  "additional_cost", "total"
}
_VENTILATION_PRICE_KEYS = {
  "ventilation.price_equipment_base", "ventilation.price_automation",
  "ventilation.price_ducts_m2", "ventilation.price_grille",
  "ventilation.price_diffuser", "ventilation.price_fan",
  "ventilation.price_recovery", "ventilation.price_cooling",
  "ventilation.price_filter", "ventilation.price_silencer",
  "ventilation.price_valve"
}
_VENTILATION_EQUIPMENT_CODES = {
  "fan", "recovery", "cooling", "filter", "silencer", "valve",
  "grille", "diffuser", "automation"
}


def _normalise_ventilation_json_setting(key, value):
  try:
    rows = json.loads(value)
  except (TypeError, ValueError):
    return None, "Поле «{}» должно содержать корректный JSON-массив.".format(key)
  if not isinstance(rows, list) or len(rows) > 200:
    return None, "В поле «{}» ожидается массив не более чем из 200 элементов.".format(key)
  kind = _VENTILATION_JSON_ARRAYS[key]
  if kind in ("rooms", "systems", "equipment") and not rows:
    return None, "В поле «{}» должен оставаться хотя бы один элемент.".format(key)

  if kind == "fields":
    normalised, error = _normalise_ventilation_custom_fields(rows)
    if error:
      return None, error
    rows = normalised
  elif kind in ("rooms", "systems", "equipment", "results"):
    seen = set()
    for row in rows:
      if not isinstance(row, dict):
        return None, "Каждая запись в «{}» должна быть объектом.".format(key)
      code_key = "key" if kind == "results" else "code"
      code = row.get(code_key)
      name_key = "label" if kind == "results" else "name"
      name = row.get(name_key)
      if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", code):
        return None, "В поле «{}» указан некорректный код.".format(key)
      if code in seen:
        return None, "Код «{}» в поле «{}» повторяется.".format(code, key)
      seen.add(code)
      if code in ("__dict__", "__class__"):
        return None, "В поле «{}» указан запрещённый код.".format(key)
      if not isinstance(name, str) or not name.strip() or len(name) > 160:
        return None, "В поле «{}» задайте подпись длиной до 160 символов.".format(key)
      if kind == "rooms":
        for field_name, minimum, maximum in (("air_changes", 0, 100), ("factor", 0, 20)):
          raw_number = row.get(field_name)
          if isinstance(raw_number, bool):
            return None, "В поле «{}» проверьте числовое значение {}.".format(key, field_name)
          try:
            number = float(str(raw_number))
          except (TypeError, ValueError):
            return None, "В поле «{}» проверьте числовое значение {}.".format(key, field_name)
          if not math.isfinite(number) or number < minimum or number > maximum:
            return None, "Значение {} в поле «{}» должно быть от {} до {}.".format(
              field_name, key, minimum, maximum
            )
          row[field_name] = number
      elif kind == "systems":
        raw_share = row.get("share")
        if isinstance(raw_share, bool):
          return None, "В поле «{}» проверьте долю стоимости.".format(key)
        try:
          share = float(str(raw_share))
        except (TypeError, ValueError):
          return None, "В поле «{}» проверьте долю стоимости.".format(key)
        if not math.isfinite(share) or share < 0 or share > 10:
          return None, "Доля стоимости вентиляции должна быть от 0 до 10." 
        if not isinstance(row.get("enabled", True), bool):
          return None, "В поле «{}» признак enabled должен быть логическим.".format(key)
        features = row.get("features", [])
        if (not isinstance(features, list)
            or any(item not in ("recovery", "cooling") for item in features)
            or len(set(features)) != len(features)):
          return None, "В поле «{}» допустимы функции recovery и cooling.".format(key)
        mode = row.get("mode")
        if mode is None:
          mode = {"supply": "supply", "exhaust": "exhaust"}.get(code, "balanced")
        if mode not in ("balanced", "supply", "exhaust"):
          return None, "Для типа «{}» выберите balanced, supply или exhaust.".format(name)
        description = row.get("description", "")
        if not isinstance(description, str) or len(description) > 500:
          return None, "Описание типа вентиляции должно содержать до 500 символов." 
        row["mode"] = mode
        row["share"] = share
      elif kind == "equipment":
        if code not in _VENTILATION_EQUIPMENT_CODES:
          return None, "В поле «{}» указан неизвестный элемент оборудования {}.".format(key, code)
        if row.get("price_key") not in _VENTILATION_PRICE_KEYS:
          return None, "В поле «{}» указана неизвестная цена оборудования.".format(key)
        if not isinstance(row.get("enabled", True), bool):
          return None, "В поле «{}» признак enabled должен быть логическим.".format(key)
      else:
        if code not in _VENTILATION_RESULT_KEYS:
          return None, "В поле «{}» указан неизвестный результат {}.".format(key, code)
        unit = row.get("unit", "")
        if not isinstance(unit, str) or len(unit) > 30:
          return None, "Единица результата «{}» должна содержать до 30 символов.".format(code)
        if not isinstance(row.get("visible", True), bool):
          return None, "Видимость результата «{}» должна быть Да или Нет.".format(code)
        order = row.get("order", 0)
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
          return None, "Порядок результата «{}» должен быть неотрицательным целым числом.".format(code)
  elif kind in ("advantages", "process", "faq"):
    seen = set()
    title_key, body_key = ("question", "answer") if kind == "faq" else ("title", "text")
    for row in rows:
      if not isinstance(row, dict):
        return None, "Каждый элемент «{}» должен быть объектом.".format(key)
      title = row.get(title_key)
      body = row.get(body_key)
      if not isinstance(title, str) or not title.strip() or len(title) > 160:
        return None, "В поле «{}» проверьте заголовок.".format(key)
      if title in seen:
        return None, "Заголовок «{}» в поле «{}» повторяется.".format(title, key)
      if not isinstance(body, str) or not body.strip() or len(body) > 2000:
        return None, "В поле «{}» проверьте текст.".format(key)
      seen.add(title)
  elif kind == "images":
    for row in rows:
      image = row if isinstance(row, str) else row.get("url") if isinstance(row, dict) else None
      if not isinstance(image, str) or len(image) > 1000 or not (
        image.startswith("https://") or image.startswith("/_/theme/")
      ):
        return None, "Изображения должны быть HTTPS-ссылками или ресурсами темы Anvil." 
      if isinstance(row, dict) and len(str(row.get("alt", ""))) > 240:
        return None, "Подпись изображения должна содержать до 240 символов." 
  elif kind == "units":
    seen = set()
    for row in rows:
      if not isinstance(row, dict):
        return None, "Каждая единица измерения должна быть объектом." 
      code, title = row.get("code"), row.get("label")
      if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", code) or code in seen:
        return None, "Коды единиц измерения должны быть уникальными." 
      if not isinstance(title, str) or not title.strip() or len(title) > 30:
        return None, "Название единицы должно содержать до 30 символов." 
      seen.add(code)
  return json.dumps(rows, ensure_ascii=False, separators=(",", ":")), None


def _ventilation_settings_consistency(settings):
  ranges = (
    ("ventilation.area_min", "ventilation.area_max", "ventilation.default_area", "площади"),
    ("ventilation.height_min", "ventilation.height_max", "ventilation.default_height", "высоты")
  )
  for minimum_key, maximum_key, default_key, label in ranges:
    minimum = settings[minimum_key]
    maximum = settings[maximum_key]
    default = settings[default_key]
    if minimum > maximum:
      return "Минимум {} не может превышать максимум.".format(label)
    if default < minimum or default > maximum:
      return "Значение {} по умолчанию должно находиться между минимумом и максимумом.".format(label)
  minimum = settings["ventilation.people_min"]
  maximum = settings["ventilation.people_max"]
  default = settings["ventilation.default_people"]
  if minimum > maximum:
    return "Минимум людей не может превышать максимум."
  if default < minimum or default > maximum:
    return "Количество людей по умолчанию должно находиться между минимумом и максимумом."
  return None


def _check_ventilation_settings_patch(checked, state=None):
  coupled = {
    "ventilation.area_min", "ventilation.area_max", "ventilation.default_area",
    "ventilation.height_min", "ventilation.height_max", "ventilation.default_height",
    "ventilation.people_min", "ventilation.people_max", "ventilation.default_people"
  }
  if not coupled.intersection(checked):
    return None
  candidate = {
    field["key"]: field["default"]
    for section in SETTINGS_SECTIONS if section["id"].startswith("ventilation.")
    for field in section["fields"]
  }
  state = state if isinstance(state, dict) else _state()
  current = state.get("settings", {})
  if isinstance(current, dict):
    candidate.update({key: value for key, value in current.items() if key in candidate})
  candidate.update({key: value for key, value in checked.items() if key in candidate})
  return _ventilation_settings_consistency(candidate)


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
    if field["key"] in ("ventilation.people_min", "ventilation.people_max", "ventilation.default_people") and not number.is_integer():
      return None, "Значение «{}» должно быть целым числом.".format(field["label"])
    return int(number) if number.is_integer() else number, None
  maximum = field.get("maximum")
  if isinstance(maximum, bool) or not isinstance(maximum, int):
    maximum = 2000 if kind == "textarea" else 500
  if not isinstance(value, str) or len(value) > maximum:
    return None, "Проверьте текст поля «{}» (до {} символов).".format(
      field["label"], maximum
    )
  value = value.strip()
  if field["key"] == "media.folder_prefix":
    parts = value.strip("/").split("/")
    if (not value or len(value) > 80 or any(
      not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", part) for part in parts
    )):
      return None, "Укажите папку облака латинскими буквами, цифрами, дефисами и /."
    value = "/".join(parts)
  if kind == "url" and value:
    if not (value.startswith("https://") or value.startswith("/_/theme/")):
      return None, "В поле «{}» укажите HTTPS-ссылку или путь к ресурсу темы.".format(
        field["label"]
      )
  if field["key"] in _VENTILATION_JSON_ARRAYS:
    return _normalise_ventilation_json_setting(field["key"], value)
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

  consistency_error = _check_ventilation_settings_patch(checked)
  if consistency_error:
    return {"ok": False, "message": consistency_error}

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


_VENTILATION_CUSTOM_FIELD_TYPES = {"text", "number", "select", "bool"}


def _normalise_ventilation_custom_fields(fields):
  if not isinstance(fields, list) or len(fields) > 100:
    return None, "Добавьте от 0 до 100 пользовательских полей."
  result = []
  seen = set()
  for position, field in enumerate(fields):
    if not isinstance(field, dict):
      return None, "Каждое пользовательское поле должно быть объектом."
    code = str(field.get("code", "")).strip().lower()
    label = str(field.get("label", "")).strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", code):
      return None, "Код поля должен содержать 2–40 латинских символов, цифр и _."
    if code in seen:
      return None, "Код поля «{}» повторяется.".format(code)
    if not label or len(label) > 120:
      return None, "Укажите название поля длиной до 120 символов."
    kind = str(field.get("type", "text"))
    if kind not in _VENTILATION_CUSTOM_FIELD_TYPES:
      return None, "Для поля «{}» выбран неизвестный тип.".format(label)
    unit = str(field.get("unit", "")).strip()[:30]
    description = str(field.get("description", "")).strip()[:240]
    raw_choices = field.get("choices", [])
    if isinstance(raw_choices, str):
      raw_choices = [item.strip() for item in raw_choices.split(",") if item.strip()]
    if not isinstance(raw_choices, list):
      raw_choices = []
    choices = [str(item).strip()[:80] for item in raw_choices if str(item).strip()][:50]
    if len(set(choices)) != len(choices):
      return None, "Варианты поля «{}» не должны повторяться.".format(label)
    if kind == "select" and not choices:
      return None, "Добавьте хотя бы один вариант для поля «{}».".format(label)
    default = field.get("default", False if kind == "bool" else "")
    if kind == "number" and default not in ("", None):
      if isinstance(default, bool):
        return None, "Значение по умолчанию поля «{}» должно быть числом.".format(label)
      try:
        default = float(default)
        if not math.isfinite(default):
          raise ValueError
        if default.is_integer():
          default = int(default)
      except (TypeError, ValueError):
        return None, "Значение по умолчанию поля «{}» должно быть числом.".format(label)
    elif kind == "bool":
      if isinstance(default, str) and default.strip().casefold() in ("", "false", "true"):
        default = default.strip().casefold() == "true"
      elif not isinstance(default, bool):
        return None, "Значение по умолчанию поля «{}» должно быть Да или Нет.".format(label)
      default = bool(default)
    else:
      default = str(default or "")[:500]
    minimum = field.get("minimum")
    maximum = field.get("maximum")
    for value, name in ((minimum, "минимум"), (maximum, "максимум")):
      if value in (None, ""):
        continue
      if isinstance(value, bool):
        return None, "Поле «{}»: {} должно быть числом.".format(label, name)
      try:
        number = float(value)
        if not math.isfinite(number):
          raise ValueError
      except (TypeError, ValueError):
        return None, "Поле «{}»: {} должно быть числом.".format(label, name)
    if minimum not in (None, "") and maximum not in (None, "") and float(minimum) > float(maximum):
      return None, "Для поля «{}» минимум не может быть больше максимума.".format(label)
    if kind == "number" and default not in ("", None):
      numeric_default = float(str(default))
      if minimum not in (None, "") and numeric_default < float(str(minimum)):
        return None, "Значение по умолчанию поля «{}» ниже минимума.".format(label)
      if maximum not in (None, "") and numeric_default > float(str(maximum)):
        return None, "Значение по умолчанию поля «{}» выше максимума.".format(label)
    if kind == "select" and default not in ("", None) and default not in choices:
      return None, "Значение по умолчанию поля «{}» отсутствует в списке вариантов.".format(label)
    required = field.get("required", False)
    visible = field.get("visible", True)
    if not isinstance(required, bool) or not isinstance(visible, bool):
      return None, "Обязательность и видимость поля «{}» должны быть логическими значениями.".format(label)
    raw_order = field.get("order", position * 10 + 10)
    if isinstance(raw_order, bool):
      return None, "Порядок поля «{}» должен быть неотрицательным целым числом.".format(label)
    try:
      numeric_order = float(str(raw_order))
    except (TypeError, ValueError):
      return None, "Порядок поля «{}» должен быть неотрицательным целым числом.".format(label)
    if not math.isfinite(numeric_order) or numeric_order < 0 or not numeric_order.is_integer():
      return None, "Порядок поля «{}» должен быть неотрицательным целым числом.".format(label)
    order = int(numeric_order)
    result.append({
      "code": code, "label": label, "description": description, "unit": unit,
      "type": kind, "required": required,
      "visible": visible,
      "minimum": None if minimum in (None, "") else float(minimum),
      "maximum": None if maximum in (None, "") else float(maximum),
      "default": default, "choices": choices,
      "order": order
    })
    seen.add(code)
  return result, None


def _ventilation_settings_snapshot(state=None):
  state = state or _state()
  settings = state.get("settings", {})
  if not isinstance(settings, dict):
    settings = {}
  snapshot = {}
  for section in SETTINGS_SECTIONS:
    if not section["id"].startswith("ventilation."):
      continue
    for field in section["fields"]:
      if not field["key"].startswith("ventilation."):
        continue
      snapshot[field["key"]] = settings.get(field["key"], field["default"])
  return snapshot


@anvil.server.callable(require_user=True)
@Core.admin_guard
def get_ventilation_custom_fields():
  value = get_admin_studio_setting("ventilation.custom_fields_json", "[]")
  try:
    fields = json.loads(value) if isinstance(value, str) else []
  except (TypeError, ValueError):
    fields = []
  normalised, error = _normalise_ventilation_custom_fields(fields)
  return {"ok": error is None, "fields": normalised or [],
          "message": error or "Пользовательские поля загружены."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def save_ventilation_custom_fields(fields):
  checked, error = _normalise_ventilation_custom_fields(fields)
  if error:
    return {"ok": False, "message": error}
  actor = Core.require_admin_user()
  state = _state()
  settings = state.get("settings", {})
  if not isinstance(settings, dict):
    settings = {}
  settings["ventilation.custom_fields_json"] = json.dumps(
    checked, ensure_ascii=False, separators=(",", ":")
  )
  state["settings"] = settings
  _save_state(state, actor, "settings.ventilation.custom_fields_update",
              {"count": len(checked or [])})
  return {"ok": True, "fields": checked,
          "message": "Пользовательские поля вентиляции сохранены."}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def export_ventilation_settings():
  return {"ok": True, "version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
          "settings": _ventilation_settings_snapshot()}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def import_ventilation_settings(payload):
  if not isinstance(payload, dict):
    return {"ok": False, "message": "Импорт должен содержать объект настроек."}
  incoming = payload.get("settings", payload)
  if not isinstance(incoming, dict):
    return {"ok": False, "message": "В файле импорта нет раздела settings."}
  allowed = {field["key"]: field for section in SETTINGS_SECTIONS
             if section["id"].startswith("ventilation.")
             for field in section["fields"]}
  unknown = [key for key in incoming if key not in allowed]
  if unknown:
    return {"ok": False, "message": "Файл содержит неизвестные настройки: {}.".format(
      ", ".join(unknown[:5]))}
  checked = {}
  for key, value in incoming.items():
    checked_value, error = _validate_value(allowed[key], value)
    if error:
      return {"ok": False, "message": error}
    checked[key] = checked_value
  state = _state()
  consistency_error = _check_ventilation_settings_patch(checked, state)
  if consistency_error:
    return {"ok": False, "message": consistency_error}
  actor = Core.require_admin_user()
  settings = state.get("settings", {})
  if not isinstance(settings, dict):
    settings = {}
  settings.update(checked)
  state["settings"] = settings
  _save_state(state, actor, "settings.ventilation.import",
              {"keys": list(checked)})
  return {"ok": True, "message": "Настройки вентиляции импортированы.",
          "settings": _ventilation_settings_snapshot(state)}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def backup_ventilation_settings():
  actor = Core.require_admin_user()
  state = _state()
  backups = state.get("ventilation_backups", [])
  if not isinstance(backups, list):
    backups = []
  backup = {"created_at": datetime.now(timezone.utc).isoformat(),
            "settings": _ventilation_settings_snapshot(state)}
  backups.insert(0, backup)
  state["ventilation_backups"] = backups[:20]
  _save_state(state, actor, "settings.ventilation.backup",
              {"count": len(state["ventilation_backups"])})
  return {"ok": True, "message": "Резервная копия настроек создана.",
          "backups": [{"created_at": item.get("created_at", "")} for item in state["ventilation_backups"]]}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def list_ventilation_backups():
  backups = _state().get("ventilation_backups", [])
  if not isinstance(backups, list):
    backups = []
  return {"ok": True, "backups": [{"created_at": item.get("created_at", ""),
                                    "index": index}
                                   for index, item in enumerate(backups)]}


@anvil.server.callable(require_user=True)
@Core.admin_guard
def restore_ventilation_backup(index):
  if isinstance(index, bool) or not isinstance(index, int) or index < 0:
    return {"ok": False, "message": "Выберите резервную копию."}
  actor = Core.require_admin_user()
  state = _state()
  backups = state.get("ventilation_backups", [])
  if not isinstance(backups, list) or index >= len(backups):
    return {"ok": False, "message": "Резервная копия не найдена."}
  snapshot = backups[index].get("settings", {})
  if not isinstance(snapshot, dict):
    return {"ok": False, "message": "Резервная копия повреждена."}
  allowed = {field["key"]: field for section in SETTINGS_SECTIONS
             if section["id"].startswith("ventilation.")
             for field in section["fields"]}
  checked_snapshot = {}
  for key, value in snapshot.items():
    if key not in allowed:
      return {"ok": False, "message": "Резервная копия содержит неизвестную настройку."}
    checked_value, error = _validate_value(allowed[key], value)
    if error:
      return {"ok": False, "message": "Резервная копия повреждена: {}".format(error)}
    checked_snapshot[key] = checked_value
  snapshot = checked_snapshot
  consistency_error = _check_ventilation_settings_patch(snapshot, state)
  if consistency_error:
    return {"ok": False, "message": "Резервная копия содержит противоречивые ограничения: {}".format(consistency_error)}
  settings = state.get("settings", {})
  if not isinstance(settings, dict):
    settings = {}
  settings.update(snapshot)
  state["settings"] = settings
  _save_state(state, actor, "settings.ventilation.restore",
              {"index": index})
  return {"ok": True, "message": "Настройки восстановлены из резервной копии."}


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
