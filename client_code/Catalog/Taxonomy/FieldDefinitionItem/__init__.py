from ._anvil_designer import FieldDefinitionItemTemplate
from anvil import handle


TYPE_TITLES = {
  "text": "Текст", "number": "Число", "price": "Цена",
  "date": "Дата", "select": "Список", "multiselect": "Несколько",
  "toggle": "Переключатель", "image": "Изображение", "file": "Файл",
  "url": "Ссылка", "rich_text": "Длинный текст"
}


class FieldDefinitionItem(FieldDefinitionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    state = "Включено" if self.item.get("enabled", True) else "Отключено"
    visibility = " · видно на сайте" if self.item.get("show_public") else " · только админке"
    self.field_summary.text = "{} · {}{}".format(
      TYPE_TITLES.get(self.item.get("kind"), "Поле"), state, visibility
    )

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event(
      "x-edit-custom-field", field_id=self.item["id"]
    )
