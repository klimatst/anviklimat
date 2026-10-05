from ._anvil_designer import ImportItemTemplate
import anvil.server
from anvil import handle


STATUS_LABELS = {
  "draft": "Черновик",
  "running": "Выполняется",
  "paused": "Приостановлен",
  "completed": "Завершён",
  "failed": "Ошибка",
  "source_changed": "Источник изменился"
}


class ImportItem(ImportItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    status = self.item["status"]
    self.progress_label.text = "{} из {}; обновлено {}; пропущено {}".format(
      self.item["processed"], self.item["total"],
      self.item["imported"], self.item["skipped"]
    )
    self.status_label.text = STATUS_LABELS.get(status, "Неизвестный статус")
    self.resume_button.visible = status not in ("completed", "source_changed")

  @handle("resume_button", "click")
  def resume_button_click(self, **event_args):
    self.parent.raise_event("x-import-resume", import_id=self.item["id"])
