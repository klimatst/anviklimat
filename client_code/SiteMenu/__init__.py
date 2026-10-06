from ._anvil_designer import SiteMenuTemplate
from anvil import confirm, handle
import anvil.server

from .. import Access


class SiteMenu(SiteMenuTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_permission_form("cms.manage"):
      return
    self._items = []
    self._editing_id = None
    self._load_menu()
    self._new_item()

  def _load_menu(self, selected_id=None):
    result = anvil.server.call("get_managed_site_menu")
    if not result["ok"]:
      self.menu_rows.items = []
      self.menu_message.text = result["message"]
      return
    self._items = result["items"]
    roots = [item for item in self._items if not item.get("parent_id")]
    self.parent_dropdown.items = [("Верхний уровень", None)] + [
      (item["title"], item["id"]) for item in roots
    ]
    self.menu_rows.items = [
      dict(item, display_title=("↳ " if item.get("parent_id") else "") + item["title"])
      for item in self._items
    ]
    self.menu_count.text = "Пунктов меню: {} · верхних разделов: {}".format(
      len(self._items), len(roots)
    )
    selected = next((item for item in self._items if item["id"] == selected_id), None)
    if selected is not None:
      self._show_item(selected)

  def _new_item(self, parent_id=None):
    self._editing_id = None
    self.menu_editor_heading.text = "Новый пункт меню"
    self.menu_title_box.text = ""
    self.menu_url_box.text = "/"
    self.menu_image_url_box.text = ""
    self.sort_order_box.text = str((len(self._items) + 1) * 10)
    self.enabled_checkbox.checked = True
    self.parent_dropdown.selected_value = parent_id
    self.delete_item_button.visible = False
    self.menu_preview_link.visible = False
    self.menu_preview_image.visible = False
    self.menu_message.text = ""

  def _show_item(self, item):
    self._editing_id = item["id"]
    self.menu_editor_heading.text = "Изменить пункт меню"
    self.menu_title_box.text = item["title"]
    self.menu_url_box.text = item["url"]
    self.menu_image_url_box.text = item.get("image_url", "")
    self.sort_order_box.text = str(item.get("sort_order", 0))
    self.enabled_checkbox.checked = bool(item.get("enabled", True))
    self.parent_dropdown.selected_value = item.get("parent_id")
    self.delete_item_button.visible = True
    self.menu_preview_link.text = "Открыть ссылку"
    self.menu_preview_link.url = item["url"]
    self.menu_preview_link.visible = bool(item["url"])
    image_url = item.get("image_url", "")
    self.menu_preview_image.source = image_url or ""
    self.menu_preview_image.visible = bool(image_url)
    self.menu_message.text = ""

  @handle("menu_rows", "x-select-menu-item")
  def menu_rows_select_item(self, item_id, **event_args):
    item = next((row for row in self._items if row["id"] == item_id), None)
    if item is not None:
      self._show_item(item)

  @handle("menu_rows", "x-move-menu-item")
  def menu_rows_move_item(self, item_id, direction, **event_args):
    current = next((item for item in self._items if item["id"] == item_id), None)
    if current is None:
      return
    siblings = sorted(
      (item for item in self._items if item.get("parent_id") == current.get("parent_id")),
      key=lambda item: (
        item.get("sort_order", 0), str(item.get("title") or "").lower()
      )
    )
    index = next((i for i, item in enumerate(siblings) if item["id"] == item_id), None)
    if index is None:
      return
    target_index = index - 1 if direction == "up" else index + 1
    if not 0 <= target_index < len(siblings):
      return
    siblings[index], siblings[target_index] = siblings[target_index], siblings[index]
    for position, item in enumerate(siblings, start=1):
      item["sort_order"] = position * 10
    self._save_items(self._items, item_id)

  def _save_items(self, items, selected_id=None):
    self.save_menu_button.enabled = False
    try:
      result = anvil.server.call("save_managed_site_menu", items)
    except Exception as exc:
      self.menu_message.text = "Не удалось сохранить меню: {}".format(exc)
      return
    finally:
      self.save_menu_button.enabled = True
    self.menu_message.text = result["message"]
    if result["ok"]:
      saved_items = result["items"]
      if selected_id is None and self._editing_id is None and saved_items:
        selected_id = saved_items[-1]["id"]
      self._load_menu(selected_id)
      self.menu_message.text = result["message"]

  @handle("new_root_button", "click")
  def new_root_button_click(self, **event_args):
    self._new_item()

  @handle("new_child_button", "click")
  def new_child_button_click(self, **event_args):
    selected = self.parent_dropdown.selected_value
    if self._editing_id:
      current = next((item for item in self._items if item["id"] == self._editing_id), None)
      if current is not None:
        selected = current.get("parent_id") or current["id"]
    if not selected:
      self.menu_message.text = "Сначала выберите верхний пункт, к которому добавить вложенную ссылку."
      return
    self._new_item(parent_id=selected)
    self.menu_message.text = "Новая вложенная ссылка появится после сохранения пункта меню."

  @handle("save_menu_button", "click")
  def save_menu_button_click(self, **event_args):
    item = {
      "id": self._editing_id,
      "title": self.menu_title_box.text or "",
      "url": self.menu_url_box.text or "",
      "image_url": self.menu_image_url_box.text or "",
      "parent_id": self.parent_dropdown.selected_value,
      "sort_order": self.sort_order_box.text or "0",
      "enabled": bool(self.enabled_checkbox.checked)
    }
    items = [dict(row) for row in self._items]
    if self._editing_id:
      for index, row in enumerate(items):
        if row["id"] == self._editing_id:
          items[index] = item
          break
    else:
      items.append(item)
    self._save_items(items, self._editing_id)

  @handle("delete_item_button", "click")
  def delete_item_button_click(self, **event_args):
    if not self._editing_id:
      return
    item_id = self._editing_id
    descendants = {item["id"] for item in self._items if item.get("parent_id") == item_id}
    count = 1 + len(descendants)
    if not confirm(
      "Удалить выбранный пункт меню{}?".format(
        " и {} вложенную ссылку".format(len(descendants)) if descendants else ""
      ), title="Удалить пункт меню"
    ):
      return
    remaining = [
      dict(item) for item in self._items
      if item["id"] != item_id and item["id"] not in descendants
    ]
    self._editing_id = None
    self._save_items(remaining)
    self.menu_message.text = "Удалено пунктов: {}.".format(count)

  @handle("cancel_edit_button", "click")
  def cancel_edit_button_click(self, **event_args):
    self._new_item()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
