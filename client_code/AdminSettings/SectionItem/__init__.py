from ._anvil_designer import SectionItemTemplate
from anvil import handle


class SectionItem(SectionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.section_status.text = "Включён" if self.item.get("enabled", True) else "Выключен"
    self.select_button.role = (
      "settings-section-link-active" if self.item.get("selected") else
      "settings-section-link"
    )

  @handle("select_button", "click")
  def select_button_click(self, **event_args):
    self.parent.raise_event("x-select-settings-section", section_id=self.item["id"])
