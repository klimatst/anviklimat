from ._anvil_designer import PreviewItemTemplate
import anvil.server


class PreviewItem(PreviewItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.preview_block_title.text = self.item.get("title", "")
    html_content = self.item.get("html", "")
    self.preview_block_html.visible = bool(html_content)
    self.preview_block_html.format = "html"
    self.preview_block_html.content = html_content
    self.preview_block_body.visible = not bool(html_content)
    self.preview_block_body.text = self.item.get("body", "")
