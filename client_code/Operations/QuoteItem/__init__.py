from ._anvil_designer import QuoteItemTemplate
import anvil.server
from anvil import handle


class QuoteItem(QuoteItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("send_button", "click")
  def send_button_click(self, **event_args):
    self.parent.raise_event(
      "x-quote-status", quote_id=self.item["id"], status="sent"
    )

  @handle("approve_button", "click")
  def approve_button_click(self, **event_args):
    self.parent.raise_event(
      "x-quote-status", quote_id=self.item["id"], status="approved"
    )
