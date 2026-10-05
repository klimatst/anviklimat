from ._anvil_designer import GalleryTemplate
from anvil import confirm, handle
import anvil.server


class Gallery(GalleryTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._item_id = None
    self._public_page = anvil.server.call("get_public_gallery_page")
    self._settings = self._public_page["settings"]
    self._admin_state = anvil.server.call("get_gallery_admin_state")
    self._can_edit = self._admin_state["can_edit"]
    self.gallery_editor_console.visible = self._can_edit
    self.settings_status.text = ""
    self.item_status.text = ""
    self._load_settings_controls()
    self._clear_item_editor()
    self._load_gallery_items()

  def _load_settings_controls(self):
    settings = self._settings
    self.gallery_title_label.text = settings["gallery_title"]
    self.gallery_intro_label.text = settings["gallery_intro"]
    self.settings_title_box.text = settings["gallery_title"]
    self.settings_intro_box.text = settings["gallery_intro"]
    self.storage_provider_box.text = settings["storage_provider"]
    self.storage_base_url_box.text = settings["storage_base_url"]
    self.items_per_page_box.text = str(settings["items_per_page"])
    self.columns_dropdown.items = [("2 колонки", 2), ("3 колонки", 3), ("4 колонки", 4)]
    self.columns_dropdown.selected_value = settings["columns"]
    self.ratio_dropdown.items = [
      ("Широкий", "landscape"), ("Кинематографичный", "cinematic"), ("Квадратный", "square")
    ]
    self.ratio_dropdown.selected_value = settings["image_ratio"]
    self.show_locations_check.checked = settings["show_locations"]
    self.show_dates_check.checked = settings["show_dates"]
    self.featured_first_check.checked = settings["featured_first"]

  def _load_gallery_items(self):
    if self._can_edit:
      self._admin_state = anvil.server.call("get_gallery_admin_state")
      self._settings = self._admin_state["settings"]
      self._gallery_items = self._admin_state["items"]
    else:
      self._public_page = anvil.server.call("get_public_gallery_page")
      self._settings = self._public_page["settings"]
      self._gallery_items = self._public_page["items"]
    display_items = []
    for item in self._gallery_items:
      row = dict(item)
      row["show_location"] = self._settings["show_locations"] and bool(row["location"])
      row["show_date"] = self._settings["show_dates"] and bool(row["completed_at"])
      display_items.append(row)
    columns = self._settings["columns"]
    ratio = self._settings["image_ratio"]
    self.gallery_rows.role = [
      "gallery-grid", "gallery-grid-columns-{}".format(columns),
      "gallery-grid-ratio-{}".format(ratio)
    ]
    self.gallery_rows.items = display_items
    self.gallery_empty_label.visible = not bool(display_items)
    self.gallery_title_label.text = self._settings["gallery_title"]
    self.gallery_intro_label.text = self._settings["gallery_intro"]

  def _clear_item_editor(self):
    self._item_id = None
    self.item_title_box.text = ""
    self.item_description_box.text = ""
    self.item_image_url_box.text = ""
    self.item_thumbnail_url_box.text = ""
    self.item_alt_text_box.text = ""
    self.item_category_box.text = ""
    self.item_location_box.text = ""
    self.item_completed_box.text = ""
    self.item_sort_order_box.text = "100"
    self.item_featured_check.checked = False
    self.item_published_check.checked = False
    self.item_delete_button.visible = False
    self.item_editor_heading.text = "Новая работа"
    self.item_status.text = ""

  def _edit_item(self, item_id):
    item = next((row for row in self._gallery_items if row["id"] == item_id), None)
    if item is None:
      return
    self._item_id = item_id
    self.item_title_box.text = item["title"]
    self.item_description_box.text = item["description"]
    self.item_image_url_box.text = item["full_image_url"]
    self.item_thumbnail_url_box.text = item["image_url"] if item["image_url"] != item["full_image_url"] else ""
    self.item_alt_text_box.text = item["alt_text"]
    self.item_category_box.text = item["category"]
    self.item_location_box.text = item["location"]
    self.item_completed_box.text = item["completed_at"]
    self.item_sort_order_box.text = str(item["sort_order"])
    self.item_featured_check.checked = item["featured"]
    self.item_published_check.checked = item["published"]
    self.item_delete_button.visible = True
    self.item_editor_heading.text = "Редактирование проекта"

  def _item_values(self):
    return {
      "title": self.item_title_box.text,
      "description": self.item_description_box.text,
      "image_url": self.item_image_url_box.text,
      "thumbnail_url": self.item_thumbnail_url_box.text,
      "alt_text": self.item_alt_text_box.text,
      "category": self.item_category_box.text,
      "location": self.item_location_box.text,
      "completed_at": self.item_completed_box.text,
      "sort_order": self.item_sort_order_box.text,
      "featured": self.item_featured_check.checked,
      "published": self.item_published_check.checked
    }

  @handle("gallery_rows", "x-gallery-edit-item")
  def gallery_rows_edit_item(self, item_id, **event_args):
    self._edit_item(item_id)

  @handle("new_item_button", "click")
  def new_item_button_click(self, **event_args):
    self._clear_item_editor()

  @handle("save_settings_button", "click")
  def save_settings_button_click(self, **event_args):
    values = {
      "gallery_title": self.settings_title_box.text,
      "gallery_intro": self.settings_intro_box.text,
      "storage_provider": self.storage_provider_box.text,
      "storage_base_url": self.storage_base_url_box.text,
      "items_per_page": self.items_per_page_box.text,
      "columns": self.columns_dropdown.selected_value,
      "image_ratio": self.ratio_dropdown.selected_value,
      "show_locations": self.show_locations_check.checked,
      "show_dates": self.show_dates_check.checked,
      "featured_first": self.featured_first_check.checked
    }
    result = anvil.server.call("save_gallery_settings", values)
    self.settings_status.text = result["message"]
    if result["ok"]:
      self._settings = result["settings"]
      self._load_gallery_items()

  @handle("save_item_button", "click")
  def save_item_button_click(self, **event_args):
    result = anvil.server.call("save_gallery_item", self._item_values(), self._item_id)
    self.item_status.text = result["message"]
    if result["ok"]:
      self._item_id = result["item"]["id"]
      self._load_gallery_items()
      self.item_editor_heading.text = "Редактирование проекта"
      self.item_delete_button.visible = True

  @handle("item_delete_button", "click")
  def item_delete_button_click(self, **event_args):
    if not self._item_id or not confirm("Удалить эту карточку из галереи?", title="Удалить проект"):
      return
    result = anvil.server.call("delete_gallery_item", self._item_id)
    self.item_status.text = result["message"]
    if result["ok"]:
      self._clear_item_editor()
      self._load_gallery_items()
