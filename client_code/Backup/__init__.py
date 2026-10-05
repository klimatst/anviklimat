from ._anvil_designer import BackupTemplate
from anvil import handle
import anvil.media
import anvil.server
import anvil.users
from .. import Access


class Backup(BackupTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_admin_form():
      return
    self.restore_file.file_types = ".enc"

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("create_backup_button", "click")
  def create_backup_button_click(self, **event_args):
    self.create_backup_button.enabled = False
    try:
      result = anvil.server.call("create_database_backup")
    finally:
      self.create_backup_button.enabled = True
    if not result["ok"]:
      self.backup_message.text = result["message"]
      return
    anvil.media.download(result["file"])
    self.backup_message.text = "{} SHA-256: {}".format(
      result["message"], result["checksum"]
    )

  @handle("inspect_backup_button", "click")
  def inspect_backup_button_click(self, **event_args):
    if self.restore_file.file is None:
      self.restore_message.text = "Выберите зашифрованный архив."
      return
    self.inspect_backup_button.enabled = False
    try:
      result = anvil.server.call("inspect_database_backup", self.restore_file.file)
    finally:
      self.inspect_backup_button.enabled = True
    self.restore_message.text = result["message"]
    if result["ok"]:
      self.restore_message.text += "\nДата: {}; таблиц: {}; строк: {}; SHA-256: {}".format(
        result["created_at"], result["tables"], result["rows"], result["checksum"]
      )

  @handle("restore_backup_button", "click")
  def restore_backup_button_click(self, **event_args):
    if self.restore_file.file is None:
      self.restore_message.text = "Выберите зашифрованный архив."
      return
    self.restore_backup_button.enabled = False
    try:
      result = anvil.server.call("restore_database_backup", self.restore_file.file)
    finally:
      self.restore_backup_button.enabled = True
    self.restore_message.text = result["message"]
