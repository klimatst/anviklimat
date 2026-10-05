from ._anvil_designer import BomItemTemplate
import anvil.server


class BomItem(BomItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
