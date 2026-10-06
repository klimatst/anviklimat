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
  """The redesigned module workspace for staff and administrators."""

  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_staff_form():
      return

    self._context = Access.get_session_context()
    self._is_admin = self._context["role_code"] == "admin"
    self._permissions = set(self._context["permissions"])
    self._modules = [module for module in MODULES if self._module_available(module)]
    self.module_group_dropdown.items = [("Все модули", "Все")] + [
      (group, group) for group in MODULE_GROUPS
      if any(module["group"] == group for module in self._modules)
    ]
    self.module_group_dropdown.selected_value = "Все"
    self.orders_button.visible = self._module_available_by_permission("catalog.manage")
    self.configure_widgets_button.visible = self._is_admin
    self.settings_button.visible = self._is_admin
    self.design_button.visible = self._is_admin
    self.health_button.visible = self._is_admin
    self.diagnostics_button.visible = self._is_admin
    self.missing_images_button.visible = self._module_available_by_permission("catalog.manage")
    self.catalog_button.visible = self._module_available_by_permission("catalog.manage")
    self.content_button.visible = self._module_available_by_permission("cms.manage")
    self.audit_panel.visible = self._is_admin
    self._render_modules()
    self.engineering_control_button.visible = self._module_available_by_permission("projects.manage")
    self._load_dashboard()
    self._load_engineering_control_room()

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
      modules = [module for module in modules if term in str(" ".join((
        str(module["title"] or ""), str(module["description"] or ""),
        str(module["badge"] or ""), str(module["group"] or "")
      ))).lower()]
    return [dict(module) for module in modules]

  def _render_modules(self):
    filtered = self._filtered_modules()
    self.module_rows.items = filtered
    self.module_status.text = "{} из {} модулей · {} визуальных редакторов".format(
      len(filtered), len(self._modules),
      sum(1 for module in self._modules if module["group"] == "Редакторы")
    )

  def _load_engineering_control_room(self):
    if not self._module_available_by_permission("projects.manage"):
      self.engineering_status.text = "Инженерный контур доступен сотрудникам с правом projects.manage."
      return
    try:
      result = anvil.server.call("get_engineering_control_room")
    except Exception as exc:
      self.engineering_status.text = "Инженерный контур временно недоступен: {}".format(exc)
      return
    if not result.get("ok"):
      self.engineering_status.text = result.get("message", "Не удалось загрузить Engineering OS.")
      return
    metrics = result.get("metrics", {})
    kpi_values = [
      metrics.get("projects", 0),
      metrics.get("active_projects", 0),
      metrics.get("needs_attention", 0),
      metrics.get("systems", 0),
      metrics.get("calculations", 0),
      metrics.get("estimates", 0)
    ]
    # The KPI strip is intentionally rendered through the component tree so
    # the dashboard stays native Anvil and remains theme-safe.
    for component, value in zip(
      ("engineering_kpi_1", "engineering_kpi_2", "engineering_kpi_3",
       "engineering_kpi_4", "engineering_kpi_5", "engineering_kpi_6"),
      kpi_values
    ):
      if hasattr(self, component):
        getattr(self, component).text = str(value)
    self.engineering_status.text = (
      "Активных проектов: {} · сервисных записей: {} · обновлено: {} UTC".format(
        metrics.get("active_projects", 0),
        metrics.get("services", 0),
        result.get("generated_at")
      )
    )
    try:
      quality = anvil.server.call("get_engineering_quality_gate")
      if quality.get("ok"):
        if quality.get("healthy"):
          self.engineering_quality_status.text = "QUALITY GATE · OK"
        else:
          self.engineering_quality_status.text = (
            "QUALITY GATE · {} замечаний".format(quality.get("issue_count", 0))
          )
      else:
        self.engineering_quality_status.text = "QUALITY GATE · недоступен"
    except Exception:
      self.engineering_quality_status.text = "QUALITY GATE · ошибка проверки"

  def _load_dashboard(self):
    try:
      result = anvil.server.call("get_admin_dashboard")
    except Exception as exc:
      self.analytics_summary.items = []
      self.analytics_status.text = "Сводка проекта временно недоступна: {}".format(exc)
      self.attention_summary.text = "Не удалось загрузить состояние проекта."
      self.attention_detail.text = "Откройте диагностику или повторите обновление."
      return
    if not result["ok"]:
      self.analytics_summary.items = []
      self.analytics_status.text = result["message"]
      self.attention_summary.text = "Не удалось загрузить состояние проекта."
      self.attention_detail.text = "Обновите данные или откройте раздел диагностики."
      return

    self.analytics_summary.items = result["widgets"]
    self.analytics_status.text = "Показателей: {}".format(
      result["widgets_available_count"]
    )
    self.analytics_updated.text = "Обновлено: {} UTC".format(result["as_of"])

    missing_images = next(
      (metric["value"] for metric in result["metrics"]
       if metric["label"] == "Товары без изображений"), 0
    )
    new_orders = next(
      (metric["value"] for metric in result["metrics"]
       if metric["label"] == "Новые заявки каталога"), 0
    )
    incomplete_products = next(
      (metric["value"] for metric in result["metrics"]
       if metric["label"] == "Товары без описания"), 0
    )
    attention = []
    if new_orders:
      attention.append("Новых заявок: {}".format(new_orders))
    if missing_images:
      attention.append("Товаров без фото: {}".format(missing_images))
    if incomplete_products:
      attention.append("Карточек без описания: {}".format(incomplete_products))
    self.attention_summary.text = (
      "Требуют внимания: {}".format(len(attention)) if attention else
      "Критических задач нет"
    )
    self.attention_detail.text = (
      "\n".join(attention) if attention else
      "Каталог, заявки и страницы готовы к работе. Показатели загружены из проекта."
    )

    if self._is_admin:
      self.audit_summary.text = "\n".join(
        result.get("recent_audit", [])
      ) or "В журнале пока нет событий."

  @handle("module_search_box", "change")
  def module_search_box_change(self, **event_args):
    self._render_modules()

  @handle("module_group_dropdown", "change")
  def module_group_dropdown_change(self, **event_args):
    self._render_modules()

  @handle("module_rows", "x-open-admin-module")
  def module_rows_open_admin_module(self, module_id, **event_args):
    module = next((item for item in self._modules if item["id"] == module_id), None)
    if module is None:
      return
    Access.open_admin_window(module["form"], **dict(module["properties"]))

  @handle("analytics_summary", "x-open-metric")
  def analytics_summary_open_metric(self, metric, **event_args):
    if not isinstance(metric, dict):
      return
    metric_id = str(metric.get("id") or "")
    title = str(metric.get("label") or "Рабочий раздел")
    if metric_id == "settings_total":
      Access.open_admin_window(
        "AdminSettings", window_title="Центр настроек",
        start_section="system.widgets", open_editor=True
      )
      return
    if metric_id == "media_without_source":
      Access.open_admin_window(
        "AdminSettings", window_title="Фото и хранилище",
        start_section="integrations.media.storage", open_editor=True
      )
      return
    route = METRIC_ROUTES.get(metric_id)
    target = route[0] if route else "AdminSettings"
    if route:
      title = route[1]
    properties = {"window_title": title}
    if target == "Operations":
      properties["section"] = "service" if metric_id.startswith("service_") else "crm"
    Access.open_admin_window(target, **properties)

  @handle("refresh_button", "click")
  def refresh_button_click(self, **event_args):
    self.refresh_button.enabled = False
    try:
      self._load_dashboard()
    finally:
      self.refresh_button.enabled = True

  @handle("orders_button", "click")
  def orders_button_click(self, **event_args):
    Access.open_admin_window("Catalog.Orders", window_title="Заявки каталога")

  @handle("missing_images_button", "click")
  def missing_images_button_click(self, **event_args):
    Access.open_admin_window("Catalog.Media", window_title="Медиа каталога")

  @handle("catalog_button", "click")
  def catalog_button_click(self, **event_args):
    Access.open_admin_window("Catalog", window_title="Каталог товаров")

  @handle("content_button", "click")
  def content_button_click(self, **event_args):
    Access.open_admin_window("CMS", window_title="Страницы и контент")

  @handle("configure_widgets_button", "click")
  def configure_widgets_button_click(self, **event_args):
    Access.open_admin_window(
      "AdminSettings", window_title="Настройка Dashboard", start_tab="widgets"
    )

  @handle("settings_button", "click")
  def settings_button_click(self, **event_args):
    Access.open_admin_window("AdminSettings", window_title="Центр настроек")

  @handle("design_button", "click")
  def design_button_click(self, **event_args):
    Access.open_admin_window("AdminSettings", window_title="Design Studio · визуальная система", start_section="design.visual.system", open_editor=True)

  @handle("health_button", "click")
  def health_button_click(self, **event_args):
    Access.open_admin_window("SystemDiagnostics", window_title="System Health Center")

  @handle("diagnostics_button", "click")
  def diagnostics_button_click(self, **event_args):
    Access.open_admin_window("SystemDiagnostics", window_title="Системная диагностика")

  @handle("engineering_control_button", "click")
  def engineering_control_button_click(self, **event_args):
    Access.open_admin_window("EngineeringControlRoom", window_title="Engineering Control Room")

