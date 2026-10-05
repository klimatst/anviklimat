from ._anvil_designer import SiteMenuItemTemplate
from anvil import handle


class SiteMenuItem(SiteMenuItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.site_menu_link.text = self.item["title"]
    self.site_menu_link.url = self.item["url"]
    self.site_menu_image.source = self.item.get("image_url") or ""
    self.site_menu_image.visible = bool(self.item.get("image_url"))
    children = self.item.get("children", [])
    self.site_menu_children.items = children
    self.site_menu_children.visible = bool(children)
    self.expand_children_button.visible = bool(children)

  @handle("expand_children_button", "click")
  def expand_children_button_click(self, **event_args):
    self.site_menu_children.visible = not self.site_menu_children.visible

