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

METRIC_GROUP_ROUTES = {
  "Каталог": "Catalog",
  "Медиа": "Catalog.Media",
  "Заказы": "Catalog.Orders",
  "Контент": "CMS",
  "Рабочие процессы": "Operations",
  "Проекты": "Projects",
  "Пользователи": "AdminUsers",
  "Интеграции": "AIOperator",
  "Импорт и экспорт": "ImportEngine",
  "Система": "SystemDiagnostics"
}


class AdminTools(AdminToolsTemplate):
  """The landing page for staff: live status, attention items and shortcuts."""

  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_staff_form():
      return

    self._context = Access.get_session_context()
    self._is_admin = self._context["role_code"] == "admin"
    permissions = set(self._context["permissions"])

    self.orders_button.visible = (
      self._is_admin or "catalog.manage" in permissions
    )
    self.configure_widgets_button.visible = self._is_admin
    self.settings_button.visible = self._is_admin
    self.diagnostics_button.visible = self._is_admin
    self.missing_images_button.visible = self.orders_button.visible
    self.catalog_button.visible = self.orders_button.visible
    self.content_button.visible = self._is_admin or "cms.manage" in permissions
    self.audit_panel.visible = self._is_admin
    self._load_dashboard()

  def _load_dashboard(self):
    result = anvil.server.call("get_admin_dashboard")
    if not result["ok"]:
      self.analytics_summary.items = []
      self.analytics_status.text = result["message"]
      self.attention_summary.text = "Не удалось загрузить состояние проекта."
      return

    self.analytics_summary.items = result["widgets"]
    self.analytics_status.text = "Виджетов на рабочем столе: {}".format(
      result["widgets_available_count"]
    )
    self.analytics_updated.text = "Обновлено: {} UTC".format(result["as_of"])

    missing_images = next(
      (metric["value"] for metric in result["metrics"]
       if metric["label"] == "Товары без изображений"),
      0
    )
    new_orders = next(
      (metric["value"] for metric in result["metrics"]
       if metric["label"] == "Новые заявки каталога"),
      0
    )
    incomplete_products = next(
      (metric["value"] for metric in result["metrics"]
       if metric["label"] == "Товары без описания"),
      0
    )
    attention = []
    if new_orders:
      attention.append("Новых заявок: {}".format(new_orders))
    if missing_images:
      attention.append("Товаров без изображений: {}".format(missing_images))
    if incomplete_products:
      attention.append("Карточек без описания: {}".format(incomplete_products))
    self.attention_summary.text = (
      "Требуют внимания: {}".format(len(attention)) if attention else
      "Все ключевые показатели загружены"
    )
    self.attention_detail.text = (
      "\n".join(attention) if attention else
      "Критичных задач по каталогу нет. Данные сводки получены из текущих таблиц проекта."
    )

    if self._is_admin:
      self.audit_summary.text = "\n".join(
        result.get("recent_audit", [])
      ) or "В журнале пока нет событий."

  @handle("refresh_button", "click")
  def refresh_button_click(self, **event_args):
    self.refresh_button.enabled = False
    try:
      self._load_dashboard()
    finally:
      self.refresh_button.enabled = True

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
    target = route[0] if route else METRIC_GROUP_ROUTES.get(
      str(metric.get("group") or ""), "AdminSettings"
    )
    if route:
      title = route[1]
    properties = {"window_title": title}
    if target == "Operations":
      properties["section"] = "service" if metric_id.startswith("service_") else "crm"
    Access.open_admin_window(target, **properties)

  @handle("orders_button", "click")
  def orders_button_click(self, **event_args):
    Access.open_admin_window("Catalog.Orders")

  @handle("missing_images_button", "click")
  def missing_images_button_click(self, **event_args):
    Access.open_admin_window("Catalog.Media")

  @handle("catalog_button", "click")
  def catalog_button_click(self, **event_args):
    Access.open_admin_window("Catalog")

  @handle("content_button", "click")
  def content_button_click(self, **event_args):
    Access.open_admin_window("CMS")

  @handle("configure_widgets_button", "click")
  def configure_widgets_button_click(self, **event_args):
    Access.open_admin_window("AdminSettings", window_title="Настройки Dashboard")

  @handle("settings_button", "click")
  def settings_button_click(self, **event_args):
    Access.open_admin_window("AdminSettings", window_title="Центр настроек")

  @handle("diagnostics_button", "click")
  def diagnostics_button_click(self, **event_args):
    Access.open_admin_window("SystemDiagnostics")
