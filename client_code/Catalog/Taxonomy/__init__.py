from ._anvil_designer import TaxonomyTemplate
from anvil import confirm, handle
import anvil.server
from ... import Access


class Taxonomy(TaxonomyTemplate):
  def __init__(self, selected_category_id=None, selected_brand_id=None,
               category_view="all", **properties):
    super().__init__(**properties)
    if not Access.require_permission_form("catalog.manage"):
      return
    self._category_view = category_view if category_view in ("all", "categories", "subcategories") else "all"
    view_titles = {
      "all": "Категории, бренды и поля каталога",
      "categories": "Категории каталога",
      "subcategories": "Подкатегории каталога"
    }
    self.page_title.text = view_titles[self._category_view]
    self.category_list_heading.text = view_titles[self._category_view]
    self.new_category_button.visible = self._category_view != "subcategories"
    self.new_subcategory_button.visible = self._category_view != "categories"
    self._categories = []
    self._category_id = None
    self._brand_id = None
    self._custom_field_id = None
    self._custom_fields = []
    self._load_data()
    self._new_category()
    self._new_brand()
    if selected_category_id:
      row = self._categories_by_id.get(selected_category_id)
      if row:
        self._show_category(row)
    if selected_brand_id:
      brand = next((
        row for row in self.brand_rows.items if row["id"] == selected_brand_id
      ), None)
      if brand:
        self._show_brand(brand)

  def _load_data(self, selected_category_id=None, selected_brand_id=None):
    result = anvil.server.call("get_catalog_admin_data")
    self._categories = result["categories"]
    self._categories_by_id = {row["id"]: row for row in self._categories}
    for row in self._categories:
      prefix = "— " * row.get("depth", 0)
      row["display_title"] = prefix + row["title"]
    if self._category_view == "categories":
      visible_categories = [row for row in self._categories if not row.get("parent_id")]
    elif self._category_view == "subcategories":
      visible_categories = [row for row in self._categories if row.get("parent_id")]
    else:
      visible_categories = self._categories
    self.category_rows.items = visible_categories
    self.brand_rows.items = result["brands"]
    self.category_parent_dropdown.items = [("Основной раздел", None)] + [
      (row["path"], row["id"])
      for row in self._categories
      if row["id"] != self._category_id and not self._is_descendant(row["id"], self._category_id)
    ]
    if selected_category_id:
      selected = self._categories_by_id.get(selected_category_id)
      if selected:
        self._show_category(selected)
    if selected_brand_id:
      brand = next((row for row in result["brands"] if row["id"] == selected_brand_id), None)
      if brand:
        self._show_brand(brand)
    self.taxonomy_message.text = "Показано категорий: {} из {} · брендов: {}".format(
      len(visible_categories), len(self._categories), len(result["brands"])
    )

  def _new_category(self, parent_id=None):
    self._category_id = None
    self.category_title_box.text = ""
    self.category_parent_dropdown.selected_value = parent_id
    self.category_active_checkbox.checked = True
    self.category_order_box.text = "1000"
    self.category_description_box.text = ""
    self.category_meta_title_box.text = ""
    self.category_meta_description_box.text = ""
    self.category_image_file.files = []
    self.category_image_preview.source = ""
    self.category_image_preview.visible = False
    self.category_image_remove_checkbox.checked = False
    self.category_editor_heading.text = "Новая категория"
    self.category_delete_button.visible = False
    self.category_message.text = ""
    self.custom_fields_manager.visible = False
    self.custom_field_editor.visible = False
    self.field_rows.items = []

  def _show_category(self, row):
    self._category_id = row["id"]
    self.category_title_box.text = row["title"]
    self.category_parent_dropdown.selected_value = row["parent_id"]
    self.category_active_checkbox.checked = row["active"]
    self.category_order_box.text = str(row["sort_order"])
    self.category_description_box.text = row.get("description") or ""
    self.category_meta_title_box.text = row.get("meta_title") or ""
    self.category_meta_description_box.text = row.get("meta_description") or ""
    self.category_image_file.files = []
    self.category_image_preview.source = row.get("image_url") or ""
    self.category_image_preview.visible = bool(row.get("image_url"))
    self.category_image_remove_checkbox.checked = False
    self.category_editor_heading.text = "Изменить: {}".format(row["title"])
    self.category_delete_button.visible = True
    self.category_message.text = (
      "В товарах: {} · подкатегорий: {}".format(
        row["product_count"], row["child_count"]
      )
    )
    self._load_custom_fields(row["id"])

  def _load_custom_fields(self, category_id, selected_field_id=None):
    result = anvil.server.call("get_catalog_custom_field_definitions", category_id)
    if not result["ok"]:
      self.custom_fields_manager.visible = False
      self.custom_field_message.text = result["message"]
      return
    self.custom_fields_manager.visible = True
    self._custom_fields = result["fields"]
    self.field_rows.items = self._custom_fields
    self.custom_field_type_dropdown.items = result["types"]
    if selected_field_id:
      field = next((item for item in self._custom_fields if item["id"] == selected_field_id), None)
      if field:
        self._show_custom_field(field)
        return
    self._new_custom_field()

  def _new_custom_field(self):
    self._custom_field_id = None
    self.custom_field_editor_heading.text = "НОВОЕ ПОЛЕ · ВАРИАНТЫ НАСТРОЕК"
    self.custom_field_code_box.enabled = True
    self.custom_field_code_box.text = ""
    self.custom_field_title_box.text = ""
    self.custom_field_type_dropdown.selected_value = "text"
    self.custom_field_unit_box.text = ""
    self.custom_field_choices_box.text = ""
    self.custom_field_order_box.text = str((len(self._custom_fields) + 1) * 10)
    self.custom_field_required_checkbox.checked = False
    self.custom_field_public_checkbox.checked = False
    self.custom_field_enabled_checkbox.checked = True
    self.disable_custom_field_button.visible = False
    self.custom_field_editor.visible = True
    self.custom_field_message.text = ""

  def _show_custom_field(self, field):
    self._custom_field_id = field["id"]
    self.custom_field_editor_heading.text = "ИЗМЕНИТЬ ПОЛЕ · {}".format(field["code"])
    self.custom_field_code_box.enabled = False
    self.custom_field_code_box.text = field["code"]
    self.custom_field_title_box.text = field["title"]
    self.custom_field_type_dropdown.selected_value = field["kind"]
    self.custom_field_unit_box.text = field.get("unit", "")
    self.custom_field_choices_box.text = "\n".join(field.get("choices", []))
    self.custom_field_order_box.text = str(field.get("sort_order", 0))
    self.custom_field_required_checkbox.checked = bool(field.get("required"))
    self.custom_field_public_checkbox.checked = bool(field.get("show_public"))
    self.custom_field_enabled_checkbox.checked = bool(field.get("enabled", True))
    self.disable_custom_field_button.visible = bool(field.get("enabled", True))
    self.custom_field_editor.visible = True
    self.custom_field_message.text = ""

  def _new_brand(self):
    self._brand_id = None
    self.brand_name_box.text = ""
    self.brand_editor_heading.text = "Новый бренд"
    self.brand_delete_button.visible = False
    self.brand_message.text = ""

  def _show_brand(self, row):
    self._brand_id = row["id"]
    self.brand_name_box.text = row["name"]
    self.brand_editor_heading.text = "Изменить: {}".format(row["name"])
    self.brand_delete_button.visible = True
    self.brand_message.text = "Карточек товаров: {}".format(row["product_count"])

  def _is_descendant(self, candidate_id, ancestor_id):
    if not ancestor_id:
      return False
    current = self._categories_by_id.get(candidate_id)
    visited = set()
    while current and current.get("parent_id"):
      parent_id = current["parent_id"]
      if parent_id == ancestor_id:
        return True
      if parent_id in visited:
        return False
      visited.add(parent_id)
      current = self._categories_by_id.get(parent_id)
    return False

  @handle("category_rows", "x-edit-category")
  def category_rows_edit_category(self, category_id, **event_args):
    row = self._categories_by_id.get(category_id)
    if row:
      self._show_category(row)

  @handle("field_rows", "x-edit-custom-field")
  def field_rows_edit_custom_field(self, field_id, **event_args):
    field = next((item for item in self._custom_fields if item["id"] == field_id), None)
    if field:
      self._show_custom_field(field)

  @handle("new_field_button", "click")
  def new_field_button_click(self, **event_args):
    if self._category_id is None:
      self.custom_field_message.text = "Сначала сохраните категорию."
      return
    self._new_custom_field()

  @handle("save_custom_field_button", "click")
  def save_custom_field_button_click(self, **event_args):
    if self._category_id is None:
      self.custom_field_message.text = "Сначала сохраните категорию."
      return
    choices = [
      item.strip() for item in (self.custom_field_choices_box.text or "").splitlines()
      if item.strip()
    ]
    result = anvil.server.call(
      "save_catalog_custom_field", self._category_id, self._custom_field_id,
      self.custom_field_code_box.text or "", self.custom_field_title_box.text or "",
      self.custom_field_type_dropdown.selected_value,
      choices, self.custom_field_unit_box.text or "",
      self.custom_field_required_checkbox.checked,
      self.custom_field_public_checkbox.checked,
      self.custom_field_enabled_checkbox.checked,
      self.custom_field_order_box.text or "0"
    )
    self.custom_field_message.text = result["message"]
    if result["ok"]:
      self._load_custom_fields(self._category_id, result["field_id"])

  @handle("disable_custom_field_button", "click")
  def disable_custom_field_button_click(self, **event_args):
    if not self._custom_field_id:
      return
    if not confirm(
      "Отключить поле? Ранее сохранённые значения товаров останутся в базе.",
      title="Отключить поле каталога"
    ):
      return
    result = anvil.server.call(
      "disable_catalog_custom_field", self._category_id, self._custom_field_id
    )
    self.custom_field_message.text = result["message"]
    if result["ok"]:
      self._load_custom_fields(self._category_id)

  @handle("brand_rows", "x-edit-brand")
  def brand_rows_edit_brand(self, brand_id, **event_args):
    row = next((
      item for item in self.brand_rows.items if item["id"] == brand_id
    ), None)
    if row:
      self._show_brand(row)

  @handle("new_category_button", "click")
  def new_category_button_click(self, **event_args):
    self._new_category()

  @handle("new_subcategory_button", "click")
  def new_subcategory_button_click(self, **event_args):
    selected = self._categories_by_id.get(self._category_id)
    parent_id = selected["id"] if selected else None
    self._new_category(parent_id)

  @handle("save_category_button", "click")
  def save_category_button_click(self, **event_args):
    result = anvil.server.call(
      "save_catalog_category",
      self._category_id,
      self.category_title_box.text or "",
      self.category_parent_dropdown.selected_value,
      self.category_active_checkbox.checked,
      self.category_order_box.text or "",
      self.category_description_box.text or "",
      self.category_meta_title_box.text or "",
      self.category_meta_description_box.text or "",
      (self.category_image_file.files or [None])[0],
      self.category_image_remove_checkbox.checked
    )
    self.category_message.text = result["message"]
    if result["ok"]:
      self._category_id = result["category_id"]
      self._load_data(selected_category_id=self._category_id)

  @handle("category_delete_button", "click")
  def category_delete_button_click(self, **event_args):
    if not confirm("Удалить выбранную категорию? Используемые категории защищены от удаления."):
      return
    result = anvil.server.call("delete_catalog_category", self._category_id)
    self.category_message.text = result["message"]
    if result["ok"]:
      self._load_data()
      self._new_category()

  @handle("new_brand_button", "click")
  def new_brand_button_click(self, **event_args):
    self._new_brand()

  @handle("save_brand_button", "click")
  def save_brand_button_click(self, **event_args):
    result = anvil.server.call(
      "save_catalog_brand", self._brand_id, self.brand_name_box.text or ""
    )
    self.brand_message.text = result["message"]
    if result["ok"]:
      self._brand_id = result["brand_id"]
      self._load_data(selected_brand_id=self._brand_id)

  @handle("brand_delete_button", "click")
  def brand_delete_button_click(self, **event_args):
    if not confirm("Удалить выбранный бренд? Бренд с товарами удалить нельзя."):
      return
    result = anvil.server.call("delete_catalog_brand", self._brand_id)
    self.brand_message.text = result["message"]
    if result["ok"]:
      self._load_data()
      self._new_brand()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
