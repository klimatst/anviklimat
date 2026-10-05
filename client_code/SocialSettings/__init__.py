from ._anvil_designer import SocialSettingsTemplate
from anvil import handle
import anvil.server
from .. import Access


class SocialSettings(SocialSettingsTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_admin_form():
      return
    settings = anvil.server.call("get_social_settings")["settings"]
    self.telegram_chat_id_box.text = settings["telegram_chat_id"]
    self.telegram_chat_targets_box.text = settings["telegram_chat_targets"]
    self.telegram_status.text = (
      "Токен Telegram настроен."
      if settings["telegram_configured"]
      else "Добавьте TELEGRAM_BOT_TOKEN в Anvil Secrets."
    )
    self.vk_url_box.text = settings["vk_url"]
    self.ok_url_box.text = settings["ok_url"]
    self.dzen_url_box.text = settings["dzen_url"]
    self.max_url_box.text = settings["max_url"]

  @handle("save_telegram_button", "click")
  def save_telegram_button_click(self, **event_args):
    self.save_telegram_button.enabled = False
    try:
      result = anvil.server.call(
        "save_telegram_target", self.telegram_chat_id_box.text or ""
      )
    finally:
      self.save_telegram_button.enabled = True
    self.social_message.text = result["message"]

  @handle("save_telegram_targets_button", "click")
  def save_telegram_targets_button_click(self, **event_args):
    self.save_telegram_targets_button.enabled = False
    try:
      result = anvil.server.call(
        "save_telegram_chat_targets", self.telegram_chat_targets_box.text or ""
      )
    finally:
      self.save_telegram_targets_button.enabled = True
    self.social_message.text = result["message"]

  @handle("send_report_button", "click")
  def send_report_button_click(self, **event_args):
    self.send_report_button.enabled = False
    try:
      result = anvil.server.call("send_telegram_summary")
    finally:
      self.send_report_button.enabled = True
    self.social_message.text = result["message"]

  @handle("save_social_links_button", "click")
  def save_social_links_button_click(self, **event_args):
    result = anvil.server.call("save_social_links", {
      "vk_url": self.vk_url_box.text or "",
      "ok_url": self.ok_url_box.text or "",
      "dzen_url": self.dzen_url_box.text or "",
      "max_url": self.max_url_box.text or ""
    })
    self.social_message.text = result["message"]

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
