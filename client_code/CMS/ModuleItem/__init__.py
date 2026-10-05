from ._anvil_designer import ModuleItemTemplate
import anvil.server
from anvil import handle


class ModuleItem(ModuleItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-module-edit", module_id=self.item["id"])

  @handle("toggle_button", "click")
  def toggle_button_click(self, **event_args):
    self.parent.raise_event(
      "x-module-toggle", module_id=self.item["id"],
      enabled=not self.item["enabled"]
    )

  @handle("move_up_button", "click")
  def move_up_button_click(self, **event_args):
    self.parent.raise_event(
      "x-module-move", module_id=self.item["id"], direction="up"
    )

  @handle("move_down_button", "click")
  def move_down_button_click(self, **event_args):
    self.parent.raise_event(
      "x-module-move", module_id=self.item["id"], direction="down"
    )

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    self.parent.raise_event("x-module-delete", module_id=self.item["id"])
