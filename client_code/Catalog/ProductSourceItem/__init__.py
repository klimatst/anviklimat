from ._anvil_designer import ProductSourceItemTemplate
import anvil.server


class ProductSourceItem(ProductSourceItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
