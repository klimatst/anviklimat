from ._anvil_designer import ToolOptionItemTemplate
from anvil import handle


class ToolOptionItem(ToolOptionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    self.parent.raise_event(
      "x-open-tool", option_index=self.item["option_index"]
    )
