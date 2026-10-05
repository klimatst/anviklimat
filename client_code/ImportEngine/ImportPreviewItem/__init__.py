from ._anvil_designer import ImportPreviewItemTemplate


class ImportPreviewItem(ImportPreviewItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.line_label.text = "Строка {}".format(self.item.get("line", ""))
    self.product_label.text = "{} {}".format(
      self.item.get("brand", ""), self.item.get("model", "")
    ).strip() or "Модель не распознана"
    self.product_meta.text = " · ".join(
      value for value in (
        "Артикул: " + self.item["sku"] if self.item.get("sku") else "",
        "Категория: " + self.item["category"] if self.item.get("category") else "",
        "Цена: " + self.item["sale_price"] if self.item.get("sale_price") else ""
      ) if value
    )
    self.status_label.text = "{} · {}".format(
      self.item.get("status", ""), self.item.get("message", "")
    )
