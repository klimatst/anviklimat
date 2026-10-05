from ._anvil_designer import ArticleDetailsTemplate
import anvil.server
from anvil import handle


class ArticleDetails(ArticleDetailsTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  def load_article(self, title, date, excerpt, sections):
    self.article_title.text = title or "Материал"
    self.article_date.text = date or "Дата не указана"
    self.article_excerpt.text = excerpt or ""
    self.article_excerpt.visible = bool(excerpt)
    self.article_sections.items = sections or []

  @handle("close_button", "click")
  def close_button_click(self, **event_args):
    self.raise_event("close")
