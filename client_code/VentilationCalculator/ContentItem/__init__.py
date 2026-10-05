from ._anvil_designer import ContentItemTemplate


class ContentItem(ContentItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    item = self.item
    self.content_index.text = str(item.get("index", ""))
    self.content_title.text = str(item.get("title", ""))
    self.content_text.text = str(item.get("text", ""))
