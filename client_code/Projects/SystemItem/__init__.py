from ._anvil_designer import SystemItemTemplate
import anvil.server
from ... import Access
from anvil import handle


class SystemItem(SystemItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    Access.open_window("Constructor", system_id=self.item["id"])

  @handle("calculations_button", "click")
  def calculations_button_click(self, **event_args):
    Access.open_window(
      "Calculations", project_id=self.item["project_id"],
      system_id=self.item["id"]
    )
