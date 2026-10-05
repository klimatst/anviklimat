from ._anvil_designer import MediaTemplate
from anvil import handle
import anvil.server
from ... import Access


class Media(MediaTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.media_message.text = ""
    if not Access.require_permission_form("catalog.manage"):
      self.media_panel.visible = False
      return
    self._load_products()

  def _load_products(self):
    result = anvil.server.call(
      "get_catalog_products_missing_images", self.search_box.text or "", 500
    )
    if not result["ok"]:
      self.missing_product_rows.items = []
      self.media_message.text = result["message"]
      return
    self.missing_product_rows.items = result["rows"]
    self.media_message.text = result["message"]

  @handle("search_button", "click")
  def search_button_click(self, **event_args):
    self._load_products()

  @handle("refresh_button", "click")
  def refresh_button_click(self, **event_args):
    self._load_products()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
