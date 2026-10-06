from ._anvil_designer import PricePageTemplate
from .. import Access
from anvil import handle
import anvil.server
from anvil.js.window import document


PRICE_CODES = ("conditioners", "vrf", "ventilation")


class PricePage(PricePageTemplate):
  def __init__(self, page_code="ventilation", **properties):
    super().__init__(**properties)
    self._page_code = page_code if page_code in PRICE_CODES else "ventilation"
    self._load_page()

  def _load_page(self):
    self.price_status.text = "Загрузка страницы цен…"
    self.price_status.visible = True
    try:
      result = anvil.server.call("get_price_page", self._page_code)
    except Exception as exc:
      self.price_status.text = "Не удалось загрузить страницу цен: {}".format(exc)
      self.price_html.html = "<p>Повторите открытие страницы через несколько секунд.</p>"
      return
    if not result["ok"]:
      self.price_status.text = result["message"]
      self.price_html.html = ""
      return
    self.page_title.text = result["title"]
    self.price_html.html = result["html"]
    self.price_status.visible = False
    document.title = "{} | ЭКО-КЛИМАТ".format(result["title"])

  @handle("prices_conditioners_button", "click")
  def prices_conditioners_button_click(self, **event_args):
    Access.open_window("PricePage", page_code="conditioners")

  @handle("prices_vrf_button", "click")
  def prices_vrf_button_click(self, **event_args):
    Access.open_window("PricePage", page_code="vrf")

  @handle("prices_ventilation_button", "click")
  def prices_ventilation_button_click(self, **event_args):
    Access.open_window("PricePage", page_code="ventilation")

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Form1")
