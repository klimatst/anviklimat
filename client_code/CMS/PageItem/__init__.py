from ._anvil_designer import PageItemTemplate
import anvil.server
from anvil import handle


class PageItem(PageItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-page-edit", page_id=self.item["id"])
