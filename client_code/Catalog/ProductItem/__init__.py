from ._anvil_designer import ProductItemTemplate
from anvil import handle
import anvil.server


class ProductItem(ProductItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.role = "catalog-product-card"
    self.details_button.text = self.item.get("model") or "Модель"
    image_url = self.item.get("image_url") or ""
    self.product_image.source = image_url
    self.product_image.visible = bool(image_url)
    self.product_image.alt_text = self.item.get("image_alt") or self.details_button.text
    self.image_placeholder.visible = not bool(image_url)

    self.price_label.text = self.item.get("price_label") or "Цена по запросу"
    self.sku_label.text = self.item.get("sku") or "—"
    self.compressor_label.text = self.item.get("compressor") or "—"
    self.mode_label.text = self.item.get("operation_mode") or "—"
    self.cooling_label.text = self.item.get("cooling_capacity") or "—"
    self.heating_label.text = self.item.get("heating_capacity") or "—"

    self.new_badge.visible = bool(self.item.get("series_is_new"))
    self.hit_badge.visible = bool(self.item.get("is_hit") or self.item.get("popular"))
    discount_value = self.item.get("discount")
    special_price = self.item.get("special_price")
    self.discount_badge.visible = bool(discount_value) or special_price not in (None, "", 0, "0")

    can_edit = bool(self.item.get("can_edit"))
    self.select_checkbox.visible = can_edit
    self.select_checkbox.checked = bool(self.item.get("selected"))
    self.select_checkbox.enabled = bool(self.item.get("can_select"))
    self.edit_button.visible = can_edit
    self.quick_panel.visible = False
    self.price_box.text = (
      "" if self.item.get("price_value") is None else str(self.item["price_value"])
    )
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

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.quick_panel.visible = not self.quick_panel.visible
    self.edit_button.text = "Закрыть" if self.quick_panel.visible else "Изменить"

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
    except Exception as exc:
      self.quick_message.text = "Ошибка сохранения: {}".format(exc)
      return
    finally:
      self.quick_save_button.enabled = True
    self.quick_message.text = result.get("message", "")
    if result.get("ok"):
      self.parent.raise_event("x-product-refresh")
