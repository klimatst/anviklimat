from ._anvil_designer import ColumnHeadingItemTemplate


class ColumnHeadingItem(ColumnHeadingItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
