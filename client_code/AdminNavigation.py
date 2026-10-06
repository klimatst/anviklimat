"""Shared admin navigation data for the dashboard and persistent sidebar."""


MENU = {
  "catalog": {
    "title": "Каталог и товарные данные",
    "intro": "Категории, карточки, цены, совместимость и импорт из PDF/таблиц.",
    "options": [
      ("Заявки каталога", "Catalog.Orders", {"window_title": "Заявки каталога"}, "catalog.manage"),
      ("Медиа и товары без фото", "Catalog.Media", {"window_title": "Медиа каталога"}, "catalog.manage"),
      ("Категории", "Catalog.Taxonomy", {"window_title": "Категории каталога", "category_view": "categories"}, "catalog.manage"),
      ("Подкатегории", "Catalog.Taxonomy", {"window_title": "Подкатегории каталога", "category_view": "subcategories"}, "catalog.manage"),
      ("Бренды и поля каталога", "Catalog.Taxonomy", {"window_title": "Справочники каталога", "category_view": "all"}, "catalog.manage"),
      ("Каталог · товары и цены", "Catalog", {"window_title": "Каталог · товары и цены"}, "catalog.manage"),
      ("Структура каталога · категории и бренды", "Catalog.Taxonomy", {"window_title": "Структура каталога"}, "catalog.manage"),
      ("Черновики импорта · 50 на страницу", "ImportEngine", {"window_title": "Черновики каталога", "drafts_only": True}, "import.manage"),
      ("Импорт каталога · PDF и таблицы", "ImportEngine", {"window_title": "Импорт каталога"}, "import.manage"),
      ("Совместимость оборудования", "Compatibility", {"window_title": "Совместимость"}, "catalog.manage")
    ]
  },
  "content": {
    "title": "Контент и страницы",
    "intro": "Редактор новостей, публикаций, страниц и галерея проектов.",
    "options": [
      ("Новости и CMS", "CMS", {"window_title": "CMS · новости и страницы"}, "cms.manage"),
      ("Меню сайта", "SiteMenu", {"window_title": "Меню сайта"}, "cms.manage"),
      ("Галерея проектов", "Gallery", {"window_title": "Галерея работ"}, "gallery.manage")
    ]
  },
  "engineering": {
    "title": "Инженерные инструменты",
    "intro": "Расчёты, коэффициенты, монтажные сметы и проекты.",
    "options": [
      ("Формулы и инженерные расчёты", "Calculations", {"window_title": "Формулы и коэффициенты", "window_key": "calculations:admin", "module_code": "engineering", "open_formula_editor": True}, "calculations.manage"),
      ("Вентиляция · страница, формулы и цены", "AdminSettings", {"window_title": "Управление · Вентиляция", "start_section": "ventilation.page", "open_editor": True}, "calculations.manage"),
      ("Монтаж, работы и материалы", "InstallationCalculator", {"window_title": "Монтаж · расчёты"}, "installation.manage"),
      ("Монтаж · цены и тарифы", "AdminSettings", {"window_title": "Монтаж · цены и тарифы", "start_section": "engineering.installation.pricing", "open_editor": True}, "installation.manage"),
      ("Engineering Control Room", "EngineeringControlRoom", {"window_title": "Engineering Control Room"}, "projects.manage"),
      ("Проекты и системы", "Projects", {"window_title": "Проекты и системы"}, "projects.manage"),
      ("Digital Twin объекта · планы и трассы", "Projects", {"window_title": "Digital Twin объекта"}, "projects.manage")
    ]
  },
  "operations": {
    "title": "Клиенты и обслуживание",
    "intro": "CRM, коммерческие предложения, задачи и сервисные записи.",
    "options": [
      ("CRM и сделки", "Operations", {"window_title": "CRM и сделки", "section": "crm"}, "operations.manage"),
      ("Сервис и обслуживание", "Operations", {"window_title": "Сервис и обслуживание", "section": "service"}, "service.manage")
    ]
  },
  "system": {
    "title": "Пользователи и система",
    "intro": "Управление доступом, настройками и резервными копиями.",
    "admin_only": True,
    "options": [
      ("Системная диагностика", "SystemDiagnostics", {"window_title": "Системная диагностика"}, None),
      ("Пользователи, роли и доступ", "AdminUsers", {"window_title": "Пользователи и роли"}, None),
      ("Центр настроек сайта и проекта", "AdminSettings", {"window_title": "Центр настроек"}, None),
      ("Резервные копии", "Backup", {"window_title": "Резервные копии"}, None)
    ]
  },
  "ai": {
    "title": "ИИ и интеграции",
    "intro": "Модели, серверные ключи и инженерные AI-инструменты.",
    "admin_only": True,
    "options": [
      ("Секреты и подключения", "AdminSettings", {"window_title": "Секреты и подключения", "start_tab": "secrets"}, None),
      ("AI Studio · редакторы сайта и каталога", "AdminSettings", {"window_title": "AI Studio", "start_tab": "ai_tools"}, None),
      ("Настроить модели и API", "AIOperator", {"window_title": "ИИ и модели"}, None)
    ]
  },
  "social": {
    "title": "Социальные сети и каналы",
    "intro": "Ссылки на площадки, Telegram и каналы компании.",
    "admin_only": True,
    "options": [
      ("Каналы и уведомления", "SocialSettings", {"window_title": "Социальные сети"}, None)
    ]
  }
}
