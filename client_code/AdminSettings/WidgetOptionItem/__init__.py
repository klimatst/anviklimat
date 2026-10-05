from ._anvil_designer import WidgetOptionItemTemplate
from anvil import handle


class WidgetOptionItem(WidgetOptionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.widget_size.items = [
      ("Компактный", "small"), ("Обычный", "normal"), ("Широкий", "wide")
    ]
    self.widget_size.selected_value = self.item.get("size", "normal")

  @handle("widget_open_button", "click")
  def widget_open_button_click(self, **event_args):
    self.parent.raise_event("x-open-widget", widget=dict(self.item))
