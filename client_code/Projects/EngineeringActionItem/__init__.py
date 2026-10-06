from ._anvil_designer import EngineeringActionItemTemplate


class EngineeringActionItem(EngineeringActionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
