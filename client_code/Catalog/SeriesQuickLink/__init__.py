from ._anvil_designer import SeriesQuickLinkTemplate
from anvil import handle


class SeriesQuickLink(SeriesQuickLinkTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.open_button.text = self.item.get("title") or "Серия"
    self.open_button.role = (
      "catalog-series-link-active"
      if self.item.get("selected") else "catalog-series-link"
    )

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    self.parent.raise_event(
      "x-series-selected", series_id=self.item.get("series_id"),
      group_key=self.item.get("group_key")
    )
