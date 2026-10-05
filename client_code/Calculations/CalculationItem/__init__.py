from ._anvil_designer import CalculationItemTemplate
import anvil.server


class CalculationItem(CalculationItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
