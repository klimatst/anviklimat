from ._anvil_designer import ProviderItemTemplate
from anvil import handle
import anvil.server


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
FREE_MODELS = [
  ("Qwen 3.8 27B · free · vision", "qwen/qwen3.8-27b:free"),
  ("Gemma 4 26B · free · vision", "google/gemma-4-26b-a4b-it:free"),
  ("Gemma 4 31B · free · vision", "google/gemma-4-31b-it:free"),
  ("Nemotron 3 Nano Omni · free · vision", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
  ("Dots 3 Note Preview · free · vision", "dots-studio/dots-3-note-preview:free")
]


class ProviderItem(ProviderItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._delete_confirmed = False
    self.slot_label.text = self.item["slot_title"]
    self.model_box.text = self.item["model"]
    self.endpoint_box.text = self.item["endpoint"]
    self.priority_box.text = str(self.item.get("priority", 50))
    self.secret_ref_box.text = self.item["secret_ref"]
    self.enabled_checkbox.checked = self.item["enabled"]
    options = self.item.get("options") or {}
    temperature = options.get("temperature")
    self.temperature_box.text = "" if temperature is None else str(temperature)
    top_p = options.get("top_p")
    self.top_p_box.text = "" if top_p is None else str(top_p)
    frequency_penalty = options.get("frequency_penalty")
    self.frequency_penalty_box.text = "" if frequency_penalty is None else str(frequency_penalty)
    presence_penalty = options.get("presence_penalty")
    self.presence_penalty_box.text = "" if presence_penalty is None else str(presence_penalty)
    self.max_tokens_box.text = str(options.get("max_tokens", 0))
    self.timeout_box.text = str(options.get("timeout_seconds", 0))
    self.api_key_box.hide_text = True
    self.api_key_box.text = ""
    self.api_key_status.text = (
      "Ключ сохранён в закрытых серверных данных. Пустое поле оставит его без изменений."
      if self.item["has_api_key"] else
      "Указана старая ссылка на секрет Anvil."
      if self.item["secret_ref"] else "Ключ пока не задан."
    )
    self.model_preset_dropdown.items = [("Выберите бесплатную модель", None)] + FREE_MODELS
    self.model_preset_dropdown.selected_value = (
      self.item["model"] if self.item["model"] in [value for _, value in FREE_MODELS]
      else None
    )
    self.provider_dropdown.items = [("Совместимый API чата", "openai_compatible")]
    self.provider_dropdown.selected_value = self.item["provider"]
    self.delete_button.visible = self.item["slot"].startswith("api_")

  @handle("model_preset_dropdown", "change")
  def model_preset_dropdown_change(self, **event_args):
    model = self.model_preset_dropdown.selected_value
    if model:
      self.model_box.text = model
      self.endpoint_box.text = OPENROUTER_ENDPOINT

  @handle("save_button", "click")
  def save_button_click(self, **event_args):
    self.save_button.enabled = False
    try:
      result = anvil.server.call(
        "save_ai_provider", self.item["slot"],
        self.provider_dropdown.selected_value, self.model_box.text or "",
        self.endpoint_box.text or "", self.secret_ref_box.text or "",
        self.enabled_checkbox.checked, self.api_key_box.text or "",
        self.clear_api_key_checkbox.checked,
        {
          "temperature": self.temperature_box.text or "",
          "top_p": self.top_p_box.text or "",
          "frequency_penalty": self.frequency_penalty_box.text or "",
          "presence_penalty": self.presence_penalty_box.text or "",
          "max_tokens": self.max_tokens_box.text or "0",
          "timeout_seconds": self.timeout_box.text or "0"
        }, self.priority_box.text or "50"
      )
    finally:
      self.save_button.enabled = True
    self.save_message.text = result["message"]
    if result["ok"]:
      self.api_key_box.text = ""
      self.clear_api_key_checkbox.checked = False
      self.api_key_status.text = "Ключ сохранён в закрытых серверных данных. Пустое поле оставит его без изменений."
      self.parent.raise_event("x-ai-provider-saved")

  @handle("test_button", "click")
  def test_button_click(self, **event_args):
    if (self.api_key_box.text
        or (self.model_box.text or "").strip() != (self.item["model"] or "")
        or (self.endpoint_box.text or "").strip() != (self.item["endpoint"] or "")):
      self.save_message.text = "Сначала сохраните ключ, адрес и модель, затем проверьте подключение."
      return
    self.test_button.enabled = False
    self.save_message.text = "Проверяю API через сервер приложения…"
    try:
      result = anvil.server.call("test_ai_provider", self.item["slot"])
    finally:
      self.test_button.enabled = True
    self.save_message.text = result["message"]

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    if not self._delete_confirmed:
      self._delete_confirmed = True
      self.delete_button.text = "Нажмите ещё раз для удаления"
      self.save_message.text = "Удаление необратимо и не затрагивает историю запросов."
      return
    self.delete_button.enabled = False
    try:
      result = anvil.server.call("delete_ai_provider", self.item["slot"])
    finally:
      self.delete_button.enabled = True
    self.save_message.text = result["message"]
    if result["ok"]:
      self.parent.raise_event("x-ai-provider-deleted")
