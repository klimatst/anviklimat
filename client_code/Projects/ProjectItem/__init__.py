from ._anvil_designer import ProjectItemTemplate
import anvil.server
from anvil import handle


class ProjectItem(ProjectItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    self.parent.raise_event("x-project-open", project_id=self.item["id"])
