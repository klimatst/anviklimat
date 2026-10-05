from ._anvil_designer import GalleryCardTemplate
import anvil.server
from anvil import handle


class GalleryCard(GalleryCardTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-gallery-edit-item", item_id=self.item["id"])
