from ._anvil_designer import ExtensionItemTemplate
from anvil import handle


class ExtensionItem(ExtensionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.extension_enabled.checked = bool(self.item.get("enabled"))
    self.extension_type.text = "JavaScript" if self.item.get("kind") == "javascript" else "CSS"

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-edit-extension", extension=self.item)

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    self.parent.raise_event("x-delete-extension", extension_id=self.item["id"])

  @handle("extension_enabled", "change")
  def extension_enabled_change(self, **event_args):
    self.parent.raise_event("x-extension-toggle")
