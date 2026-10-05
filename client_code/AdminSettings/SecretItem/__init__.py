from ._anvil_designer import SecretItemTemplate
from anvil import handle


class SecretItem(SecretItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.secret_status.text = self.item.get("display", "Значение скрыто")

  @handle("edit_secret_button", "click")
  def edit_secret_button_click(self, **event_args):
    self.parent.raise_event("x-edit-secret", secret=dict(self.item))

  @handle("clear_secret_button", "click")
  def clear_secret_button_click(self, **event_args):
    self.parent.raise_event("x-clear-secret", secret_name=self.item["name"])
