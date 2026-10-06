from ._anvil_designer import VentilationRateItemTemplate


class VentilationRateItem(VentilationRateItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.rate_label.text = self.item.get("label", "")
    self.rate_unit.text = self.item.get("unit", "₽")
