from ._anvil_designer import CategoryItemTemplate
import anvil.server
from anvil import handle


class CategoryItem(CategoryItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._expanded = False
    self._menu_mode = self.item.get("menu_mode", False)
    self.open_category_button.text = self.item.get("menu_label") or self.item.get("title", "Категория")
    if not self._menu_mode and self.item.get("selected"):
      self.open_category_button.role = "catalog-tree-link-active"
    image_url = self.item.get("image_url") or ""
    self.category_image.source = image_url
    self.category_image.visible = bool(image_url)
    count = self.item.get("product_count")
    self.category_count.text = str(count) if count else ""
    self.category_count.visible = bool(count)
    if self._menu_mode:
      self.role = "navigation-tree-node"
      self.open_category_button.role = "navigation-tree-link"
      self.expand_button.role = "navigation-tree-expand"
      self.category_children.role = "navigation-tree-flyout"
    # RepeatingPanel data can arrive from cached/legacy catalog payloads.
    # Treat the menu-node contract as optional at the UI boundary so one
    # malformed/older node cannot crash the whole Anvil layout.
    children = self.item.get("children") or []
    has_children = bool(self.item.get("has_children", children))
    expand_icon = self.item.get("expand_icon") or ("›" if has_children else "")
    self.category_children.items = children
    self.expand_button.visible = has_children
    self.expand_button.text = expand_icon

  @handle("open_category_button", "click")
  def open_category_button_click(self, **event_args):
    self.parent.raise_event(
      "x-category-selected", category_id=self.item["id"],
      category_code=self.item.get("code")
    )

  @handle("expand_button", "click")
  def expand_button_click(self, **event_args):
    self._expanded = not self._expanded
    if self._menu_mode:
      self.category_children.role = (
        "navigation-tree-flyout-open" if self._expanded else "navigation-tree-flyout"
      )
    else:
      self.category_children.role = (
        "catalog-tree-flyout-open" if self._expanded else "catalog-tree-flyout"
      )
    self.expand_button.text = "⌄" if self._expanded else "›"

  @handle("category_children", "x-category-selected")
  def category_children_category_selected(self, category_id=None, category_code=None, **event_args):
    # Relay selections up through each nested RepeatingPanel until the
    # catalogue form receives the event.
    self.parent.raise_event(
      "x-category-selected", category_id=category_id,
      category_code=category_code
    )
