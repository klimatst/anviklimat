from ._anvil_designer import AdminToolsTemplate
from anvil import handle
import anvil.server
from .. import Access


METRIC_ROUTES = {
  "products_total": ("Catalog", "Каталог · товары"),
  "products_active": ("Catalog", "Каталог · активные товары"),
  "products_missing_images": ("Catalog.Media", "Медиа · товары без фото"),
  "categories_total": ("Catalog.Taxonomy", "Категории каталога"),
  "product_images": ("Catalog.Media", "Медиа каталога"),
  "orders_total": ("Catalog.Orders", "Заявки каталога"),
  "orders_new": ("Catalog.Orders", "Новые заявки"),
  "cms_pages": ("CMS", "Страницы и контент"),
  "gallery_items": ("Gallery", "Галерея проектов"),
  "crm_clients": ("Operations", "CRM и сделки"),
  "crm_tasks_open": ("Operations", "Открытые задачи"),
  "projects_total": ("Projects", "Проекты и системы"),
  "calculations_total": ("Calculations", "Инженерные расчёты"),
  "users_total": ("AdminUsers", "Пользователи и роли"),
  "ai_providers": ("AIOperator", "API и модели AI"),
  "ai_usage_week": ("AIOperator", "Использование AI"),
  "imports_total": ("ImportEngine", "Импорт каталога"),
  "audit_week": ("SystemDiagnostics", "Журнал и диагностика"),
  "settings_total": ("AdminSettings", "Центр настроек")
}


MODULES = [
  {
    "id": "pages", "title": "Редактор страниц", "group": "Редакторы",
    "description": "Создание, изменение и публикация страниц и материалов сайта.",
    "icon": "▤", "badge": "CMS", "form": "CMS", "permission": "cms.manage",
    "properties": {"window_title": "Редактор страниц · CMS"}
  },
  {
    "id": "navigation", "title": "Меню и навигация", "group": "Редакторы",
    "description": "Настройка ссылок, порядка разделов и пунктов меню.",
    "icon": "⌘", "badge": "САЙТ", "form": "SiteMenu", "permission": "cms.manage",
    "properties": {"window_title": "Меню и навигация сайта"}
  },
  {
    "id": "appearance", "title": "Цвета и тема", "group": "Редакторы",
    "description": "Палитра, плотность интерфейса и эффекты переходов.",
    "icon": "◉", "badge": "ДИЗАЙН", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Редактор темы и цветов", "start_section": "site.appearance", "open_editor": True}
  },
  {
    "id": "typography", "title": "Типографика", "group": "Редакторы",
    "description": "Размеры текста, начертания и иерархия заголовков.",
    "icon": "Aa", "badge": "ДИЗАЙН", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Редактор типографики", "start_section": "site.typography", "open_editor": True}
  },
  {
    "id": "header", "title": "Шапка и навигация", "group": "Редакторы",
    "description": "Контактная полоса, быстрые кнопки и поведение шапки.",
    "icon": "▱", "badge": "БЛОКИ", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Редактор шапки сайта", "start_section": "site.header", "open_editor": True}
  },
  {
    "id": "homepage", "title": "Главная страница", "group": "Редакторы",
    "description": "Первый экран, блоки витрины и главные действия.",
    "icon": "⌂", "badge": "БЛОКИ", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Конструктор главной", "start_section": "site.home.hero", "open_editor": True}
  },
  {
    "id": "seo", "title": "SEO сайта", "group": "Редакторы",
    "description": "Заголовки, описания и правила индексации страниц.",
    "icon": "⌕", "badge": "ПОИСК", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "SEO редактор сайта", "start_section": "site.seo", "open_editor": True}
  },
  {
    "id": "catalog_seo", "title": "SEO каталога", "group": "Редакторы",
    "description": "Шаблоны поисковых заголовков и индексация каталога.",
    "icon": "⌕", "badge": "КАТАЛОГ", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "SEO редактор каталога", "start_section": "site.seo.catalog", "open_editor": True}
  },
  {
    "id": "scripts", "title": "Редактор CSS и JavaScript", "group": "Редакторы",
    "description": "Управляемые расширения оформления и поведения сайта.",
    "icon": "{ }", "badge": "КОД", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "CSS и JavaScript · расширения", "start_tab": "extensions"}
  },
  {
    "id": "ai_content", "title": "AI редактор", "group": "Редакторы",
    "description": "Инструменты генерации и редактирования контента проекта.",
    "icon": "✧", "badge": "AI STUDIO", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "AI Studio · редакторы контента", "start_tab": "ai_tools"}
  },
  {
    "id": "catalog", "title": "Каталог и товары", "group": "Каталог",
    "description": "Карточки, цены, категории, серии, характеристики и остатки.",
    "icon": "▦", "badge": "ТОВАРЫ", "form": "Catalog", "permission": "catalog.manage",
    "properties": {"window_title": "Каталог товаров"}
  },
  {
    "id": "catalog_structure", "title": "Структура и категории", "group": "Каталог",
    "description": "Дерево разделов, подкатегории, бренды и поля карточек. Изменения сразу видны на сайте.",
    "icon": "⌘", "badge": "СТРУКТУРА", "form": "Catalog.Taxonomy", "permission": "catalog.manage",
    "properties": {"window_title": "Структура каталога · категории"}
  },
  {
    "id": "lovable_catalog_sync", "title": "Hisense · синхронизация Lovable", "group": "Каталог",
    "description": "Полный перенос каталога Hisense: модели, цены, характеристики, серии и фото из GitHub.",
    "icon": "⇄", "badge": "SYNC", "form": "Catalog", "permission": "catalog.manage",
    "properties": {"window_title": "Hisense · синхронизация каталога", "sync_lovable": True}
  },
  {
    "id": "media", "title": "Медиа и фотохранилище", "group": "Каталог",
    "description": "Фото товаров, облачные ссылки и записи без изображений.",
    "icon": "▧", "badge": "МЕДИА", "form": "Catalog.Media", "permission": "catalog.manage",
    "properties": {"window_title": "Медиа каталога"}
  },
  {
    "id": "drafts", "title": "Черновики импорта", "group": "Каталог",
    "description": "Проверка PDF/XLSX, категории и точечное добавление товаров.",
    "icon": "⇧", "badge": "ИМПОРТ", "form": "ImportEngine", "permission": "import.manage",
    "properties": {"window_title": "Черновики импорта", "drafts_only": True}
  },
  {
    "id": "calculations", "title": "Формулы и расчёты", "group": "Инженерия",
    "description": "Инженерные формулы, правила расчётов и калькуляторы.",
    "icon": "∑", "badge": "РАСЧЁТЫ", "form": "Calculations", "permission": "calculations.manage",
    "properties": {"window_title": "Инженерные расчёты"}
  },
  {
    "id": "installation_pricing", "title": "Монтаж · цены как в Lovable", "group": "Инженерия",
    "description": "Большой редактор тарифов монтажа с теми же 15 основными позициями и структурой цен.",
    "icon": "₽", "badge": "PRICING", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Монтаж · цены и тарифы", "start_section": "engineering.installation.pricing", "open_editor": True}
  },
  {
    "id": "ventilation", "title": "Расчёт вентиляции", "group": "Инженерия",
    "description": "Страница вентиляции, поля калькулятора, формулы и тарифы.",
    "icon": "↗", "badge": "ИНЖЕНЕРИЯ", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Управление вентиляцией", "start_section": "ventilation.page", "open_editor": True}
  },
  {
    "id": "engineering_control_room", "title": "Engineering Control Room", "group": "Инженерия",
    "description": "Единый контур инженерного проекта: стадии, системы, расчёты, сметы и сервис.",
    "icon": "⌬", "badge": "ENGINEERING OS", "form": "EngineeringControlRoom", "permission": "projects.manage",
    "properties": {"window_title": "Engineering Control Room"}
  },
  {
    "id": "projects", "title": "Проекты и системы", "group": "Инженерия",
    "description": "Объекты, помещения и спецификации оборудования.",
    "icon": "⌗", "badge": "ПРОЕКТЫ", "form": "Projects", "permission": "projects.manage",
    "properties": {"window_title": "Проекты и системы"}
  },
  {
    "id": "crm", "title": "Клиенты и обслуживание", "group": "Операции",
    "description": "CRM, сделки, сервисные обращения и задачи.",
    "icon": "◌", "badge": "CRM", "form": "Operations", "permission": "operations.manage",
    "properties": {"window_title": "CRM и обслуживание", "section": "crm"}
  },
  {
    "id": "widgets", "title": "Виджеты Dashboard", "group": "Система",
    "description": "Состав рабочего стола и порядок ключевых показателей.",
    "icon": "▥", "badge": "РАБОЧИЙ СТОЛ", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Настройка Dashboard", "start_tab": "widgets"}
  },
  {
    "id": "secrets", "title": "Секреты и API", "group": "Система",
    "description": "Cloudinary, AI-провайдеры и защищённые серверные ключи.",
    "icon": "⌑", "badge": "ИНТЕГРАЦИИ", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Секреты и подключения", "start_tab": "secrets"}
  },
  {
    "id": "backups", "title": "Резервные копии", "group": "Система",
    "description": "Экспорт, восстановление и резервирование данных проекта.",
    "icon": "⤓", "badge": "БЕЗОПАСНОСТЬ", "form": "Backup", "permission": None,
    "properties": {"window_title": "Резервные копии"}
  },
  {
    "id": "diagnostics", "title": "Диагностика системы", "group": "Система",
    "description": "Сводка проверок, журнал событий и состояние модулей.",
    "icon": "⌁", "badge": "СИСТЕМА", "form": "SystemDiagnostics", "permission": None,
    "properties": {"window_title": "Системная диагностика"}
  },
  {
    "id": "command_center", "title": "Command Center", "group": "Система",
    "description": "Главный центр управления: KPI, быстрые действия, состояние системы и критические задачи.",
    "icon": "⌘", "badge": "CONTROL CENTER", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Command Center · ЭКО-КЛИМАТ", "start_tab": "widgets"}
  },
  {
    "id": "design_studio", "title": "Design Studio", "group": "Редакторы",
    "description": "Полное управление пятью темами, сеткой, карточками, Hero, анимациями и мобильным видом.",
    "icon": "✦", "badge": "DESIGN", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Design Studio · визуальная система", "start_section": "design.visual.system", "open_editor": True}
  },
  {
    "id": "page_builder", "title": "Visual Page Builder", "group": "Редакторы",
    "description": "Управление блоками страниц, порядком секций, шаблонами и предпросмотром.",
    "icon": "▤", "badge": "BUILDER", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Visual Page Builder", "start_section": "content.visual-editor", "open_editor": True}
  },
  {
    "id": "menu_builder", "title": "Menu Builder", "group": "Редакторы",
    "description": "Центральный редактор меню, навигации, CTA и структуры переходов.",
    "icon": "☰", "badge": "NAV", "form": "SiteMenu", "permission": "cms.manage",
    "properties": {"window_title": "Menu Builder · навигация"}
  },
  {
    "id": "bulk_catalog", "title": "Bulk Catalog Editor", "group": "Каталог",
    "description": "Массовое редактирование товаров, цен, категорий, брендов, характеристик и публикации.",
    "icon": "▦", "badge": "BULK EDIT", "form": "Catalog", "permission": "catalog.manage",
    "properties": {"window_title": "Bulk Catalog Editor · каталог"}
  },
  {
    "id": "import_center", "title": "Import Center", "group": "Каталог",
    "description": "Единый контроль XLSX, PDF, CSV, черновиков, проверки данных и журналов импорта.",
    "icon": "⇧", "badge": "IMPORT", "form": "ImportEngine", "permission": "import.manage",
    "properties": {"window_title": "Import Center · импорт"}
  },
  {
    "id": "media_manager", "title": "Media Manager Pro", "group": "Каталог",
    "description": "Центр изображений: отсутствующие фото, источники, ссылки, массовые операции и хранилища.",
    "icon": "▧", "badge": "MEDIA PRO", "form": "Catalog.Media", "permission": "catalog.manage",
    "properties": {"window_title": "Media Manager Pro · изображения"}
  },
  {
    "id": "system_health", "title": "System Health Center", "group": "Система",
    "description": "Контроль целостности каталога, изображений, калькуляторов, ссылок, данных и ошибок.",
    "icon": "♥", "badge": "HEALTH", "form": "SystemDiagnostics", "permission": None,
    "properties": {"window_title": "System Health Center"}
  },
  {
    "id": "security_center", "title": "Security Center", "group": "Система",
    "description": "Сессии, защита входа, аудит чувствительных действий и контроль повторных ошибок.",
    "icon": "⌑", "badge": "SECURITY", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Security Center", "start_section": "security.control", "open_editor": True}
  },
  {
    "id": "automation_center", "title": "Automation Center", "group": "Система",
    "description": "Автоматические уведомления, назначения, напоминания и история статусов.",
    "icon": "↯", "badge": "AUTOMATION", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Automation Center", "start_section": "workflow.automation", "open_editor": True}
  },
  {
    "id": "performance_center", "title": "Performance Center", "group": "Система",
    "description": "Управление скоростью, lazy-load, WebP, preload, качеством изображений и motion.",
    "icon": "◒", "badge": "PERFORMANCE", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "Performance Center", "start_section": "performance.control", "open_editor": True}
  },
  {
    "id": "seo_center", "title": "SEO Control Center", "group": "Редакторы",
    "description": "Расширенный SEO-контроль: schema, sitemap, canonical, breadcrumbs и индексация.",
    "icon": "⌕", "badge": "SEO PRO", "form": "AdminSettings", "permission": None,
    "properties": {"window_title": "SEO Control Center", "start_section": "seo.advanced", "open_editor": True}
  }
]


MODULE_GROUPS = ("Редакторы", "Каталог", "Инженерия", "Операции", "Система")

class AdminTools(AdminToolsTemplate):
  """Compact, fast admin workspace. Heavy dashboards are deliberately opt-in."""

  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_staff_form():
      return

    self._context = Access.get_session_context() or {}
    self._is_admin = self._context.get("role_code") == "admin"
    self._permissions = set(self._context.get("permissions") or [])
    hidden = {"widgets", "command_center"}
    self._modules = [
      module for module in MODULES
      if module.get("id") not in hidden and self._module_available(module)
    ]
    self.module_group_dropdown.items = [("Все модули", "Все")] + [
      (group, group) for group in MODULE_GROUPS
      if any(module["group"] == group for module in self._modules)
    ]
    self.module_group_dropdown.selected_value = "Все"
    self._set_sidebar_active("sidebar_all")
    self._render_modules()
    self.attention_summary.text = "Админка работает в быстром режиме"
    self.attention_detail.text = (
      "Каталог, CMS, инженерия, CRM и системные инструменты загружаются только "
      "при открытии раздела. Это снижает стартовую нагрузку Anvil."
    )
    self.engineering_control_button.visible = self._module_available_by_permission("projects.manage")
    if self.engineering_control_button.visible:
      self.engineering_status.text = (
        "Расширенные KPI, Quality Gate и аудит доступны внутри Engineering Control Room."
      )
    else:
      self.engineering_status.text = "Инженерный контур доступен по правам projects.manage."

  def _module_available_by_permission(self, permission):
    return self._is_admin or permission in self._permissions or "*" in self._permissions

  def _module_available(self, module):
    permission = module.get("permission")
    return self._is_admin if permission is None else self._module_available_by_permission(permission)

  def _filtered_modules(self):
    term = str(self.module_search_box.text or "").strip().lower()
    selected_group = self.module_group_dropdown.selected_value or "Все"
    modules = self._modules
    if selected_group != "Все":
      modules = [module for module in modules if module["group"] == selected_group]
    if term:
      modules = [
        module for module in modules
        if term in str(" ".join((
          module.get("title") or "", module.get("description") or "",
          module.get("badge") or "", module.get("group") or ""
        ))).lower()
      ]
    return [dict(module) for module in modules]

  def _render_modules(self):
    filtered = self._filtered_modules()
    self.module_rows.items = filtered
    self.module_status.text = "{} разделов".format(len(filtered))

  def _set_sidebar_active(self, component_name):
    for name in (
      "sidebar_all", "sidebar_editors", "sidebar_catalog",
      "sidebar_engineering", "sidebar_operations", "sidebar_system"
    ):
      component = getattr(self, name, None)
      if component is not None:
        component.role = (
          "admin-sidebar-link admin-sidebar-link-active"
          if name == component_name else "admin-sidebar-link"
        )

  def _select_group(self, group, component_name):
    self.module_group_dropdown.selected_value = group
    self._set_sidebar_active(component_name)
    self._render_modules()

  @handle("module_search_box", "change")
  def module_search_box_change(self, **event_args):
    self._render_modules()

  @handle("module_rows", "x-open-admin-module")
  def module_rows_open_admin_module(self, module_id, **event_args):
    module = next((item for item in self._modules if item["id"] == module_id), None)
    if module is not None:
      Access.open_admin_window(module["form"], **dict(module["properties"]))

  @handle("sidebar_all", "click")
  def sidebar_all_click(self, **event_args):
    self._select_group("Все", "sidebar_all")

  @handle("sidebar_editors", "click")
  def sidebar_editors_click(self, **event_args):
    self._select_group("Редакторы", "sidebar_editors")

  @handle("sidebar_catalog", "click")
  def sidebar_catalog_click(self, **event_args):
    self._select_group("Каталог", "sidebar_catalog")

  @handle("sidebar_engineering", "click")
  def sidebar_engineering_click(self, **event_args):
    self._select_group("Инженерия", "sidebar_engineering")

  @handle("sidebar_operations", "click")
  def sidebar_operations_click(self, **event_args):
    self._select_group("Операции", "sidebar_operations")

  @handle("sidebar_system", "click")
  def sidebar_system_click(self, **event_args):
    self._select_group("Система", "sidebar_system")

  @handle("refresh_button", "click")
  def refresh_button_click(self, **event_args):
    self._render_modules()

  @handle("engineering_control_button", "click")
  def engineering_control_button_click(self, **event_args):
    Access.open_admin_window(
      "EngineeringControlRoom", window_title="Engineering Control Room"
    )
