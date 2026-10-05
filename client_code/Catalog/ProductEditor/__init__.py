from ._anvil_designer import ProductEditorTemplate
from anvil import confirm, handle
import anvil.server
from ... import Access


class ProductEditor(ProductEditorTemplate):
  def __init__(self, product_id=None, **properties):
    super().__init__(**properties)
    self.product_id = product_id
    self._categories = []
    if not Access.require_permission_form("catalog.manage"):
      return

    result = anvil.server.call("get_product_editor_data", product_id)
    if not result["ok"]:
      self.product_status.text = result["message"]
      self.product_form.visible = False
      return

    self._categories = result["categories"]
    self._series = result.get("series", [])
    self._categories_by_code = {
      row["code"]: row for row in self._categories
    }
    root_categories = [row for row in self._categories if row["parent_code"] is None]
    self.category_dropdown.items = [("Выберите категорию", None)] + [
      (row.get("path") or row["title"], row["id"]) for row in root_categories
    ]
    self.document_kind_dropdown.items = [
      ("Инструкция", "instruction"), ("Технические данные", "datasheet"),
      ("Сертификат", "certificate"), ("Другой документ", "other")
    ]
    self.document_kind_dropdown.selected_value = "instruction"
    self._set_subcategory_options()
    self._set_series_options()
    self._fill_form(result["data"])
    self.product_id = result["product_id"]
    self.specs_panel.visible = self.product_id is not None
    self.spec_rows.items = result["specs"]
    self._custom_fields = result.get("custom_fields", [])
    self.custom_field_rows.items = self._custom_fields
    self.media_panel.visible = self.product_id is not None
    self.media_rows.items = result.get("media", [])
    self.document_panel.visible = self.product_id is not None
    self.document_rows.items = [dict(row, can_delete=True) for row in result.get("documents", [])]
    self.specs_tab_button.visible = self.product_id is not None
    self.custom_fields_tab_button.visible = bool(self._custom_fields)
    self.media_tab_button.visible = self.product_id is not None
    self.documents_tab_button.visible = self.product_id is not None
    self.duplicate_button.visible = self.product_id is not None
    self.delete_button.visible = self.product_id is not None
    self.product_status.text = "Редактирование карточки" if self.product_id else "Новая карточка товара"
    self._show_product_tab("basic")

  def _show_product_tab(self, tab_code):
    labels = {
      "basic": "Основные сведения",
      "pricing": "Цена и наличие",
      "specs": "Характеристики",
      "custom_fields": "Дополнительные поля категории",
      "media": "Изображения модели",
      "documents": "Документы и инструкции",
      "source": "Источник данных"
    }
    panels = {
      "basic": self.product_basic_tab,
      "pricing": self.product_pricing_tab,
      "specs": self.specs_panel,
      "custom_fields": self.custom_fields_panel,
      "media": self.media_panel,
      "documents": self.document_panel,
      "source": self.product_source_tab
    }
    buttons = {
      "basic": self.basic_tab_button,
      "pricing": self.pricing_tab_button,
      "specs": self.specs_tab_button,
      "custom_fields": self.custom_fields_tab_button,
      "media": self.media_tab_button,
      "documents": self.documents_tab_button,
      "source": self.source_tab_button
    }
    for code, panel in panels.items():
      available = (
        code in ("basic", "pricing", "source")
        or (code == "custom_fields" and bool(self._custom_fields))
        or (code in ("specs", "media", "documents") and self.product_id is not None)
      )
      panel.visible = available and code == tab_code
      buttons[code].role = (
        "product-editor-tab-active" if code == tab_code else "product-editor-tab"
      )
    self.product_tab_heading.text = labels.get(tab_code, labels["basic"])

  @handle("basic_tab_button", "click")
  def basic_tab_button_click(self, **event_args):
    self._show_product_tab("basic")

  @handle("pricing_tab_button", "click")
  def pricing_tab_button_click(self, **event_args):
    self._show_product_tab("pricing")

  @handle("specs_tab_button", "click")
  def specs_tab_button_click(self, **event_args):
    self._show_product_tab("specs")

  @handle("custom_fields_tab_button", "click")
  def custom_fields_tab_button_click(self, **event_args):
    self._show_product_tab("custom_fields")

  @handle("media_tab_button", "click")
  def media_tab_button_click(self, **event_args):
    self._show_product_tab("media")

  @handle("documents_tab_button", "click")
  def documents_tab_button_click(self, **event_args):
    self._show_product_tab("documents")

  @handle("source_tab_button", "click")
  def source_tab_button_click(self, **event_args):
    self._show_product_tab("source")

  def _set_subcategory_options(self, selected_id=None):
    root_id = self.category_dropdown.selected_value
    descendants = set([root_id]) if root_id else set()
    children = []
    changed = True
    while changed:
      changed = False
      for row in self._categories:
        if row["id"] in descendants or row.get("parent_id") not in descendants:
          continue
        descendants.add(row["id"])
        children.append(row)
        changed = True
    self.subcategory_dropdown.items = [("Без подкатегории", None)] + [
      (self._category_path(row), row["id"]) for row in children
    ]
    self.subcategory_dropdown.selected_value = selected_id

  def _category_path(self, row):
    parts = [row["title"]]
    parent_code = row["parent_code"]
    visited = {row["code"]}
    while (
      parent_code and parent_code in self._categories_by_code
      and parent_code not in visited
    ):
      visited.add(parent_code)
      parent = self._categories_by_code[parent_code]
      parts.insert(0, parent["title"])
      parent_code = parent["parent_code"]
    return " / ".join(parts)

  def _is_within_category(self, candidate_id, ancestor_id):
    if not candidate_id or not ancestor_id:
      return False
    current = next((row for row in self._categories if row["id"] == candidate_id), None)
    visited = set()
    while current:
      if current["id"] == ancestor_id:
        return True
      parent_id = current.get("parent_id")
      if not parent_id or parent_id in visited:
        return False
      visited.add(parent_id)
      current = next((row for row in self._categories if row["id"] == parent_id), None)
    return False

  def _set_series_options(self, selected_id=None):
    parent_id = self.subcategory_dropdown.selected_value or self.category_dropdown.selected_value
    options = [("Без серии", None)]
    for row in self._series:
      if parent_id and not self._is_within_category(row.get("category_id"), parent_id):
        continue
      label = row["title"]
      if row.get("category_title"):
        label = "{} · {}".format(label, row["category_title"])
      options.append((label, row["id"]))
    self.series_dropdown.items = options
    self.series_dropdown.selected_value = selected_id

  def _fill_form(self, data):
    self.brand_box.text = data["brand_name"] or ""
    self.model_box.text = data["model"] or ""
    self.sku_box.text = data["sku"] or ""
    self.type_box.text = data["type"] or ""
    self.description_box.text = data["description"] or ""
    self.active_checkbox.checked = data.get("active", True)
    self.image_url_box.text = data.get("image_url", "") or ""
    self.category_dropdown.selected_value = data["category_id"]
    self._set_subcategory_options(data["subcategory_id"])
    self._set_series_options(data.get("series_id"))
    self.purchase_price_box.text = self._to_text(data["purchase_price"])
    self.sale_price_box.text = self._to_text(data["sale_price"])
    self.special_price_box.text = self._to_text(data["special_price"])
    self.discount_box.text = self._to_text(data["discount"])
    self.markup_box.text = self._to_text(data["markup"])
    self.installation_price_box.text = self._to_text(data["installation_price"])
    self.quantity_box.text = self._to_text(data["quantity"])
    self.minimum_stock_box.text = self._to_text(data["minimum_stock"])
    self.source_url_box.text = data["source_url"] or ""
    self.source_publisher_box.text = data["source_publisher"] or ""
    self.source_version_box.text = data["source_version"] or ""

  def _to_text(self, value):
    return "" if value is None else str(value)

  def _reload_specs(self):
    result = anvil.server.call("get_product_editor_data", self.product_id)
    if result["ok"]:
      self.spec_rows.items = result["specs"]

  def _reload_custom_fields(self):
    result = anvil.server.call(
      "get_product_custom_fields", self.product_id,
      self.category_dropdown.selected_value or "",
      self.subcategory_dropdown.selected_value or ""
    )
    if result["ok"]:
      self._custom_fields = result["fields"]
      self.custom_field_rows.items = self._custom_fields
      self.custom_fields_tab_button.visible = bool(self._custom_fields)
      if not self._custom_fields and self.product_tab_heading.text == "Дополнительные поля категории":
        self._show_product_tab("basic")

  @handle("custom_field_rows", "x-custom-field-saved")
  def custom_field_rows_saved(self, **event_args):
    self._reload_custom_fields()
    self.product_status.text = "Дополнительное поле сохранено."

  @handle("category_dropdown", "change")
  def category_dropdown_change(self, **event_args):
    self._set_subcategory_options()
    self._set_series_options()
    self._reload_custom_fields()

  @handle("subcategory_dropdown", "change")
  def subcategory_dropdown_change(self, **event_args):
    self._set_series_options()
    self._reload_custom_fields()

  @handle("save_product_button", "click")
  def save_product_button_click(self, **event_args):
    product_data = {
      "brand_name": self.brand_box.text or "",
      "model": self.model_box.text or "",
      "sku": self.sku_box.text or "",
      "category_id": self.category_dropdown.selected_value,
      "subcategory_id": self.subcategory_dropdown.selected_value,
      "series_id": self.series_dropdown.selected_value,
      "type": self.type_box.text or "",
      "description": self.description_box.text or "",
      "active": self.active_checkbox.checked
    }
    prices = {
      "purchase_price": self.purchase_price_box.text or "",
      "sale_price": self.sale_price_box.text or "",
      "special_price": self.special_price_box.text or "",
      "discount": self.discount_box.text or "",
      "markup": self.markup_box.text or "",
      "installation_price": self.installation_price_box.text or ""
    }
    stock = {
      "quantity": self.quantity_box.text or "",
      "minimum_stock": self.minimum_stock_box.text or ""
    }
    source_data = {
      "url": self.source_url_box.text or "",
      "publisher": self.source_publisher_box.text or "",
      "version": self.source_version_box.text or ""
    }
    result = anvil.server.call(
      "save_product", product_data, prices, stock, source_data, self.product_id,
      self.image_url_box.text or ""
    )
    self.product_status.text = result["message"]
    if result["ok"]:
      self.product_id = result["product_id"]
      self.specs_tab_button.visible = True
      self.media_tab_button.visible = True
      self.documents_tab_button.visible = True
      self.duplicate_button.visible = True
      self.delete_button.visible = True
      self._reload_custom_fields()
      self._show_product_tab("basic")
      self._reload_specs()
      self._reload_media()
      self._reload_documents()

  @handle("duplicate_button", "click")
  def duplicate_button_click(self, **event_args):
    result = anvil.server.call("duplicate_product", self.product_id)
    self.product_status.text = result["message"]
    if result["ok"]:
      Access.open_context_window("Catalog.ProductEditor", product_id=result["product_id"])

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    if not confirm(
      "Удалить товар и данные его карточки? Связанные с заказами, проектами или расчётами товары удалить нельзя.",
      title="Удалить товар"
    ):
      return
    result = anvil.server.call("delete_product", self.product_id)
    self.product_status.text = result["message"]
    if result["ok"]:
      self.product_form.visible = False
      self.specs_tab_button.visible = False
      self.media_tab_button.visible = False
      self.documents_tab_button.visible = False
      self.duplicate_button.visible = False
      self.delete_button.visible = False

  def _reload_media(self):
    result = anvil.server.call("get_product_editor_data", self.product_id)
    if result["ok"]:
      self.media_rows.items = result.get("media", [])

  def _reload_documents(self):
    result = anvil.server.call("get_catalog_documents", "product", self.product_id)
    if result["ok"]:
      self.document_rows.items = [dict(row, can_delete=True) for row in result["documents"]]

  @handle("add_document_button", "click")
  def add_document_button_click(self, **event_args):
    if not self.product_id:
      self.document_message.text = "Сначала сохраните товар."
      return
    result = anvil.server.call(
      "save_catalog_document", "product", self.product_id,
      self.document_title_box.text or "", self.document_kind_dropdown.selected_value or "other",
      (self.document_file.files or [None])[0], self.document_url_box.text or "",
      self.document_order_box.text or "0"
    )
    self.document_message.text = result["message"]
    if result["ok"]:
      self.document_title_box.text = ""
      self.document_file.files = []
      self.document_url_box.text = ""
      self._reload_documents()

  @handle("document_rows", "x-document-deleted")
  def document_rows_document_deleted(self, **event_args):
    self._reload_documents()

  @handle("upload_images_button", "click")
  def upload_images_button_click(self, **event_args):
    files = self.image_files.files
    if not files:
      self.media_status.text = "Выберите изображения в формате JPEG, PNG, WebP или GIF."
      return
    self.upload_images_button.enabled = False
    try:
      result = anvil.server.call(
        "upload_product_images", self.product_id, files
      )
    finally:
      self.upload_images_button.enabled = True
    self.media_status.text = result["message"]
    if result["ok"]:
      self.image_files.files = []
      self.media_rows.items = result["images"]

  @handle("media_rows", "x-product-image-primary")
  def media_rows_set_primary(self, media_id, **event_args):
    result = anvil.server.call("set_product_image_primary", media_id)
    self.media_status.text = result["message"]
    if result["ok"]:
      self.media_rows.items = result["images"]

  @handle("media_rows", "x-product-image-delete")
  def media_rows_delete(self, media_id, **event_args):
    if not confirm("Удалить это изображение из карточки товара?", title="Удалить изображение"):
      return
    result = anvil.server.call("delete_product_image", media_id)
    self.media_status.text = result["message"]
    if result["ok"]:
      self.media_rows.items = result["images"]

  @handle("add_spec_button", "click")
  def add_spec_button_click(self, **event_args):
    result = anvil.server.call(
      "save_product_spec",
      self.product_id,
      self.spec_key_box.text or "",
      self.spec_value_box.text or "",
      self.spec_unit_box.text or "",
      self.spec_source_box.text or ""
    )
    self.spec_message.text = result["message"]
    if result["ok"]:
      self.spec_key_box.text = ""
      self.spec_value_box.text = ""
      self.spec_unit_box.text = ""
      self.spec_source_box.text = ""
      self._reload_specs()

  @handle("spec_rows", "x-specs-changed")
  def spec_rows_specs_changed(self, **event_args):
    self._reload_specs()

  @handle("back_button", "click")
  def back_button_click(self, **event_args):
    Access.open_context_window("Catalog")
