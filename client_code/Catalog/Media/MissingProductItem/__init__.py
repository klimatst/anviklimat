from ._anvil_designer import MissingProductItemTemplate
from anvil import handle
from .... import Access


class MissingProductItem(MissingProductItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.product_heading.text = "{} {}".format(
      self.item.get("brand", ""), self.item.get("model", "")
    ).strip()
    self.sku_label.text = "Артикул: {}".format(self.item.get("sku") or "не указан")
    self.category_label.text = self.item.get("category") or "Категория не указана"

  @handle("edit_media_button", "click")
  def edit_media_button_click(self, **event_args):
    Access.open_context_window(
      "Catalog.ProductEditor", product_id=self.item["id"]
    )
