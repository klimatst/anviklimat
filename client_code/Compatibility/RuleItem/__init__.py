from ._anvil_designer import RuleItemTemplate
import anvil.server
from anvil import handle


class RuleItem(RuleItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event(
      "x-compatibility-edit", record_id=self.item["id"]
    )
