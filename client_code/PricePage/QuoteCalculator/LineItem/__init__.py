from ._anvil_designer import LineItemTemplate


class LineItem(LineItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    item = self.item
    self.line_category.text = str(item.get("category", ""))
    self.line_title.text = str(item.get("title", ""))
    self.line_quantity.text = str(item.get("quantity", ""))
    self.line_unit_price.text = str(item.get("unit_price", ""))
    self.line_total.text = str(item.get("total", ""))
