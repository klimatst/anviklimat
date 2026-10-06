from ._anvil_designer import CustomFieldItemTemplate
from anvil import handle
import anvil.server


KIND_LABELS = {
  "text": "Текст", "number": "Число", "price": "Цена",
  "date": "Дата · ГГГГ-ММ-ДД", "select": "Список",
  "multiselect": "Несколько значений", "toggle": "Переключатель",
  "image": "Изображение", "file": "Файл или документ",
  "url": "Ссылка", "rich_text": "Длинный текст"
}


class CustomFieldItem(CustomFieldItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._kind = self.item["kind"]
    self._product_id = self.item.get("product_id")
    self._stored_reference = self.item.get("stored_reference", "")
    self.field_title.text = self.item["title"]
    unit = self.item.get("unit") or KIND_LABELS.get(self._kind, "")
    required = " · обязательно" if self.item.get("required") else ""
    self.field_hint.text = "{}{}".format(unit, required)
    self.value_box.visible = self._kind in (
      "text", "number", "price", "date", "url", "image", "file"
    )
    self.value_box.placeholder = {
      "number": "Введите число", "price": "Введите цену",
      "date": "ГГГГ-ММ-ДД", "url": "HTTPS-ссылка",
      "image": "HTTPS-ссылка или загрузите фото",
      "file": "HTTPS-ссылка или загрузите документ"
    }.get(self._kind, "Введите значение")
    self.rich_value_box.visible = self._kind in ("rich_text", "multiselect")
    self.rich_value_box.placeholder = (
      "Выберите значения · по одному на строку" if self._kind == "multiselect"
      else "Введите текст"
    )
    self.choice_dropdown.visible = self._kind == "select"
    if self._kind == "select":
      self.choice_dropdown.items = [("Выберите значение", "")] + [
        (choice, choice) for choice in self.item.get("choices", [])
      ]
      self.choice_dropdown.selected_value = self.item.get("value") or ""
    else:
      self.choice_dropdown.items = []
    self.toggle_checkbox.visible = self._kind == "toggle"
    self.toggle_checkbox.checked = bool(self.item.get("value"))
    self.file_loader.visible = self._kind in ("image", "file")
    self.file_loader.text = (
      "Заменить изображение" if self._kind == "image" else "Загрузить документ"
    )
    self.value_box.text = (
      self.item.get("value") or ""
      if self._kind != "toggle" else ""
    )
    value = self.item.get("value")
    self.rich_value_box.text = (
      "\n".join(value) if self._kind == "multiselect" and isinstance(value, list)
      else value if self._kind == "rich_text" and isinstance(value, str)
      else ""
    )
    self.save_button.enabled = self._product_id is not None
    self.field_status.text = (
      "Сначала сохраните товар, чтобы редактировать его значения."
      if self._product_id is None else ""
    )

  def _value(self):
    if self._kind == "toggle":
      return bool(self.toggle_checkbox.checked)
    if self._kind == "select":
      return self.choice_dropdown.selected_value or ""
    if self._kind == "multiselect":
      return [
        line.strip() for line in (self.rich_value_box.text or "").splitlines()
        if line.strip()
      ]
    if self._kind == "rich_text":
      return self.rich_value_box.text or ""
    return self.value_box.text or ""

  @handle("save_button", "click")
  def save_button_click(self, **event_args):
    if self._product_id is None:
      self.field_status.text = "Сначала сохраните товар."
      return
    files = self.file_loader.files or []
    self.save_button.enabled = False
    try:
      result = anvil.server.call(
        "save_product_custom_field_value", self._product_id,
        self.item["id"], self._value(), files[0] if files else None
      )
    finally:
      self.save_button.enabled = self._product_id is not None
    self.field_status.text = result["message"]
    if result["ok"]:
      self.file_loader.clear()
      self.parent.raise_event("x-custom-field-saved", field_id=self.item["id"])
