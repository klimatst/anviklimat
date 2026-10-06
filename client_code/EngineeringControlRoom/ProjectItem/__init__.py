from ._anvil_designer import ProjectItemTemplate
from anvil import handle
from .. import Access

class ProjectItem(ProjectItemTemplate):
  def __init__(self, item=None, **properties):
    super().__init__(**properties)
    self.item = item or {}
    self.title_label.text = self.item.get("title") or self.item.get("code") or "Проект"
    self.meta_label.text = "{} · {}".format(
      self.item.get("code", "—"), self.item.get("status", "draft")
    )

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    if self.item.get("id"):
      Access.open_admin_window("Projects", window_title="Проекты и системы")
