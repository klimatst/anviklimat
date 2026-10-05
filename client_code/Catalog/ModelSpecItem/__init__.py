from ._anvil_designer import ModelSpecItemTemplate


class ModelSpecItem(ModelSpecItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not self.item.get("title"):
      self.role = "catalog-model-spec-cell-empty"
