from ._anvil_designer import MetricItemTemplate


class MetricItem(MetricItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.metric_label.text = str(self.item.get("label", ""))
    self.metric_value.text = str(self.item.get("value", "—"))
