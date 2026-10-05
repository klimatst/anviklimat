from ._anvil_designer import GalleryThumbTemplate
from anvil import handle


class GalleryThumb(GalleryThumbTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.select_button.text = "Главное фото" if self.item.get("is_primary") else "Открыть"

  @handle("select_button", "click")
  def select_button_click(self, **event_args):
    self.parent.raise_event(
      "x-gallery-select", image_url=self.item.get("url") or "",
      alt_text=self.item.get("alt_text") or "Фото модели"
    )
