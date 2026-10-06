from ._anvil_designer import BaseLayoutTemplate
from anvil import handle
from anvil.js.window import document
import anvil.server
import anvil.users
from ... import Access, AdminExtensions, AdminNavigation, NewsCategories
import time


_PUBLIC_SHELL_CACHE = None
_PUBLIC_SHELL_CACHE_AT = 0.0
_PUBLIC_SHELL_CACHE_EMAIL = None

SITE_THEME_CODES = ("blue", "graphite", "ice", "amber", "crimson", "violet")


class BaseLayout(BaseLayoutTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    document_root = document.documentElement
    if document_root is not None:
      document_root.setAttribute("lang", "ru")
      document_root.setAttribute("translate", "no")
    self._navigation_settings = {
      "catalog": True, "news": True, "projects": True, "account": True
    }
    bootstrap = self._load_public_shell_data()
    self.catalog_dropdown.visible = False
    self.calculators_dropdown.visible = False
    self.news_dropdown.visible = False
    self.service_dropdown.visible = False
    self.custom_site_menu_dropdown.visible = False

    # Public navigation is the first render path. Bootstrap theme, menu,
    # session context and extensions in one request to avoid a chain of
    # synchronous server round-trips on every page open.
    if bootstrap.get("ok"):
      self._apply_site_theme(bootstrap.get("site_theme", "blue"))
      catalog = bootstrap.get("catalog") or {}
      self.nav_catalog_tree.items = self._apply_catalog_menu_result(catalog)
      Access.prime_session_context(bootstrap.get("session_context"))
      AdminExtensions.apply_saved_extensions(bundle=bootstrap.get("extensions"))
    else:
      # Keep the old fallback path for temporary runtime failures.
      self._apply_site_theme(Access.get_site_theme())
      self.nav_catalog_tree.items = self._catalog_menu_tree()
      AdminExtensions.apply_saved_extensions()

    self.nav_news_tree.items = NewsCategories.build_tree(menu_mode=True)
    self.nav_service_tree.items = self._service_menu_tree()
    self._refresh_session_context()
    self._configure_admin_sidebar()

  def _apply_site_theme(self, theme_code):
    if not isinstance(theme_code, str) or theme_code not in SITE_THEME_CODES:
      theme_code = "blue"
    for code in SITE_THEME_CODES:
      self.classes["site-theme--" + code] = code == theme_code

  def _refresh_session_context(self):
    user = anvil.users.get_user()
    email = user["email"] if user is not None else ""
    self.projects_nav.visible = bool(email) and self._navigation_settings["projects"]
    self.ai_nav.visible = bool(email)
    self.catalog_nav.visible = self._navigation_settings["catalog"]
    self.news_nav.visible = self._navigation_settings["news"]
    self.profile_nav.visible = self._navigation_settings["account"]
    context = Access.get_cached_session_context()
    if email and context["role_code"] == "user":
      try:
        context = Access.get_session_context()
      except anvil.server.RuntimeUnavailableError:
        context = Access.get_cached_session_context()
    self.admin_panel_nav.visible = context["role_code"] == "admin" or (
      context["role_code"] == "moderator"
      and "dashboard.view" in context["permissions"]
    )
    self.profile_nav.text = email.split("@", 1)[0] if email else "Войти"

  def _configure_admin_sidebar(self):
    active = Access.admin_navigation_active()
    self.classes["admin-mode"] = active
    self.admin_global_sidebar.visible = active
    self.admin_topbar.visible = active
    if not active:
      self.admin_global_subnav.visible = False
      return

    self.admin_breadcrumb.text = str(Access.get_admin_window_title() or "Обзор проекта")

    try:
      context = Access.get_session_context()
    except anvil.server.RuntimeUnavailableError:
      # This fallback only controls the client-side navigation. Server-side
      # permission checks remain authoritative for every protected action.
      context = Access.get_cached_session_context()
    self._admin_role = context["role_code"]
    self._admin_permissions = set(context["permissions"])
    allowed = {
      category: bool(self._available_admin_options(category))
      for category in AdminNavigation.MENU
    }
    for category, component_name in (
      ("catalog", "admin_catalog_nav"), ("content", "admin_content_nav"),
      ("engineering", "admin_engineering_nav"), ("operations", "admin_operations_nav"),
      ("social", "admin_social_nav"), ("system", "admin_system_nav"),
      ("ai", "admin_ai_nav")
    ):
      getattr(self, component_name).visible = allowed[category]

    category = Access.get_admin_navigation_category()
    if category in allowed and allowed[category]:
      self._show_admin_category(category)
    else:
      self.admin_global_subnav.visible = False

  def _available_admin_options(self, category):
    definition = AdminNavigation.MENU[category]
    if self._admin_role == "admin":
      return definition["options"]
    if definition.get("admin_only"):
      return []
    return [
      option for option in definition["options"]
      if option[3] in self._admin_permissions
    ]

  def _show_admin_category(self, category):
    options = self._available_admin_options(category)
    if not options:
      return
    self._admin_options = options
    definition = AdminNavigation.MENU[category]
    self.admin_global_picker_title.text = definition["title"]
    self.admin_global_picker_intro.text = definition["intro"]
    self.admin_global_picker_rows.items = [
      {"label": option[0], "option_index": index}
      for index, option in enumerate(options)
    ]
    self.admin_global_subnav.visible = True

  def _search_admin_workspace(self):
    term = (self.admin_search_box.text or "").strip()
    if len(term) < 2:
      self._admin_options = []
      self.admin_global_picker_title.text = "Поиск по системе"
      self.admin_global_picker_intro.text = "Введите не менее двух символов."
      self.admin_global_picker_rows.items = []
      self.admin_global_subnav.visible = True
      return

    lowered = term.lower()
    options = []
    for category, definition in AdminNavigation.MENU.items():
      for option in self._available_admin_options(category):
        if (lowered in str(option[0] or "").lower()
            or lowered in str(definition.get("title") or "").lower()):
          options.append(option)

    result = anvil.server.call("search_admin_workspace", term)
    if not result["ok"]:
      self._admin_options = options
      self.admin_global_picker_title.text = "Результаты поиска"
      self.admin_global_picker_intro.text = result["message"]
      self.admin_global_picker_rows.items = [
        {"label": option[0], "option_index": index}
        for index, option in enumerate(options)
      ]
      self.admin_global_subnav.visible = True
      return
    route_map = {
      "product": ("Catalog.ProductEditor", "catalog.manage", "product_id"),
      "category": ("Catalog.Taxonomy", "catalog.manage", "selected_category_id"),
      "brand": ("Catalog.Taxonomy", "catalog.manage", "selected_brand_id"),
      "order": ("Catalog.Orders", "catalog.manage", "search_query"),
      "page": ("CMS", "cms.manage", "selected_page_id"),
      "user": ("AdminUsers", None, "search_query")
    }
    for row in result["results"]:
      route = route_map.get(row["kind"])
      if route is None:
        continue
      form_name, permission, property_name = route
      properties = {property_name: row["id"]}
      if row["kind"] in ("order", "user"):
        properties[property_name] = term
      properties["window_title"] = row["title"]
      options.append((
        "{} · {}".format(row["title"], row["detail"]),
        form_name, properties, permission
      ))

    self._admin_options = options[:24]
    self.admin_global_picker_title.text = "Результаты поиска"
    self.admin_global_picker_intro.text = (
      "Найдено: {}. Выберите запись или раздел.".format(len(self._admin_options))
      if self._admin_options else "Совпадений не найдено. Проверьте запрос."
    )
    self.admin_global_picker_rows.items = [
      {"label": option[0], "option_index": index}
      for index, option in enumerate(self._admin_options)
    ]
    self.admin_global_subnav.visible = True

  def _toggle_admin_category(self, category):
    if (Access.get_admin_navigation_category() == category
        and self.admin_global_subnav.visible):
      self.admin_global_subnav.visible = False
      self._admin_options = []
      Access.set_admin_navigation_category(None)
      return
    Access.set_admin_navigation_category(category)
    self._show_admin_category(category)

  def _service_menu_tree(self):
    services = (
      ("installation", "Монтаж"),
      ("maintenance", "Обслужить"),
      ("repair", "Отремонтировать"),
      ("commissioning", "Пусконаладка"),
      ("measurement", "Провести измерения"),
      ("diagnosis", "Найти неисправность"),
      ("humidification_maintenance", "Обслужить увлажнитель")
    )
    children = [
      {
        "id": code, "code": code, "title": title, "children": [],
        "has_children": False, "expand_icon": "", "menu_mode": True
      }
      for code, title in services
    ]
    return [{
      "id": "service", "code": "service", "title": "Заявка на сервис",
      "children": children, "has_children": True, "expand_icon": "›",
      "menu_mode": True
    }]

  def _load_public_shell_data(self):
    global _PUBLIC_SHELL_CACHE, _PUBLIC_SHELL_CACHE_AT, _PUBLIC_SHELL_CACHE_EMAIL
    user = anvil.users.get_user()
    email = user["email"] if user is not None else ""
    now = time.monotonic()
    if (
      isinstance(_PUBLIC_SHELL_CACHE, dict)
      and _PUBLIC_SHELL_CACHE_EMAIL == email
      and now - _PUBLIC_SHELL_CACHE_AT < 30
    ):
      return _PUBLIC_SHELL_CACHE

    try:
      result = anvil.server.call("get_public_shell_data")
    except Exception:
      return {}
    if not isinstance(result, dict):
      return {}

    _PUBLIC_SHELL_CACHE = result
    _PUBLIC_SHELL_CACHE_EMAIL = email
    _PUBLIC_SHELL_CACHE_AT = now
    return result

  def _apply_catalog_menu_result(self, result):
    if not isinstance(result, dict):
      return []
    self.nav_custom_site_menu.items = result.get("site_menu", [])
    self.custom_site_menu_nav.visible = bool(self.nav_custom_site_menu.items)
    settings = result.get("navigation_settings", {})
    if isinstance(settings, dict):
      self._navigation_settings = {
        key: settings.get(key) is not False
        for key in ("catalog", "news", "projects", "account")
      }
    tree = result.get("tree")
    return tree if isinstance(tree, list) else []

  def _catalog_menu_tree(self):
    try:
      result = anvil.server.call("get_catalog_menu_tree")
      if result.get("ok"):
        return self._apply_catalog_menu_result(result)
    except Exception:
      # The header remains usable while the server runtime reconnects; the
      # database-backed tree replaces this compact fallback on the next load.
      pass
    self.nav_custom_site_menu.items = []
    self.custom_site_menu_nav.visible = False
    return [
      {"id": "direction-home", "code": "direction-home", "title": "Для дома",
       "menu_label": "Для дома", "children": [
         {"id": "air-conditioning", "code": "air-conditioning", "title": "Кондиционеры",
          "menu_label": "Кондиционеры", "children": [], "has_children": False,
          "expand_icon": "", "menu_mode": True}
       ], "has_children": True, "expand_icon": "›", "menu_mode": True},
      {"id": "direction-business", "code": "direction-business", "title": "Для бизнеса",
       "menu_label": "Для бизнеса", "children": [
         {"id": "vrf-vrv", "code": "vrf-vrv", "title": "VRV / VRF",
          "menu_label": "VRV / VRF", "children": [], "has_children": False,
          "expand_icon": "", "menu_mode": True}
       ], "has_children": True, "expand_icon": "›", "menu_mode": True}
    ]

  def _show_dropdown(self, dropdown_name):
    if dropdown_name == "catalog_dropdown" and not self._navigation_settings["catalog"]:
      return
    if dropdown_name == "news_dropdown" and not self._navigation_settings["news"]:
      return
    if dropdown_name == "custom_site_menu_dropdown" and not self.nav_custom_site_menu.items:
      return
    target = getattr(self, dropdown_name)
    self._close_dropdowns()
    target.visible = True

  def _hide_dropdown(self, dropdown_name):
    getattr(self, dropdown_name).visible = False

  def _close_dropdowns(self):
    self.catalog_dropdown.visible = False
    self.calculators_dropdown.visible = False
    self.news_dropdown.visible = False
    self.service_dropdown.visible = False
    self.custom_site_menu_dropdown.visible = False

  def _open_category(self, category_code):
    self._close_dropdowns()
    Access.open_window("Catalog", category_code=category_code)

  @handle("home_nav", "click")
  def home_nav_click(self, **event_args):
    Access.open_window("Form1")

  @handle("home_menu_nav", "click")
  def home_menu_nav_click(self, **event_args):
    Access.open_window("Form1")

  @handle("profile_nav", "click")
  def profile_nav_click(self, **event_args):
    Access.open_window("Profile")

  @handle("admin_panel_nav", "click")
  def admin_panel_nav_click(self, **event_args):
    Access.open_admin_dashboard()

  @handle("admin_dashboard_nav", "click")
  def admin_dashboard_nav_click(self, **event_args):
    Access.open_admin_dashboard()

  @handle("admin_catalog_nav", "click")
  def admin_catalog_nav_click(self, **event_args):
    self._toggle_admin_category("catalog")

  @handle("admin_content_nav", "click")
  def admin_content_nav_click(self, **event_args):
    self._toggle_admin_category("content")

  @handle("admin_engineering_nav", "click")
  def admin_engineering_nav_click(self, **event_args):
    self._toggle_admin_category("engineering")

  @handle("admin_operations_nav", "click")
  def admin_operations_nav_click(self, **event_args):
    self._toggle_admin_category("operations")

  @handle("admin_social_nav", "click")
  def admin_social_nav_click(self, **event_args):
    self._toggle_admin_category("social")

  @handle("admin_system_nav", "click")
  def admin_system_nav_click(self, **event_args):
    self._toggle_admin_category("system")

  @handle("admin_ai_nav", "click")
  def admin_ai_nav_click(self, **event_args):
    self._toggle_admin_category("ai")

  @handle("admin_global_picker_rows", "x-open-tool")
  def admin_global_picker_rows_open_tool(self, option_index, **event_args):
    options = getattr(self, "_admin_options", [])
    if option_index < 0 or option_index >= len(options):
      return
    _, form_name, properties, _ = options[option_index]
    Access.set_admin_navigation_category(None)
    Access.open_admin_window(form_name, **properties)

  @handle("admin_global_close_button", "click")
  def admin_global_close_button_click(self, **event_args):
    self.admin_global_subnav.visible = False
    self._admin_options = []
    Access.set_admin_navigation_category(None)

  @handle("admin_global_home_button", "click")
  def admin_global_home_button_click(self, **event_args):
    Access.open_window("Form1")

  @handle("admin_profile_button", "click")
  def admin_profile_button_click(self, **event_args):
    Access.open_context_window("Profile")

  @handle("admin_search_button", "click")
  def admin_search_button_click(self, **event_args):
    self._search_admin_workspace()

  @handle("admin_search_box", "pressed_enter")
  def admin_search_box_pressed_enter(self, **event_args):
    self._search_admin_workspace()

  @handle("search_button", "click")
  def search_button_click(self, **event_args):
    search_text = (self.search_box.text or "").strip()
    Access.open_window("Catalog", category_code=None, search_query=search_text)

  @handle("catalog_nav", "click")
  def catalog_nav_click(self, **event_args):
    if self.catalog_dropdown.visible:
      self.catalog_dropdown.visible = False
    else:
      self._show_dropdown("catalog_dropdown")

  def catalog_menu_mouse_enter(self, event):
    self._show_dropdown("catalog_dropdown")

  def catalog_menu_mouse_leave(self, event):
    self._hide_dropdown("catalog_dropdown")

  @handle("nav_catalog_tree", "x-category-selected")
  def nav_catalog_tree_category_selected(self, category_id=None, category_code=None, **event_args):
    self._open_category(category_code or category_id)

  @handle("calculators_nav", "click")
  def calculators_nav_click(self, **event_args):
    self._show_dropdown("calculators_dropdown")

  def calculators_menu_mouse_enter(self, event):
    self._show_dropdown("calculators_dropdown")

  def calculators_menu_mouse_leave(self, event):
    self._hide_dropdown("calculators_dropdown")

  @handle("calc_ac_nav", "click")
  def calc_ac_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("Calculations", module_code="ac")

  @handle("calc_vrf_nav", "click")
  def calc_vrf_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("Calculations", module_code="vrf_vrv")

  @handle("calc_ventilation_nav", "click")
  def calc_ventilation_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("VentilationCalculator")

  @handle("installation_tool_nav", "click")
  def installation_tool_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("InstallationCalculator")

  @handle("ruler_nav", "click")
  def ruler_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("RefrigerantRuler")

  @handle("installation_nav", "click")
  def installation_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("InstallationCalculator")

  @handle("news_nav", "click")
  def news_nav_click(self, **event_args):
    self._show_dropdown("news_dropdown")

  def news_menu_mouse_enter(self, event):
    self._show_dropdown("news_dropdown")

  def news_menu_mouse_leave(self, event):
    self._hide_dropdown("news_dropdown")

  @handle("news_all_nav", "click")
  def news_all_nav_click(self, **event_args):
    self._close_dropdowns()
    Access.open_window("News")

  @handle("nav_news_tree", "x-category-selected")
  def nav_news_tree_category_selected(self, category_id, **event_args):
    self._close_dropdowns()
    Access.open_window("News", category_code=category_id)

  @handle("service_nav", "click")
  def service_nav_click(self, **event_args):
    self._show_dropdown("service_dropdown")

  def service_menu_mouse_enter(self, event):
    self._show_dropdown("service_dropdown")

  def service_menu_mouse_leave(self, event):
    self._hide_dropdown("service_dropdown")

  @handle("custom_site_menu_nav", "click")
  def custom_site_menu_nav_click(self, **event_args):
    self._show_dropdown("custom_site_menu_dropdown")

  def custom_site_menu_mouse_enter(self, event):
    self._show_dropdown("custom_site_menu_dropdown")

  def custom_site_menu_mouse_leave(self, event):
    self._hide_dropdown("custom_site_menu_dropdown")

  @handle("nav_service_tree", "x-category-selected")
  def nav_service_tree_category_selected(self, category_id, **event_args):
    self._close_dropdowns()
    Access.open_window("Contacts", topic=category_id)

  @handle("ai_nav", "click")
  def ai_nav_click(self, **event_args):
    Access.open_window("AIOperator")

  @handle("projects_nav", "click")
  def projects_nav_click(self, **event_args):
    Access.open_window("Projects")
