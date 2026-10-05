from ._anvil_designer import CustomFieldItemTemplate
from anvil import handle


class CustomFieldItem(CustomFieldItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    field = self.item
    self.custom_field_type.text = str({
      "text": "Текст", "number": "Число", "select": "Список", "bool": "Да / нет"
    }.get(field.get("type"), field.get("type", "")) or "")
    self.custom_field_required.text = str("Обязательное" if field.get("required") else "Необязательное")
    self.custom_field_visibility.text = str("Показывается" if field.get("visible", True) else "Скрыто")

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event("x-edit-custom-field", field=dict(self.item))

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    self.parent.raise_event("x-delete-custom-field", code=self.item.get("code"))
