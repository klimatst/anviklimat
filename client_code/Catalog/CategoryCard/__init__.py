from ._anvil_designer import CategoryCardTemplate
from anvil import handle


class CategoryCard(CategoryCardTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    is_direction = self.item.get("card_type") == "direction"
    if is_direction:
      self.role = "catalog-direction-card"
      self.category_kicker.text = "НАПРАВЛЕНИЕ"
      self.category_action_button.text = "Смотреть оборудование"
    else:
      self.category_kicker.text = "РАЗДЕЛ КАТАЛОГА"
      self.category_action_button.text = "Открыть раздел"
    self.category_description.text = self.item.get("card_description") or ""
    image_url = self.item.get("image_url") or ""
    self.category_image.source = image_url
    self.category_image.visible = bool(image_url)
    self.image_placeholder.visible = not bool(image_url)
    self.image_placeholder.text = self.item.get("title") or "Категория оборудования"

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    self.parent.raise_event("x-category-selected", category_code=self.item["code"])

  @handle("category_action_button", "click")
  def category_action_button_click(self, **event_args):
    self.parent.raise_event("x-category-selected", category_code=self.item["code"])
