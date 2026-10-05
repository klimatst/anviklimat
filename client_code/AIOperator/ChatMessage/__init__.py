from ._anvil_designer import ChatMessageTemplate
import anvil.server


PROVIDER_TITLES = {
  "primary": "Основной поставщик",
  "secondary": "Резервный поставщик 1",
  "third": "Резервный поставщик 2",
  "local": "Локальная модель"
}


class ChatMessage(ChatMessageTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.speaker_label.text = self.item.get("speaker", "")
    self.speaker_label.role = (
      "ai-chat-speaker-user" if self.item.get("role") == "user"
      else "ai-chat-speaker-assistant"
    )
    self.message_label.text = self.item.get("text", "")
    image = self.item.get("image")
    if image is not None:
      self.message_image.source = image
      self.message_image.visible = True
    provider = self.item.get("provider")
    if provider:
      title = PROVIDER_TITLES.get(provider, provider)
      self.message_meta.text = "{} · {} токенов".format(
        title, self.item.get("tokens", 0)
      )
      self.message_meta.visible = True
    else:
      self.message_meta.visible = False
