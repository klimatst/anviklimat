from ._anvil_designer import SettingFieldItemTemplate


class SettingFieldItem(SettingFieldItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.field_title.text = self.item["label"]
    self.field_hint.text = self.item.get("hint", "")
    kind = self.item["type"]
    value = self.item.get("value")
    self.text_input.visible = kind in ("text", "url", "number")
    self.long_input.visible = kind == "textarea"
    self.choice_input.visible = kind == "select"
    self.boolean_input.visible = kind == "bool"
    if kind in ("text", "url", "number"):
      self.text_input.placeholder = self.item.get("hint", "Введите значение")
      self.text_input.text = "" if value is None else str(value)
    elif kind == "textarea":
      self.long_input.text = "" if value is None else str(value)
    elif kind == "select":
      self.choice_input.items = self.item.get("choices", [])
      self.choice_input.selected_value = value
    elif kind == "bool":
      self.boolean_input.checked = bool(value)
