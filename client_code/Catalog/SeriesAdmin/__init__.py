from ._anvil_designer import SeriesAdminTemplate
from anvil import confirm, handle
import anvil.server
from ... import Access


class SeriesAdmin(SeriesAdminTemplate):
  def __init__(self, selected_series_id=None, **properties):
    super().__init__(**properties)
    if not Access.require_permission_form("catalog.manage"):
      return
    self._series = []
    self._series_by_id = {}
    self._series_id = None
    self._categories = []
    self.status_dropdown.items = [
      ("Опубликована", "active"), ("Черновик", "draft"), ("В архиве", "archived")
    ]
    self.document_kind_dropdown.items = [
      ("Инструкция", "instruction"), ("Технические данные", "datasheet"),
      ("Сертификат", "certificate"), ("Другой документ", "other")
    ]
    self.document_kind_dropdown.selected_value = "instruction"
    self._load_data(selected_series_id)
    if selected_series_id and selected_series_id in self._series_by_id:
      self._show_series(self._series_by_id[selected_series_id])
    else:
      self._new_series()

  def _load_data(self, selected_series_id=None):
    result = anvil.server.call("get_catalog_series_admin")
    self._series = result["series"]
    self._series_by_id = {row["id"]: row for row in self._series}
    self._categories = result["categories"]
    self.series_rows.items = self._series
    self.category_dropdown.items = [("Выберите категорию", None)] + [
      (row["path"] if row.get("path") else row["title"], row["id"])
      for row in self._categories
    ]
    if selected_series_id and selected_series_id in self._series_by_id:
      self._show_series(self._series_by_id[selected_series_id])
    self.series_status.text = "Серий: {} · без потери товаров и документов".format(
      len(self._series)
    )

  def _new_series(self):
    self._series_id = None
    self.title_box.text = ""
    self.category_dropdown.selected_value = None
    self.description_box.text = ""
    self.power_range_box.text = ""
    self.status_dropdown.selected_value = "active"
    self.is_new_checkbox.checked = False
    self.active_checkbox.checked = True
    self.sort_order_box.text = "1000"
    self.image_file.files = []
    self.image_preview.source = ""
    self.image_preview.visible = False
    self.series_editor_heading.text = "Новая серия"
    self.series_delete_button.visible = False
    self.document_panel.visible = False
    self.document_rows.items = []
    self.series_message.text = "Сначала сохраните серию, затем прикрепите к ней документы."

  def _show_series(self, row):
    self._series_id = row["id"]
    self.title_box.text = row["title"] or ""
    self.category_dropdown.selected_value = row["category_id"]
    self.description_box.text = row["description"] or ""
    self.power_range_box.text = row["power_range"] or ""
    self.status_dropdown.selected_value = row["status"] or "active"
    self.is_new_checkbox.checked = bool(row["is_new"])
    self.active_checkbox.checked = bool(row["active"])
    self.sort_order_box.text = str(row["sort_order"] or 0)
    self.image_file.files = []
    self.image_preview.source = row["image_url"] or ""
    self.image_preview.visible = bool(row["image_url"])
    self.series_editor_heading.text = "Изменить: {}".format(row["title"])
    self.series_delete_button.visible = True
    self.document_panel.visible = True
    self.series_message.text = "Моделей: {} · документов: {}".format(
      row["product_count"], row["document_count"]
    )
    self._load_documents()

  def _load_documents(self):
    if not self._series_id:
      self.document_rows.items = []
      return
    result = anvil.server.call("get_catalog_documents", "series", self._series_id)
    self.document_rows.items = [dict(row, can_delete=True) for row in result["documents"]]

  @handle("series_rows", "x-edit-series")
  def series_rows_edit_series(self, series_id, **event_args):
    row = self._series_by_id.get(series_id)
    if row:
      self._show_series(row)

  @handle("new_series_button", "click")
  def new_series_button_click(self, **event_args):
    self._new_series()

  @handle("sync_series_button", "click")
  def sync_series_button_click(self, **event_args):
    self.sync_series_button.enabled = False
    try:
      result = anvil.server.call("sync_catalog_series_from_specs")
    finally:
      self.sync_series_button.enabled = True
    self.series_status.text = result["message"]
    if result["ok"]:
      self._load_data()

  @handle("save_series_button", "click")
  def save_series_button_click(self, **event_args):
    payload = {
      "title": self.title_box.text or "",
      "category_id": self.category_dropdown.selected_value,
      "description": self.description_box.text or "",
      "power_range": self.power_range_box.text or "",
      "status": self.status_dropdown.selected_value or "active",
      "is_new": self.is_new_checkbox.checked,
      "active": self.active_checkbox.checked,
      "sort_order": self.sort_order_box.text or "0"
    }
    self.save_series_button.enabled = False
    try:
      result = anvil.server.call(
        "save_catalog_series", self._series_id, payload,
        (self.image_file.files or [None])[0]
      )
    finally:
      self.save_series_button.enabled = True
    self.series_message.text = result["message"]
    if result["ok"]:
      self._series_id = result["series_id"]
      self.image_file.files = []
      self._load_data(self._series_id)

  @handle("series_delete_button", "click")
  def series_delete_button_click(self, **event_args):
    if not confirm("Удалить серию? Сначала нужно перенести связанные модели и документы."):
      return
    result = anvil.server.call("delete_catalog_series", self._series_id)
    self.series_message.text = result["message"]
    if result["ok"]:
      self._load_data()
      self._new_series()

  @handle("add_document_button", "click")
  def add_document_button_click(self, **event_args):
    result = anvil.server.call(
      "save_catalog_document", "series", self._series_id,
      self.document_title_box.text or "", self.document_kind_dropdown.selected_value or "other",
      (self.document_file.files or [None])[0], self.document_url_box.text or "",
      self.document_order_box.text or "0"
    )
    self.document_message.text = result["message"]
    if result["ok"]:
      self.document_title_box.text = ""
      self.document_file.files = []
      self.document_url_box.text = ""
      self._load_documents()
      self._load_data(self._series_id)

  @handle("document_rows", "x-document-deleted")
  def document_rows_document_deleted(self, **event_args):
    self._load_documents()
    self._load_data(self._series_id)

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_window("Catalog")
