from ._anvil_designer import ProductItemTemplate
import anvil.server
from ... import Access
from anvil import handle


class ProductItem(ProductItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    Access.open_context_window("Catalog.ProductEditor", product_id=self.item["id"])

  @handle("details_button", "click")
  def details_button_click(self, **event_args):
    self.parent.raise_event(
      "x-product-details", product_id=self.item["id"]
    )

  @handle("order_button", "click")
  def order_button_click(self, **event_args):
    self.parent.raise_event("x-product-order", product_id=self.item["id"])

  @handle("select_checkbox", "change")
  def select_checkbox_change(self, **event_args):
    self.parent.raise_event(
      "x-product-selection",
      product_id=self.item["id"],
      selected=self.select_checkbox.checked
    )
