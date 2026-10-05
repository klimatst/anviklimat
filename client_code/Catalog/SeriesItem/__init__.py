from ._anvil_designer import SeriesItemTemplate
from anvil import handle


class SeriesItem(SeriesItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.series_title.text = self.item.get("title") or "Модели категории"
    self.series_description.text = self.item.get("description") or ""
    self.series_description.visible = bool(self.series_description.text)
    self.power_range.text = self.item.get("power_range") or ""
    self.power_range.visible = bool(self.power_range.text)
    self.new_badge.visible = bool(self.item.get("is_new"))
    image_url = self.item.get("image_url") or ""
    self.series_image.source = image_url
    self.series_image.visible = bool(image_url)
    self.series_image_placeholder.visible = not bool(image_url)
    self.series_count.text = "Моделей на странице: {}".format(
      len(self.item.get("models", []))
    )
    self.document_rows.items = self.item.get("documents", [])
    self.documents_panel.visible = bool(self.item.get("documents"))
    self.column_headings.items = self.item.get("columns", [])
    self.model_rows.items = self.item.get("models", [])
    self.models_panel.visible = bool(self.item.get("expanded"))
    self.toggle_models_button.visible = bool(self.item.get("models"))
    self.toggle_models_button.text = (
      "Свернуть модели" if self.models_panel.visible else "Показать модели"
    )

  @handle("toggle_models_button", "click")
  def toggle_models_button_click(self, **event_args):
    self.models_panel.visible = not self.models_panel.visible
    self.toggle_models_button.text = (
      "Свернуть модели" if self.models_panel.visible else "Показать модели"
    )

  @handle("model_rows", "x-product-details")
  def model_rows_product_details(self, product_id, **event_args):
    self.parent.raise_event("x-product-details", product_id=product_id)

  @handle("model_rows", "x-product-order")
  def model_rows_product_order(self, product_id, **event_args):
    self.parent.raise_event("x-product-order", product_id=product_id)

  @handle("model_rows", "x-product-selection")
  def model_rows_product_selection(self, product_id, selected, **event_args):
    self.parent.raise_event(
      "x-product-selection", product_id=product_id, selected=selected
    )

  @handle("model_rows", "x-product-refresh")
  def model_rows_product_refresh(self, **event_args):
    self.parent.raise_event("x-product-refresh")
