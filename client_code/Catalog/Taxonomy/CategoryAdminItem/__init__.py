from ._anvil_designer import CategoryAdminItemTemplate
import anvil.server
from anvil import handle


class CategoryAdminItem(CategoryAdminItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-edit-category", category_id=self.item["id"])
