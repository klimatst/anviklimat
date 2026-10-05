from ._anvil_designer import FormulaItemTemplate
import anvil.server
from anvil import handle


class FormulaItem(FormulaItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-formula-edit", code=self.item["code"])
