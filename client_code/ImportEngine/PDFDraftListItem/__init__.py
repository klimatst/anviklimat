from ._anvil_designer import PDFDraftListItemTemplate
import anvil.server
from anvil import handle


class PDFDraftListItem(PDFDraftListItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    is_xlsx = self.item.get("format") == "xlsx"
    file_type = "XLSX" if is_xlsx else "PDF"
    file_size = self.item.get("file_size", 0) or 0
    size_label = " · {:.1f} МБ".format(file_size / (1024.0 * 1024.0)) if file_size else ""
    status_titles = {
      "pdf_draft": "Ожидает проверки",
      "pdf_processing": "Обрабатывается",
      "pdf_paused": "Приостановлен · можно продолжить",
      "pdf_failed": "Нужен повтор",
      "pdf_approved": "Утверждён",
      "pdf_rejected": "Отклонён",
      "xlsx_draft": "Ожидает проверки",
      "xlsx_uploading": (
        "Передача приостановлена" if self.item.get("upload_paused")
        else "Файл передаётся"
      ),
      "xlsx_processing": "Обрабатывается",
      "xlsx_images_processing": "Загружаются изображения",
      "xlsx_paused": "Приостановлен · можно продолжить",
      "xlsx_failed": "Нужен повтор",
      "xlsx_approved": "Утверждён",
      "xlsx_rejected": "Отклонён"
    }
    self.status_label.text = status_titles.get(self.item["status"], "Статус не распознан")
    if is_xlsx and self.item["status"] == "xlsx_uploading":
      total_bytes = self.item.get("file_size", 0) or 0
      sent_bytes = self.item.get("processed", 0) or 0
      self.count_label.text = "Передано {}% · {:.1f}/{:.1f} МБ".format(
        self.item.get("progress_percent", 0), sent_bytes / (1024.0 * 1024.0),
        total_bytes / (1024.0 * 1024.0)
      )
    elif self.item["status"] == "xlsx_images_processing":
      self.count_label.text = "Фото: {} из {}".format(
        self.item.get("processed", 0), self.item.get("page_total", 0)
      ) + size_label
    elif self.item["status"] in ("pdf_processing", "xlsx_processing"):
      unit = "строк" if is_xlsx else "страниц"
      suffix = " · листов: {}".format(self.item.get("sheet_count", 0)) if is_xlsx else ""
      self.count_label.text = "Готово {}% · {}: {} из {}{}".format(
        self.item.get("progress_percent", 0), unit, self.item.get("processed", 0),
        self.item.get("page_total", 0), suffix
      ) + size_label
    elif self.item["status"] in ("pdf_paused", "xlsx_paused", "pdf_failed", "xlsx_failed"):
      unit = "строк" if is_xlsx else "страниц"
      self.count_label.text = "Checkpoint: {} из {} {} · ошибок: {}".format(
        self.item.get("processed", 0), self.item.get("page_total", 0), unit,
        self.item.get("failed_pages", 0)
      ) + size_label
    else:
      detail = " · листов: {}".format(self.item.get("sheet_count", 0)) if is_xlsx else ""
      self.count_label.text = "Товаров: {} · добавлено: {}{}".format(
        self.item.get("total", 0), self.item.get("imported", 0), detail
      ) + size_label
    self.source_label.text = "{} · {}".format(file_type, self.item["source_name"])
    self.open_button.text = (
      "Проверить черновик" if self.item["status"] in (
        "pdf_draft", "pdf_processing", "pdf_failed", "pdf_paused",
        "xlsx_draft", "xlsx_uploading", "xlsx_processing", "xlsx_images_processing",
        "xlsx_failed", "xlsx_paused"
      )
      else "Открыть запись"
    )

  @handle("open_button", "click")
  def open_button_click(self, **event_args):
    self.parent.raise_event("x-pdf-draft-open", draft_id=self.item["id"])
