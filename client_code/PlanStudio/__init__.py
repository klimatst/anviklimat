from ._anvil_designer import PlanStudioTemplate
from anvil import handle
from .. import Access


class PlanStudio(PlanStudioTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("back_button", "click")
  def back_button_click(self, **event_args):
    Access.open_window("Projects")
