from ._anvil_designer import BrandAdminItemTemplate
import anvil.server
from anvil import handle


class BrandAdminItem(BrandAdminItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-edit-brand", brand_id=self.item["id"])
