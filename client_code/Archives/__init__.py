from ._anvil_designer import ArchivesTemplate
from anvil import handle
from .. import Access


class Archives(ArchivesTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Form1")
