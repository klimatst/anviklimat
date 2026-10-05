from ._anvil_designer import ImageItemTemplate


class ImageItem(ImageItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    item = self.item
    url = item.get("url", "") if isinstance(item, dict) else item
    alt = item.get("alt", "Изображение системы вентиляции") if isinstance(item, dict) else "Изображение системы вентиляции"
    self.page_image.source = url or ""
    self.page_image.alt_text = alt
    self.image_caption.text = str(item.get("caption", "")) if isinstance(item, dict) else ""
    self.image_caption.visible = bool(self.image_caption.text)
