from ._anvil_designer import NodeItemTemplate
import anvil.server
from anvil import handle


class NodeItem(NodeItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("select_button", "click")
  def select_button_click(self, **event_args):
    self.parent.raise_event("x-node-select", node_id=self.item["id"])

  @handle("select_checkbox", "change")
  def select_checkbox_change(self, **event_args):
    self.parent.raise_event(
      "x-node-toggle", node_id=self.item["id"],
      selected=self.select_checkbox.checked
    )
