from ._anvil_designer import ChildItemTemplate


class ChildItem(ChildItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.child_menu_link.text = self.item["title"]
    self.child_menu_link.url = self.item["url"]
