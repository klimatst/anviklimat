from ._anvil_designer import DetailSpecItemTemplate
import anvil.server


class DetailSpecItem(DetailSpecItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
