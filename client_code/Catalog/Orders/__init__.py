from ._anvil_designer import OrdersTemplate
from anvil import handle
import anvil.server
from ... import Access


class Orders(OrdersTemplate):
  def __init__(self, search_query="", **properties):
    super().__init__(**properties)
    self.order_message.text = ""
    if not Access.require_permission_form("catalog.manage"):
      self.orders_panel.visible = False
      return
    self.status_filter.items = [
      ("Все статусы", "all"), ("Новые", "new"),
      ("В обработке", "processing"), ("Завершённые", "completed"),
      ("Отменённые", "cancelled")
    ]
    self.status_filter.selected_value = "all"
    self.search_box.text = search_query or ""
    self._load_orders()

  def _load_orders(self):
    result = anvil.server.call(
      "get_catalog_orders", self.search_box.text or "",
      self.status_filter.selected_value or "all", 200
    )
    if not result["ok"]:
      self.order_rows.items = []
      self.order_message.text = result["message"]
      return
    self.order_rows.items = result["rows"]
    self.order_message.text = result["message"]

  @handle("search_button", "click")
  def search_button_click(self, **event_args):
    self._load_orders()

  @handle("status_filter", "change")
  def status_filter_change(self, **event_args):
    self._load_orders()

  @handle("refresh_button", "click")
  def refresh_button_click(self, **event_args):
    self._load_orders()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()

  @handle("order_rows", "x-order-status-change")
  def order_rows_status_change(self, order_id, status, **event_args):
    result = anvil.server.call("update_catalog_order_status", order_id, status)
    self.order_message.text = result["message"]
    if result["ok"]:
      self._load_orders()
