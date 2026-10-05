from ._anvil_designer import CustomFieldItemTemplate
from anvil import handle


class CustomFieldItem(CustomFieldItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    field = self.item
    self.custom_label.text = str(field.get("label", field.get("code", "")))
    self.custom_hint.text = str(field.get("description", ""))
    self.custom_unit.text = str(field.get("unit", ""))
    kind = field.get("type", "text")
    self.custom_text.visible = kind in ("text", "number")
    self.custom_choice.visible = kind == "select"
    self.custom_choice.items = [(str(item), str(item)) for item in field.get("choices", [])]
    self.custom_bool.visible = kind == "bool"
    value = field.get("value", field.get("default", ""))
    if kind == "bool":
      self.custom_bool.checked = bool(value)
    elif kind == "select":
      self.custom_choice.selected_value = value if value in field.get("choices", []) else (
        field.get("choices", [None])[0] if field.get("choices") else None
      )
    else:
      self.custom_text.text = "" if value is None else str(value)

  @handle("custom_text", "change")
  def custom_text_change(self, **event_args):
    self.item["value"] = self.custom_text.text or ""

  @handle("custom_bool", "change")
  def custom_bool_change(self, **event_args):
    self.item["value"] = bool(self.custom_bool.checked)

  @handle("custom_choice", "change")
  def custom_choice_change(self, **event_args):
    self.item["value"] = self.custom_choice.selected_value
