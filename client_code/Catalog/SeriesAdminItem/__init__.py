from ._anvil_designer import SeriesAdminItemTemplate
from anvil import handle


class SeriesAdminItem(SeriesAdminItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-edit-series", series_id=self.item["id"])
