from ._anvil_designer import MediaItemTemplate
from anvil import handle


class MediaItem(MediaItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.image_label.text = self.item.get("alt_text") or "Изображение модели"
    self.primary_badge.visible = bool(self.item.get("is_primary"))
    self.primary_button.visible = not bool(self.item.get("is_primary"))

  @handle("primary_button", "click")
  def primary_button_click(self, **event_args):
    self.parent.raise_event(
      "x-product-image-primary", media_id=self.item["id"]
    )

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    self.parent.raise_event(
      "x-product-image-delete", media_id=self.item["id"]
    )
