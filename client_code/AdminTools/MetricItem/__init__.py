from ._anvil_designer import MetricItemTemplate
from anvil import handle


class MetricItem(MetricItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("open_metric_button", "click")
  def open_metric_button_click(self, **event_args):
    self.parent.raise_event("x-open-metric", metric=dict(self.item))
