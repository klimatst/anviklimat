from ._anvil_designer import BreadcrumbItemTemplate
from anvil import handle


class BreadcrumbItem(BreadcrumbItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.open_button.text = self.item.get("title") or "Каталог"
    self.open_button.enabled = not bool(self.item.get("current"))
    self.separator.visible = not bool(self.item.get("first"))

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    if not self.item.get("current"):
      self.parent.raise_event(
        "x-breadcrumb-selected", category_code=self.item.get("code")
      )
