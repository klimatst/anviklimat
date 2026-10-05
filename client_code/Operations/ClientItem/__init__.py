from ._anvil_designer import ClientItemTemplate
import anvil.server
from anvil import handle


class ClientItem(ClientItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-client-edit", client_id=self.item["id"])
