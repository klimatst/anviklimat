from ._anvil_designer import ArticleSectionItemTemplate
import anvil.server


class ArticleSectionItem(ArticleSectionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.section_title.text = self.item.get("title", "")
    self.section_title.visible = bool(self.item.get("title"))
    text = self.item.get("text", "")
    self.section_text.text = text
    self.section_text.visible = bool(text) and not bool(self.item.get("html"))
    html_content = self.item.get("html", "")
    self.section_html.visible = bool(html_content)
    self.section_html.format = "html"
    self.section_html.content = html_content
    image_url = self.item.get("image_url", "")
    self.section_image.visible = bool(image_url)
    self.section_image.source = image_url
    self.section_image.alt_text = self.item.get("image_alt", "Иллюстрация к материалу")
