from ._anvil_designer import ModuleCardTemplate
from anvil import handle


class ModuleCard(ModuleCardTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    self.parent.raise_event(
      "x-open-admin-module", module_id=self.item.get("id")
    )

  @handle("favorite_button", "click")
  def favorite_button_click(self, **event_args):
    self.parent.raise_event(
      "x-toggle-admin-favorite", module_id=self.item.get("id")
    )
