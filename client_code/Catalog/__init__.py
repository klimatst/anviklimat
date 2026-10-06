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
    self._expanded_series_key = None
    self._category_navigation_open = False
    self._categories = []
    self._categories_by_code = {}
    self._categories_by_id = {}
    self._series = []
    context = Access.get_cached_session_context()
    self.is_admin = context["role_code"] == "admin"
    self.can_edit_catalog = self.is_admin or "catalog.manage" in context["permissions"]
    self.can_import_catalog = self.is_admin or "import.manage" in context["permissions"]

    self.new_product_button.visible = self.can_edit_catalog
    self.import_button.visible = self.can_import_catalog
    self.manage_categories_button.visible = self.can_edit_catalog
    self.manage_series_button.visible = self.can_edit_catalog
    self.add_category_button.visible = self.can_edit_catalog
    self.bulk_panel.visible = self.can_edit_catalog
    self.clear_selection_button.visible = self.can_edit_catalog
    self.export_filter_button.visible = self.can_edit_catalog
    self.export_selected_button.visible = self.can_edit_catalog
    self.export_format_dropdown.visible = self.can_edit_catalog
    self.selection_count.visible = self.can_edit_catalog
    self.status_filter.visible = self.can_edit_catalog
    self.bulk_apply_button.enabled = False
    self.export_selected_button.enabled = False
    self.export_format_dropdown.items = [("CSV", "csv"), ("Excel XLSX", "xlsx"), ("JSON", "json")]
    self.export_format_dropdown.selected_value = "csv"
    self.bulk_field_dropdown.items = [
      ("Цена продажи", "sale_price"), ("Закупочная цена", "purchase_price"),
      ("Специальная цена", "special_price"), ("Скидка", "discount"),
      ("Наценка", "markup"), ("Цена монтажа", "installation_price"),
      ("Категория", "category_id"), ("Серия", "series_id"),
      ("Публикация", "active"), ("Остаток", "quantity")
    ]
    self.bulk_mode_dropdown.items = [
      ("Установить значение", "set"), ("Изменить на %", "percent")
    ]
    self.bulk_choice_dropdown.visible = False
    self.bulk_value_box.visible = True
    self.status_filter.items = [
      ("Опубликованные", "active"), ("Черновики и скрытые", "inactive"),
      ("Все товары", "all")
    ]
    self.status_filter.selected_value = "active"
    self.sort_filter.items = [("Модель · А—Я", "model_asc"), ("Модель · Я—А", "model_desc")]
    self.sort_filter.selected_value = "model_asc"
    self.available_filter.checked = False
    self.catalog_navigation_toggle_button.text = "Все категории"
    self.catalog_view.classes["catalog-navigation-open"] = False
    self.new_category_panel.visible = False
    self.product_detail_overlay.visible = False
    self._load_categories(category_code)
    self._load_page()

  def _load_categories(self, category_code=None):
    result = anvil.server.call("get_catalog_menu_tree")
    if not result["ok"]:
      self.catalog_message.text = "Не удалось загрузить дерево каталога."
      self.category_tree.items = []
      self.category_tiles.items = []
      return
    self._categories = result["categories"]
    self._categories_by_code = {row["code"]: row for row in self._categories}
    self._categories_by_id = {row["id"]: row for row in self._categories}
    self._series = result.get("series", [])
    def page_nodes(nodes):
      return [
        dict(
          row, menu_mode=False, menu_label=row["title"],
          selected=row["code"] == category_code,
          children=page_nodes(row.get("children", []))
        )
        for row in nodes
      ]
    self.category_tree.items = page_nodes(result["tree"])
    self.category_filter.items = [("Все категории", None)] + [
      (row.get("path") or row["title"], row["id"])
      for row in self._categories
    ]
    if self.can_edit_catalog:
      self.new_category_parent.items = [("Основной раздел", None)] + [
        (row.get("path") or row["title"], row["id"])
        for row in self._categories
      ]
    if category_code:
      self._select_category(category_code, load=False)
    else:
      self._select_category(None, load=False)

  def _scope_codes(self, category_code=None):
    if category_code in ("direction-home", "direction-business"):
      direction = next((row for row in self.category_tree.items if row["code"] == category_code), None)
      roots = direction.get("children", []) if direction else []
      codes = {row["code"] for row in roots}
    elif category_code:
      codes = {category_code}
    else:
      return {row["code"] for row in self._categories}
    changed = True
    while changed:
      changed = False
      for row in self._categories:
        if row["parent_code"] in codes and row["code"] not in codes:
          codes.add(row["code"])
          changed = True
    return codes

  def _filter_category_value(self):
    if self._active_category_code in ("direction-home", "direction-business"):
      return self._active_category_code
    if self._active_category_code:
      row = self._categories_by_code.get(self._active_category_code)
      return row["id"] if row else None
    return self.category_filter.selected_value

  def _refresh_category_heading(self):
    code = self._active_category_code
    if not code:
      if (self.search_box.text or "").strip():
        title = "Результаты поиска"
        description = "Модели по всей номенклатуре каталога."
        children = []
      else:
        title = "Каталог оборудования"
        description = "Подберите оборудование по назначению, категории и серии."
        children = list(self.category_tree.items)
    elif code in ("direction-home", "direction-business"):
      direction = next((row for row in self.category_tree.items if row["code"] == code), None)
      title = direction["title"] if direction else "Каталог"
      description = (
        "Оборудование для жилых и небольших коммерческих объектов."
        if code == "direction-home" else
        "Инженерное оборудование для коммерческих и промышленных объектов."
      )
      children = direction.get("children", []) if direction else []
    else:
      row = self._categories_by_code.get(code)
      if row is None:
        self._active_category_code = None
        return self._refresh_category_heading()
      title = row["title"]
      description = row.get("description") or "Выберите серию, сравните характеристики и откройте карточку модели."
      children = [item for item in self._categories if item["parent_code"] == code]

    self.page_title.text = title
    self.category_description.text = description
    self.breadcrumb_rows.items = self._build_breadcrumbs(code)
    self.catalog_panel.visible = bool(
      (self.search_box.text or "").strip()
      or (code and code not in ("direction-home", "direction-business"))
    )
    cards = []
    for row in children:
      is_direction = row["code"] in ("direction-home", "direction-business")
      if is_direction:
        card_description = (
          "Решения для квартир, частных домов и небольших объектов."
          if row["code"] == "direction-home" else
          "Инженерные системы для коммерческих и промышленных объектов."
        )
        summary = "{} моделей · {} разделов".format(
          row.get("product_count", 0),
          row.get("child_count", len(row.get("children", [])))
        )
      else:
        card_description = row.get("description") or "Оборудование и серии этого раздела каталога."
        summary = "{} моделей · {} подразделений".format(
          row.get("product_count", 0),
          row.get("child_count", len(row.get("children", [])))
        )
      cards.append(dict(
        row, summary=summary, card_description=card_description,
        card_type="direction" if is_direction else "category"
      ))
    self.category_tiles.items = cards
    self.category_tiles.role = (
      "catalog-direction-grid"
      if cards and all(row.get("card_type") == "direction" for row in cards)
      else "catalog-category-grid"
    )
    scopes = self._scope_codes(code)
    selected_category_ids = {
      row["id"] for row in self._categories if row["code"] in scopes
    }
    series_options = [row for row in self._series if row.get("category_id") in selected_category_ids]
    self.series_filter.items = [("Все серии", None)] + [
      (row["title"], row["id"]) for row in series_options
    ]
    self.series_filter.selected_value = None
    self._expanded_series_key = None
    self._refresh_series_navigation(series_options)

  def _refresh_series_navigation(self, series_options=None):
    if series_options is None:
      selected_category_ids = {
        row["id"] for row in self._categories
        if row["code"] in self._scope_codes(self._active_category_code)
      }
      series_options = [
        row for row in self._series
        if row.get("category_id") in selected_category_ids
      ]
    selected_id = self.series_filter.selected_value
    links = [{
      "title": "Все серии", "series_id": None, "group_key": None,
      "selected": selected_id is None
    }]
    links.extend({
      "title": row["title"], "series_id": row["id"],
      "group_key": "series:" + row["id"],
      "selected": row["id"] == selected_id
    } for row in series_options)
    self.series_quick_links.items = links
    self.catalog_series_navigation.classes["is-hidden"] = not bool(
      self.catalog_panel.visible and series_options
    )

  def _build_breadcrumbs(self, category_code):
    crumbs = [{"title": "Каталог", "code": None}]
    if not category_code:
      crumbs[0]["current"] = True
      crumbs[0]["first"] = True
      return crumbs

    if category_code in ("direction-home", "direction-business"):
      direction = next((
        row for row in self.category_tree.items if row["code"] == category_code
      ), None)
      if direction:
        crumbs.append({"title": direction["title"], "code": category_code})
    else:
      chain = []
      visited = set()
      current = self._categories_by_code.get(category_code)
      while current is not None and current["code"] not in visited:
        visited.add(current["code"])
        chain.append(current)
        current = self._categories_by_code.get(current.get("parent_code"))
      chain.reverse()
      if chain:
        root_code = chain[0]["code"]
        direction = next((
          row for row in self.category_tree.items
          if row["code"] in ("direction-home", "direction-business")
          and self._tree_has_category(row, root_code)
        ), None)
        if direction:
          crumbs.append({"title": direction["title"], "code": direction["code"]})
        crumbs.extend({"title": row["title"], "code": row["code"]} for row in chain)

    for index, crumb in enumerate(crumbs):
      crumb["first"] = index == 0
      crumb["current"] = index == len(crumbs) - 1
    return crumbs

  def _tree_has_category(self, node, category_code):
    if node.get("code") == category_code:
      return True
    return any(
      self._tree_has_category(child, category_code)
      for child in node.get("children", [])
    )

  def _select_category(self, category_code, load=True):
    self._active_category_code = category_code
    if category_code and category_code not in ("direction-home", "direction-business"):
      row = self._categories_by_code.get(category_code)
      self.category_filter.selected_value = row["id"] if row else None
    else:
      self.category_filter.selected_value = None
    self._refresh_category_heading()
    if load and self._categories:
      self._reset_and_load()

  def _load_page(self, cursor=None):
    self._current_cursor = cursor
    self.previous_button.visible = bool(self._cursor_stack)
    if not self.catalog_panel.visible:
      self.product_series_rows.items = []
      self.previous_button.visible = False
      self.next_button.visible = False
      return
    result = anvil.server.call(
      "search_catalog", self.search_box.text or "",
      self._filter_category_value(), cursor,
      self.status_filter.selected_value or "active",
      self.series_filter.selected_value,
      bool(self.available_filter.checked),
      self.minimum_price_box.text or "", self.maximum_price_box.text or "",
      self.sort_filter.selected_value or "model_asc"
    )
    if not result["ok"]:
      self.product_series_rows.items = []
      self.next_button.visible = False
      self.catalog_message.text = result["message"]
      return
    rows = result["rows"]
    for row in rows:
      row["selected"] = row["id"] in self._selected_ids
      row["can_select"] = self.can_edit_catalog and (
        len(self._selected_ids) < 100 or row["selected"]
      )
      row["category_options"] = self._categories
      category_option = self._categories_by_id.get(row.get("edit_category_id"))
      if category_option is not None:
        row["category_path"] = category_option.get("path") or row.get("category_path")
      row["series_options"] = list(self._series)
      if row.get("series_id") and not any(
        item["id"] == row["series_id"] for item in row["series_options"]
      ):
        row["series_options"].append({
          "id": row["series_id"], "title": row.get("series_title") or "Текущая серия"
        })
    groups = self._group_series(rows)
    self.product_series_rows.items = groups
    self._refresh_series_navigation()
    self._next_cursor = result["next_cursor"]
    self.next_button.visible = result["has_more"]
    self.catalog_message.text = (
      "Найдено моделей на странице: {}".format(len(rows))
      if rows else "По заданным условиям модели не найдены."
    )

  def _group_series(self, rows):
    groups = {}
    for row in rows:
      series_id = row.get("series_id")
      group_key = "series:" + series_id if series_id else "category:{}".format(
        row.get("subcategory_id") or row.get("category_id") or "other"
      )
      if group_key not in groups:
        title = row.get("series_title") or row.get("subcategory") or row.get("category") or "Модели без серии"
        groups[group_key] = {
          "group_key": group_key,
          "id": series_id, "title": title,
          "description": row.get("series_description") or "",
          "power_range": row.get("series_power_range") or "",
          "is_new": bool(row.get("series_is_new")),
          "image_url": row.get("series_image_url") or "",
          "documents": row.get("series_documents", []),
          "models": [], "expanded": group_key == self._expanded_series_key
        }
      groups[group_key]["models"].append(row)
    result = []
    for group in groups.values():
      models = group["models"]
      keys = {}
      for model in models:
        for spec in model.get("specs", []):
          label = spec.get("key") or ""
          label_key = str(label).lower()
          if label and label_key not in keys:
            keys[label_key] = label
      preferred = (
        "Мощность охлаждения", "Мощность обогрева", "Габариты внутреннего блока",
        "Производительность охлаждения", "Производительность обогрева",
        "Расход воздуха", "Воздушный расход", "Напор", "Габариты"
      )
      ordered_keys = sorted(
        keys.values(),
        key=lambda key: (
          preferred.index(key) if key in preferred else len(preferred),
          str(key).lower()
        )
      )[:4]
      while len(ordered_keys) < 4:
        ordered_keys.append("")
      group["columns"] = [{"title": key} for key in ordered_keys]
      for model in models:
        values = {
          str(spec.get("key") or "").lower(): "{}{}".format(
            spec.get("value") or "", " " + spec.get("unit", "") if spec.get("unit") else ""
          ).strip()
          for spec in model.get("specs", [])
        }
        model["spec_values"] = [
          {"title": key, "value": values.get(str(key).lower(), "—")}
          for key in ordered_keys
        ]
      result.append(group)
    return result

  def _reset_and_load(self):
    self._cursor_stack = []
    self._selected_ids.clear()
    self._update_selection_summary()
    self._load_page()

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
      "export_catalog", self.search_box.text or "",
      self._filter_category_value(), product_ids,
      self.export_format_dropdown.selected_value or "csv",
      self.series_filter.selected_value, bool(self.available_filter.checked),
      self.minimum_price_box.text or "", self.maximum_price_box.text or "",
      self.status_filter.selected_value or "active"
    )
    self.catalog_message.text = result["message"]
    if result["ok"]:
      anvil.media.download(result["file"])

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Form1")

  @handle("new_product_button", "click")
  def new_product_button_click(self, **event_args):
    Access.open_context_window("Catalog.ProductEditor")

  @handle("import_button", "click")
  def import_button_click(self, **event_args):
    Access.open_context_window("ImportEngine")

  @handle("manage_categories_button", "click")
  def manage_categories_button_click(self, **event_args):
    Access.open_context_window("Catalog.Taxonomy")

  @handle("manage_series_button", "click")
  def manage_series_button_click(self, **event_args):
    Access.open_context_window("Catalog.SeriesAdmin")

  @handle("search_button", "click")
  def search_button_click(self, **event_args):
    self._refresh_category_heading()
    self._reset_and_load()

  @handle("search_box", "pressed_enter")
  def search_box_pressed_enter(self, **event_args):
    self._refresh_category_heading()
    self._reset_and_load()

  @handle("catalog_navigation_toggle_button", "click")
  def catalog_navigation_toggle_button_click(self, **event_args):
    self._category_navigation_open = not self._category_navigation_open
    self.catalog_view.classes["catalog-navigation-open"] = self._category_navigation_open
    self.catalog_navigation_toggle_button.text = (
      "Скрыть категории" if self._category_navigation_open else "Все категории"
    )

  @handle("category_filter", "change")
  def category_filter_change(self, **event_args):
    selected = self._categories_by_id.get(self.category_filter.selected_value)
    Access.open_context_window(
      "Catalog",
      category_code=selected["code"] if selected else None,
      search_query=self.search_box.text or ""
    )

  @handle("category_tree", "x-category-selected")
  def category_tree_category_selected(self, category_id=None, category_code=None, **event_args):
    category = category_code or category_id
    if category == category_id and category not in self._categories_by_code:
      row = self._categories_by_id.get(category_id)
      category = row["code"] if row else category
    Access.open_context_window("Catalog", category_code=category)

  @handle("category_tiles", "x-category-selected")
  def category_tiles_category_selected(self, category_code, **event_args):
    Access.open_context_window("Catalog", category_code=category_code)

  @handle("breadcrumb_rows", "x-breadcrumb-selected")
  def breadcrumb_rows_breadcrumb_selected(self, category_code=None, **event_args):
    Access.open_context_window("Catalog", category_code=category_code)

  @handle("series_filter", "change")
  def series_filter_change(self, **event_args):
    self._expanded_series_key = None
    self._refresh_series_navigation()
    self._reset_and_load()

  @handle("series_quick_links", "x-series-selected")
  def series_quick_links_series_selected(self, series_id=None, group_key=None, **event_args):
    self.series_filter.selected_value = series_id
    self._expanded_series_key = group_key
    self._refresh_series_navigation()
    self._reset_and_load()

  @handle("available_filter", "change")
  def available_filter_change(self, **event_args):
    self._reset_and_load()

  @handle("sort_filter", "change")
  def sort_filter_change(self, **event_args):
    self._reset_and_load()

  @handle("status_filter", "change")
  def status_filter_change(self, **event_args):
    self._reset_and_load()

  @handle("product_series_rows", "x-product-selection")
  def product_series_rows_selection(self, product_id, selected, **event_args):
    if selected and product_id not in self._selected_ids and len(self._selected_ids) >= 100:
      self.catalog_message.text = "В одном пакете можно выбрать не более 100 моделей."
      self._load_page(self._current_cursor)
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
    except Exception as exc:
      self.bulk_message.text = "Не удалось выполнить массовое изменение: {}".format(exc)
      return
    finally:
      self.bulk_apply_button.enabled = bool(self._selected_ids)
    self.bulk_message.text = result["message"]
    if result["ok"]:
      self._selected_ids.clear()
      self._update_selection_summary()
      self._load_page(self._current_cursor)

  @handle("bulk_field_dropdown", "change")
  def bulk_field_dropdown_change(self, **event_args):
    field = self.bulk_field_dropdown.selected_value
    self.bulk_choice_dropdown.visible = field in ("category_id", "series_id", "active")
    self.bulk_value_box.visible = not self.bulk_choice_dropdown.visible
    self.bulk_mode_dropdown.selected_value = "set"
    self.bulk_mode_dropdown.enabled = field in {
      "purchase_price", "sale_price", "special_price", "discount", "markup",
      "installation_price"
    }
    if field == "category_id":
      self.bulk_choice_dropdown.items = [("Выберите категорию", None)] + [
        (row.get("path") or row["title"], row["id"])
        for row in self._categories
      ]
      self.bulk_choice_dropdown.selected_value = None
    elif field == "series_id":
      self.bulk_choice_dropdown.items = [("Без серии", "")] + [
        (row["title"], row["id"]) for row in self._series
      ]
      self.bulk_choice_dropdown.selected_value = ""
    elif field == "active":
      self.bulk_choice_dropdown.items = [
        ("Опубликован", "active"), ("Скрыт", "inactive")
      ]
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

  @handle("add_category_button", "click")
  def add_category_button_click(self, **event_args):
    self.new_category_panel.visible = not self.new_category_panel.visible

  @handle("save_category_button", "click")
  def save_category_button_click(self, **event_args):
    result = anvil.server.call(
      "add_catalog_category", self.new_category_name_box.text or "",
      self.new_category_parent.selected_value
    )
    self.category_message.text = result["message"]
    if result["ok"]:
      self.new_category_name_box.text = ""
      self._load_categories(self._active_category_code)
      self._load_page()
