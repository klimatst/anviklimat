from ._anvil_designer import ModelRowTemplate
from anvil import handle
import anvil.server


class ModelRow(ModelRowTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    image_url = self.item.get("image_url") or ""
    self.model_image.source = image_url
    self.model_image.visible = bool(image_url)
    self.model_image.alt_text = self.item.get("image_alt") or self.item.get("model") or "Фото модели"
    self.model_image_placeholder.visible = not bool(image_url)
    self.brand_label.text = self.item.get("brand") or ""
    self.details_button.text = self.item.get("model") or "Модель"
    self.sku_label.text = "Артикул: {}".format(self.item.get("sku") or "—")
    self.category_label.text = self.item.get("category_path") or "Категория не указана"
    self.series_label.text = self.item.get("series_title") or "Без серии"
    self.spec_cells.items = self.item.get("spec_values", [])
    self.price_label.text = self.item.get("price_label") or "Цена по запросу"
    self.stock_label.text = self.item.get("stock_label") or "Наличие уточняйте"
    can_edit = bool(self.item.get("can_edit"))
    self.select_checkbox.visible = can_edit
    self.select_checkbox.checked = bool(self.item.get("selected"))
    self.select_checkbox.enabled = bool(self.item.get("can_select"))
    self.edit_button.visible = can_edit
    self.quick_panel.visible = False
    self.price_box.text = "" if self.item.get("price_value") is None else str(self.item["price_value"])
    self.active_checkbox.checked = bool(self.item.get("active"))
    self.quantity_box.text = (
      "" if self.item.get("stock_quantity") is None
      else str(self.item["stock_quantity"])
    )
    self.category_dropdown.items = [
      (row.get("path") or row["title"], row["id"])
      for row in self.item.get("category_options", [])
    ]
    self.category_dropdown.selected_value = self.item.get("edit_category_id")
    self.series_dropdown.items = [("Без серии", "")] + [
      (row["title"], row["id"])
      for row in self.item.get("series_options", [])
    ]
    self.series_dropdown.selected_value = self.item.get("series_id") or ""

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.quick_panel.visible = not self.quick_panel.visible
    self.edit_button.text = "Закрыть" if self.quick_panel.visible else "Изменить"

  @handle("details_button", "click")
  def details_button_click(self, **event_args):
    self.parent.raise_event("x-product-details", product_id=self.item["id"])

  @handle("order_button", "click")
  def order_button_click(self, **event_args):
    self.parent.raise_event("x-product-order", product_id=self.item["id"])

  @handle("select_checkbox", "change")
  def select_checkbox_change(self, **event_args):
    self.parent.raise_event(
      "x-product-selection", product_id=self.item["id"],
      selected=self.select_checkbox.checked
    )

  @handle("quick_save_button", "click")
  def quick_save_button_click(self, **event_args):
    self.quick_save_button.enabled = False
    try:
      result = anvil.server.call(
        "update_product_quick_fields", self.item["id"],
        self.price_box.text or "", self.active_checkbox.checked,
        self.category_dropdown.selected_value,
        self.series_dropdown.selected_value or "",
        self.quantity_box.text or ""
      )
    finally:
      self.quick_save_button.enabled = True
    self.quick_message.text = result["message"]
    if result["ok"]:
      self.parent.raise_event("x-product-refresh")
