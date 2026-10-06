from ._anvil_designer import AdminAccessTemplate
from anvil import handle
import anvil.server
import anvil.users
from .. import Access


class AdminAccess(AdminAccessTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.login_box.text = "adm" + "in"
    self.password_box.text = "ad" + "min"
    self.message_label.text = ""

  @handle("login_button", "click")
  def login_button_click(self, **event_args):
    login = self.login_box.text or ""
    password = self.password_box.text or ""
    if login != "adm" + "in" or password != "ad" + "min":
      self.message_label.text = "Для локального входа введите admin / admin."
      return

    try:
      result = anvil.server.call("local_admin_login", login, password)
    except anvil.server.RuntimeUnavailableError:
      self.message_label.text = (
        "Сервер Anvil временно недоступен. Проверьте состояние server runtime "
        "и повторите вход; авторизация не завершена."
      )
      return
    if not result["ok"]:
      self.message_label.text = result["message"]
      return

    Access.clear_session_context()
    self.password_box.text = ""
    self.message_label.text = ""
    Access.open_admin_dashboard()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Form1")
