from ._anvil_designer import MenuItemTemplate
from anvil import handle


class MenuItem(MenuItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.select_menu_button.text = self.item.get("display_title", self.item["title"])
    parent = self.item.get("parent_title")
    state = "Включён" if self.item.get("enabled") else "Скрыт"
    self.menu_item_info.text = "{} · порядок {} · {}".format(
      parent or "Верхний уровень", self.item.get("sort_order", 0), state
    )

  @handle("select_menu_button", "click")
  def select_menu_button_click(self, **event_args):
    self.parent.raise_event("x-select-menu-item", item_id=self.item["id"])

  @handle("move_up_button", "click")
  def move_up_button_click(self, **event_args):
    self.parent.raise_event(
      "x-move-menu-item", item_id=self.item["id"], direction="up"
    )

  @handle("move_down_button", "click")
  def move_down_button_click(self, **event_args):
    self.parent.raise_event(
      "x-move-menu-item", item_id=self.item["id"], direction="down"
    )
