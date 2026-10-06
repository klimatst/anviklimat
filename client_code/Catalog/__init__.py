from ._anvil_designer import CatalogTemplate
from .. import Access
from anvil import handle
import anvil.media
import anvil.server


class Catalog(CatalogTemplate):
  def __init__(self, category_code=None, search_query="", **properties):
    super().__init__(**properties)
    self.search_box.text = search_query or ""
    self._cursor_stack = []
    self._selected_ids = set()
    self._current_cursor = None
    self._next_cursor = None
    self._active_category_code = None
    self._category_navigation_open = False
    self._filters_open = False
    self._filters_loaded = False
    self._categories = []
    self._categories_by_code = {}
    self._categories_by_id = {}
    context = Access.get_cached_session_context()
    self.is_admin = context["role_code"] == "admin"
    self.can_edit_catalog = self.is_admin or "catalog.manage" in context["permissions"]
    self.can_import_catalog = self.is_admin or "import.manage" in context["permissions"]
    self.sync_lovable_requested = bool(properties.get("sync_lovable")) and self.is_admin

    for name, visible in (
      ("new_product_button", self.can_edit_catalog),
      ("import_button", self.can_import_catalog),
      ("sync_lovable_button", self.is_admin),
      ("manage_categories_button", self.can_edit_catalog),
      ("manage_series_button", self.can_edit_catalog),
      ("add_category_button", self.can_edit_catalog),
      ("bulk_panel", self.can_edit_catalog),
      ("clear_selection_button", self.can_edit_catalog),
      ("export_filter_button", self.can_edit_catalog),
      ("export_selected_button", self.can_edit_catalog),
      ("export_format_dropdown", self.can_edit_catalog),
      ("selection_count", self.can_edit_catalog),
      ("status_filter", self.can_edit_catalog),
    ):
      getattr(self, name).visible = visible

    self.export_format_dropdown.items = [("CSV", "csv"), ("Excel XLSX", "xlsx"), ("JSON", "json")]
    self.export_format_dropdown.selected_value = "csv"
    self.bulk_field_dropdown.items = [
      ("Цена продажи", "sale_price"), ("Закупочная цена", "purchase_price"),
      ("Специальная цена", "special_price"), ("Скидка", "discount"),
      ("Наценка", "markup"), ("Цена монтажа", "installation_price"),
      ("Категория", "category_id"), ("Серия", "series_id"),
      ("Публикация", "active"), ("Остаток", "quantity")
    ]
    self.bulk_mode_dropdown.items = [("Установить значение", "set"), ("Изменить на %", "percent")]
    self.bulk_choice_dropdown.visible = False
    self.bulk_value_box.visible = True

    self.status_filter.items = [
      ("Опубликованные", "active"), ("Черновики и скрытые", "inactive"),
      ("Все товары", "all")
    ]
    self.status_filter.selected_value = "active"
    self.sort_filter.items = [
      ("сначала популярное", "popular"),
      ("низкая цена", "price_asc"),
      ("высокая цена", "price_desc"),
    ]
    self.sort_filter.selected_value = "popular"
    self.available_filter.checked = False
    self.catalog_navigation_toggle_button.text = "☰ Категории"
    self.catalog_view.classes["catalog-navigation-open"] = False
    self.catalog_view.classes["catalog-filters-open"] = False
    self.new_category_panel.visible = False
    self.product_detail_overlay.visible = False

    self._load_categories(category_code or ("air-conditioning" if not search_query else None))
    if self.sync_lovable_requested:
      self._sync_lovable_catalog()
    self._load_page()

  def _fallback_catalog_result(self):
    roots = [
      ("air-conditioning", "Кондиционеры", "conditioners.jpg", [
        ("air-conditioning-split-systems", "Настенные"),
        ("multi-split-systems", "Мультисплит-системы"),
        ("semi-industrial", "Кассетные и полупромышленные")
      ]),
      ("vrf-vrv", "VRV / VRF", "vrv-vrf.jpg", []),
      ("ventilation", "Вентиляция", "ventilation.jpg", []),
      ("heat-equipment", "Отопление", "vrv-vrf.jpg", []),
      ("heat-pumps", "Тепловые насосы", "vrv-vrf.jpg", []),
      ("humidifiers-purifiers", "Очистка и увлажнение", "ventilation.jpg", []),
      ("refrigeration", "Холодильное оборудование", "refrigeration.jpg", []),
      ("installation", "Монтаж и материалы", "materials.jpg", []),
    ]
    categories, tree = [], []
    for order, (code, title, image, children) in enumerate(roots):
      root = {
        "id": code, "code": code, "title": title, "parent_id": None,
        "parent_code": None, "path": title, "description": "",
        "product_count": 0, "child_count": len(children),
        "image_url": "_/theme/catalog/" + image, "active": True,
        "sort_order": order, "children": []
      }
      categories.append(root)
      for child_order, (child_code, child_title) in enumerate(children):
        child = dict(
          root, id=child_code, code=child_code, title=child_title,
          parent_id=code, parent_code=code, path=title + " / " + child_title,
          child_count=0, sort_order=child_order, children=[],
        )
        root["children"].append(child)
        categories.append(child)
      tree.append(root)
    return {"ok": True, "categories": categories, "series": [], "tree": [
      {"id": "direction-home", "code": "direction-home", "title": "Для дома",
       "children": tree[:5], "has_children": True, "expand_icon": "›", "menu_mode": True, "product_count": 0},
      {"id": "direction-business", "code": "direction-business", "title": "Для бизнеса",
       "children": tree[5:], "has_children": True, "expand_icon": "›", "menu_mode": True, "product_count": 0}
    ], "navigation_settings": {}, "site_menu": []}

  def _load_categories(self, category_code=None):
    try:
      result = anvil.server.call("get_catalog_menu_tree", True, True)
    except Exception:
      result = self._fallback_catalog_result()
    if not result.get("ok"):
      result = self._fallback_catalog_result()
    self._categories = result.get("categories", [])
    self._categories_by_code = {row["code"]: row for row in self._categories}
    self._categories_by_id = {row["id"]: row for row in self._categories}
    self._series = result.get("series", [])

    def page_nodes(nodes):
      safe_nodes = []
      for raw in nodes or []:
        if not isinstance(raw, dict):
          continue
        children = page_nodes(raw.get("children") or [])
        node = dict(raw)
        node.setdefault("id", node.get("code"))
        node.setdefault("code", node.get("id"))
        node.setdefault("title", "Категория")
        node.setdefault("children", children)
        node["children"] = children
        node.setdefault("has_children", bool(children))
        node["has_children"] = bool(children) or bool(node.get("has_children"))
        node.setdefault("expand_icon", "›" if node["has_children"] else "")
        node["expand_icon"] = node["expand_icon"] or ("›" if node["has_children"] else "")
        node["menu_mode"] = False
        node["menu_label"] = node.get("title") or "Категория"
        node["selected"] = node.get("code") == category_code
        safe_nodes.append(node)
      return safe_nodes
    self.category_tree.items = page_nodes(result.get("tree", []))
    if self.can_edit_catalog:
      self.new_category_parent.items = [("Основной раздел", None)] + [
        (row.get("path") or row["title"], row["id"]) for row in self._categories
      ]

    self._select_category(category_code, load=False)

  def _ensure_filter_options(self):
    if self._filters_loaded:
      return
    self._load_filter_options()

  def _load_filter_options(self):
    try:
      result = anvil.server.call("get_catalog_filter_options", self._filter_category_value())
    except Exception:
      result = {"ok": False}
    if not result.get("ok"):
      result = {"brands": [], "compressors": [], "countries": [],
                "operation_modes": [], "energy_classes": []}

    def options(values, empty="Все"):
      if not isinstance(values, list):
        values = []
      return [(empty, None)] + [(v.get("title", v), v.get("id", v)) if isinstance(v, dict) else (v, v)
                                for v in values]

    brands = result.get("brands", [])
    if not isinstance(brands, list):
      brands = []
    self.brand_filter.items = [("Все производители", None)] + [
      (row["title"] + " · " + str(row.get("count", 0)), row["id"])
      for row in brands if isinstance(row, dict) and row.get("id") is not None
    ]
    self.compressor_filter.items = options(result.get("compressors", []))
    self.country_filter.items = options(result.get("countries", []))
    self.mode_filter.items = options(result.get("operation_modes", []))
    self.energy_filter.items = options(result.get("energy_classes", []))
    self.installation_filter.items = options(result.get("installations", []))
    self.warranty_filter.items = options(result.get("warranties", []))
    self.indoor_type_filter.items = options(result.get("indoor_types", []))
    for name in ("brand_filter", "compressor_filter", "country_filter", "mode_filter",
                 "energy_filter", "installation_filter", "warranty_filter", "indoor_type_filter"):
      getattr(self, name).selected_value = None
    self._filters_loaded = True

  def _scope_codes(self, category_code=None):
    if category_code in ("direction-home", "direction-business"):
      node = next((row for row in self.category_tree.items if row["code"] == category_code), None)
      codes = {row["code"] for row in (node.get("children", []) if node else [])}
    elif category_code:
      codes = {category_code}
    else:
      return {row["code"] for row in self._categories}
    changed = True
    while changed:
      changed = False
      for row in self._categories:
        if row.get("parent_code") in codes and row["code"] not in codes:
          codes.add(row["code"])
          changed = True
    return codes

  def _filter_category_value(self):
    if self._active_category_code in ("direction-home", "direction-business"):
      return self._active_category_code
    row = self._categories_by_code.get(self._active_category_code)
    return row["id"] if row else None

  def _refresh_heading(self):
    code = self._active_category_code
    if code in ("direction-home", "direction-business"):
      node = next((row for row in self.category_tree.items if row["code"] == code), None)
      title = node["title"] if node else "Каталог"
    elif code:
      title = self._categories_by_code.get(code, {}).get("title", "Каталог")
    else:
      title = "Каталог оборудования"
    if code == "air-conditioning" or (code and code.startswith("air-conditioning-")):
      title = "Кондиционеры" if code == "air-conditioning" else title
    self.page_title.text = title
    self.breadcrumb_rows.items = self._build_breadcrumbs(code)
    self.catalog_total_label.text = ""
    # The target storefront puts related category/topic links above products.
    links = []
    if code:
      links = [row for row in self._categories if row.get("parent_code") == code]
    else:
      links = [row for row in self._categories if not row.get("parent_code")]
    cards = []
    for row in links[:30]:
      cards.append(dict(
        row, summary="{} товаров".format(row.get("product_count", 0)),
        card_description=row.get("description") or "",
        card_type="category"
      ))
    self.category_tiles.items = cards
    self.category_tiles.role = "catalog-reference-links"
    self.category_tiles.visible = bool(cards)

  def _build_breadcrumbs(self, category_code):
    crumbs = [{"title": "Каталог", "code": None}]
    if category_code:
      chain, seen = [], set()
      current = self._categories_by_code.get(category_code)
      while current is not None and current["code"] not in seen:
        seen.add(current["code"])
        chain.append(current)
        current = self._categories_by_code.get(current.get("parent_code"))
      for row in reversed(chain):
        crumbs.append({"title": row["title"], "code": row["code"]})
    for i, row in enumerate(crumbs):
      row["first"] = i == 0
      row["current"] = i == len(crumbs) - 1
    return crumbs

  def _select_category(self, category_code, load=True):
    self._active_category_code = category_code
    self._refresh_heading()
    if load:
      if self._filters_loaded:
        self._load_filter_options()
      self._reset_and_load()

  def _reset_and_load(self):
    self._cursor_stack = []
    self._selected_ids.clear()
    self._update_selection_summary()
    self._load_page()

  def _filter_args(self):
    return {
      "brand": self.brand_filter.selected_value,
      "compressor": self.compressor_filter.selected_value or "",
      "country": self.country_filter.selected_value or "",
      "mode": self.mode_filter.selected_value or "",
      "energy": self.energy_filter.selected_value or "",
      "minimum_area": self.minimum_area_box.text or "",
      "maximum_area": self.maximum_area_box.text or "",
      "minimum_cooling": self.minimum_cooling_box.text or "",
      "maximum_cooling": self.maximum_cooling_box.text or "",
      "minimum_heating": self.minimum_heating_box.text or "",
      "maximum_heating": self.maximum_heating_box.text or "",
      "minimum_consumption_cooling": self.minimum_consumption_cooling_box.text or "",
      "maximum_consumption_cooling": self.maximum_consumption_cooling_box.text or "",
      "minimum_consumption_heating": self.minimum_consumption_heating_box.text or "",
      "maximum_consumption_heating": self.maximum_consumption_heating_box.text or "",
      "minimum_power": self.minimum_power_box.text or "",
      "maximum_power": self.maximum_power_box.text or "",
      "installation": self.installation_filter.selected_value or "",
      "minimum_current": self.minimum_current_box.text or "",
      "maximum_current": self.maximum_current_box.text or "",
      "warranty": self.warranty_filter.selected_value or "",
      "minimum_airflow": self.minimum_airflow_box.text or "",
      "maximum_airflow": self.maximum_airflow_box.text or "",
      "minimum_indoor_units": self.minimum_indoor_units_box.text or "",
      "maximum_indoor_units": self.maximum_indoor_units_box.text or "",
      "indoor_type": self.indoor_type_filter.selected_value or ""
    }

  def _load_page(self, cursor=None):
    self._current_cursor = cursor
    self.previous_button.visible = bool(self._cursor_stack)
    try:
      args = self._filter_args()
      result = anvil.server.call(
        "search_catalog", self.search_box.text or "",
        self._filter_category_value(), cursor,
        self.status_filter.selected_value or "active",
        None, bool(self.available_filter.checked),
        self.minimum_price_box.text or "", self.maximum_price_box.text or "",
        self.sort_filter.selected_value or "popular",
        args["brand"], args["compressor"], args["country"],
        args["mode"], args["energy"], args["minimum_area"], args["maximum_area"],
        {key: value for key, value in args.items() if key not in {
          "brand", "compressor", "country", "mode", "energy",
          "minimum_area", "maximum_area"
        }}
      )
    except Exception as exc:
      self.product_series_rows.items = []
      self.next_button.visible = False
      self.catalog_message.text = "Каталог временно недоступен."
      return
    if not result.get("ok"):
      self.product_series_rows.items = []
      self.next_button.visible = False
      self.catalog_message.text = result.get("message", "Не удалось загрузить каталог.")
      return

    rows = result.get("rows", [])
    for row in rows:
      row["selected"] = row["id"] in self._selected_ids
      row["can_select"] = self.can_edit_catalog and (
        len(self._selected_ids) < 100 or row["selected"]
      )
      row["category_options"] = self._categories
      row["category_path"] = row.get("category_path") or row.get("category") or ""
      row["series_options"] = list(self._series)
    self.product_series_rows.items = rows
    self.product_series_rows.role = "catalog-product-grid"

    self._next_cursor = result.get("next_cursor")
    self.next_button.visible = bool(result.get("has_more"))
    shown = result.get("shown_count", len(rows))
    self.catalog_message.text = "Найдено товаров: {}".format(shown)
    self.catalog_total_label.text = (
      "Показано {}{}"
      .format(shown, " · есть ещё" if result.get("has_more") else "")
    )

  def _update_selection_summary(self):
    count = len(self._selected_ids)
    self.selection_count.text = "Выбрано моделей: {} из 100".format(count)
    self.bulk_apply_button.enabled = self.can_edit_catalog and count > 0
    self.export_selected_button.enabled = self.can_edit_catalog and count > 0

  def _export_catalog(self, selected_only=False):
    product_ids = list(self._selected_ids) if selected_only else None
    if selected_only and not product_ids:
      self.catalog_message.text = "Сначала выберите модели для экспорта."
      return
    result = anvil.server.call(
      "export_catalog", self.search_box.text or "", self._filter_category_value(),
      product_ids, self.export_format_dropdown.selected_value or "csv", None,
      bool(self.available_filter.checked), self.minimum_price_box.text or "",
      self.maximum_price_box.text or "", self.status_filter.selected_value or "active"
    )
    self.catalog_message.text = result.get("message", "")
    if result.get("ok"):
      anvil.media.download(result["file"])

  def _sync_lovable_catalog(self, force=False):
    self.sync_lovable_button.enabled = False
    try:
      result = anvil.server.call("sync_hisense_lovable_catalog", bool(force))
      self.catalog_message.text = result.get("message", "")
      if result.get("ok"):
        self._load_categories(self._active_category_code)
        self._load_filter_options()
        self._reset_and_load()
    except Exception as exc:
      self.catalog_message.text = "Ошибка синхронизации: {}".format(exc)
    finally:
      self.sync_lovable_button.enabled = True

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Form1")

  @handle("new_product_button", "click")
  def new_product_button_click(self, **event_args):
    Access.open_context_window("Catalog.ProductEditor")

  @handle("sync_lovable_button", "click")
  def sync_lovable_button_click(self, **event_args):
    self._sync_lovable_catalog()

  @handle("import_button", "click")
  def import_button_click(self, **event_args):
    Access.open_context_window("ImportEngine")

  @handle("manage_categories_button", "click")
  def manage_categories_button_click(self, **event_args):
    Access.open_context_window("Catalog.Taxonomy")

  @handle("manage_series_button", "click")
  def manage_series_button_click(self, **event_args):
    Access.open_context_window("Catalog.SeriesAdmin")

  @handle("add_category_button", "click")
  def add_category_button_click(self, **event_args):
    self.new_category_panel.visible = not self.new_category_panel.visible

  @handle("save_category_button", "click")
  def save_category_button_click(self, **event_args):
    result = anvil.server.call(
      "add_catalog_category", self.new_category_name_box.text or "",
      self.new_category_parent.selected_value
    )
    self.category_message.text = result.get("message", "")
    if result.get("ok"):
      self.new_category_name_box.text = ""
      self._load_categories(self._active_category_code)

  @handle("search_button", "click")
  def search_button_click(self, **event_args):
    self._reset_and_load()

  @handle("search_box", "pressed_enter")
  def search_box_pressed_enter(self, **event_args):
    self._reset_and_load()

  @handle("catalog_navigation_toggle_button", "click")
  def catalog_navigation_toggle_button_click(self, **event_args):
    self._category_navigation_open = not self._category_navigation_open
    self.catalog_view.classes["catalog-navigation-open"] = self._category_navigation_open

  @handle("show_filters_button", "click")
  def show_filters_button_click(self, **event_args):
    self._ensure_filter_options()
    self._filters_open = not self._filters_open
    self.catalog_view.classes["catalog-filters-open"] = self._filters_open
    self.show_filters_button.text = "Скрыть фильтры" if self._filters_open else "Фильтры"

  @handle("apply_filters_button", "click")
  def apply_filters_button_click(self, **event_args):
    self._filters_open = False
    self.catalog_view.classes["catalog-filters-open"] = False
    self.show_filters_button.text = "Фильтры"
    self._reset_and_load()

  @handle("reset_filters_button", "click")
  def reset_filters_button_click(self, **event_args):
    for name in (
      "minimum_price_box", "maximum_price_box", "minimum_area_box", "maximum_area_box",
      "minimum_cooling_box", "maximum_cooling_box", "minimum_heating_box", "maximum_heating_box",
      "minimum_consumption_cooling_box", "maximum_consumption_cooling_box",
      "minimum_consumption_heating_box", "maximum_consumption_heating_box",
      "minimum_power_box", "maximum_power_box", "minimum_current_box", "maximum_current_box",
      "minimum_airflow_box", "maximum_airflow_box",
      "minimum_indoor_units_box", "maximum_indoor_units_box"
    ):
      getattr(self, name).text = ""
    for name in (
      "brand_filter", "compressor_filter", "country_filter", "mode_filter",
      "energy_filter", "installation_filter", "warranty_filter", "indoor_type_filter"
    ):
      getattr(self, name).selected_value = None
    self.available_filter.checked = False
    self.sort_filter.selected_value = "popular"
    self.status_filter.selected_value = "active"
    self._reset_and_load()

  @handle("sort_filter", "change")
  def sort_filter_change(self, **event_args):
    self._reset_and_load()

  @handle("status_filter", "change")
  def status_filter_change(self, **event_args):
    self._reset_and_load()

  @handle("available_filter", "change")
  def available_filter_change(self, **event_args):
    self._reset_and_load()

  @handle("category_tree", "x-category-selected")
  def category_tree_category_selected(self, category_id=None, category_code=None, **event_args):
    category = category_code or category_id
    if category == category_id:
      row = self._categories_by_id.get(category_id)
      category = row["code"] if row else category
    Access.open_context_window("Catalog", category_code=category)

  @handle("category_tiles", "x-category-selected")
  def category_tiles_category_selected(self, category_code, **event_args):
    Access.open_context_window("Catalog", category_code=category_code)

  @handle("breadcrumb_rows", "x-breadcrumb-selected")
  def breadcrumb_rows_breadcrumb_selected(self, category_code=None, **event_args):
    Access.open_context_window("Catalog", category_code=category_code)

  @handle("product_series_rows", "x-product-selection")
  def product_series_rows_selection(self, product_id, selected, **event_args):
    if selected and product_id not in self._selected_ids and len(self._selected_ids) >= 100:
      self.catalog_message.text = "В одном пакете можно выбрать не более 100 моделей."
      return
    if selected:
      self._selected_ids.add(product_id)
    else:
      self._selected_ids.discard(product_id)
    self._update_selection_summary()

  @handle("product_series_rows", "x-product-details")
  def product_series_rows_product_details(self, product_id, **event_args):
    self.product_detail_form.load_product(product_id)
    self.product_detail_overlay.visible = True

  @handle("product_series_rows", "x-product-order")
  def product_series_rows_product_order(self, product_id, **event_args):
    self.product_detail_form.load_product(product_id)
    self.product_detail_overlay.visible = True

  @handle("product_series_rows", "x-product-refresh")
  def product_series_rows_product_refresh(self, **event_args):
    self._load_page(self._current_cursor)

  @handle("product_detail_form", "close")
  def product_detail_form_close(self, **event_args):
    self.product_detail_overlay.visible = False

  @handle("clear_selection_button", "click")
  def clear_selection_button_click(self, **event_args):
    self._selected_ids.clear()
    self._update_selection_summary()
    self._load_page(self._current_cursor)

  @handle("export_filter_button", "click")
  def export_filter_button_click(self, **event_args):
    self._export_catalog()

  @handle("export_selected_button", "click")
  def export_selected_button_click(self, **event_args):
    self._export_catalog(selected_only=True)

  @handle("bulk_apply_button", "click")
  def bulk_apply_button_click(self, **event_args):
    product_ids = list(self._selected_ids)
    self.bulk_apply_button.enabled = False
    try:
      result = anvil.server.call(
        "bulk_update_prices", product_ids,
        self.bulk_field_dropdown.selected_value,
        self.bulk_choice_dropdown.selected_value if self.bulk_choice_dropdown.visible
        else self.bulk_value_box.text or "",
        self.bulk_mode_dropdown.selected_value
      )
      self.bulk_message.text = result.get("message", "")
      if result.get("ok"):
        self._selected_ids.clear()
        self._update_selection_summary()
        self._load_page(self._current_cursor)
    except Exception as exc:
      self.bulk_message.text = "Не удалось выполнить массовое изменение: {}".format(exc)
    finally:
      self.bulk_apply_button.enabled = bool(self._selected_ids)

  @handle("bulk_field_dropdown", "change")
  def bulk_field_dropdown_change(self, **event_args):
    field = self.bulk_field_dropdown.selected_value
    self.bulk_choice_dropdown.visible = field in ("category_id", "series_id", "active")
    self.bulk_value_box.visible = not self.bulk_choice_dropdown.visible
    self.bulk_mode_dropdown.selected_value = "set"
    self.bulk_mode_dropdown.enabled = field in {
      "purchase_price", "sale_price", "special_price", "discount", "markup", "installation_price"
    }
    if field == "category_id":
      self.bulk_choice_dropdown.items = [("Выберите категорию", None)] + [
        (row.get("path") or row["title"], row["id"]) for row in self._categories
      ]
      self.bulk_choice_dropdown.selected_value = None
    elif field == "series_id":
      self.bulk_choice_dropdown.items = [("Без серии", "")] + [
        (row["title"], row["id"]) for row in self._series
      ]
      self.bulk_choice_dropdown.selected_value = ""
    elif field == "active":
      self.bulk_choice_dropdown.items = [("Опубликован", "active"), ("Скрыт", "inactive")]
      self.bulk_choice_dropdown.selected_value = "active"

  @handle("next_button", "click")
  def next_button_click(self, **event_args):
    if self._next_cursor is None:
      return
    self._cursor_stack.append(self._current_cursor)
    self._load_page(self._next_cursor)

  @handle("previous_button", "click")
  def previous_button_click(self, **event_args):
    if not self._cursor_stack:
      return
    self._load_page(self._cursor_stack.pop())
