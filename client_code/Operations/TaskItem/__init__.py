from ._anvil_designer import TaskItemTemplate
import anvil.server
from anvil import handle


class TaskItem(TaskItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("complete_button", "click")
  def complete_button_click(self, **event_args):
    self.parent.raise_event("x-task-complete", task_id=self.item["id"])
