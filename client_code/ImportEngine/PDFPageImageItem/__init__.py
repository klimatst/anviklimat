from ._anvil_designer import PDFPageImageItemTemplate


class PDFPageImageItem(PDFPageImageItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    url = self.item.get("url") or ""
    self.preview_image.source = url if url else ""
    self.preview_image.visible = bool(url)
    self.image_details.text = "{} · {} байт".format(
      self.item.get("name") or "Изображение PDF",
      self.item.get("size") or 0
    )
