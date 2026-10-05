from ._anvil_designer import InputItemTemplate
import anvil.server


class InputItem(InputItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
