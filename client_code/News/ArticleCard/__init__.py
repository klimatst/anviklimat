from ._anvil_designer import ArticleCardTemplate
import anvil.server
from anvil import handle


class ArticleCard(ArticleCardTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("read_button", "click")
  def read_button_click(self, **event_args):
    self.parent.raise_event("x-open-article", slug=self.item["slug"])
