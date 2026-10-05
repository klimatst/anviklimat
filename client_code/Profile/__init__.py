from ._anvil_designer import ProfileTemplate
from .. import Access
from anvil import handle
import anvil.server
import anvil.users


class Profile(ProfileTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.message_label.text = ""
    self.refresh_profile()

  def refresh_profile(self):
    user = anvil.users.get_user()
    self.auth_panel.visible = user is None
    self.account_panel.visible = user is not None
    if user is None:
      return
    self.profile_email.text = user["email"]
    self.profile_role.text = "Сессия активна"

  @handle("login_button", "click")
  def login_button_click(self, **event_args):
    login = (self.login_box.text or "").strip()
    password = self.password_box.text or ""
    if not login or not password:
      self.message_label.text = "Введите логин и пароль."
      return
    email = login.lower()
    if "@" not in email:
      self.message_label.text = "Введите email или откройте отдельный вход администратора."
      return

    try:
      anvil.users.login_with_email(email, password, remember=False)
    except anvil.users.AuthenticationFailed:
      self.message_label.text = "Не удалось войти. Проверьте логин и пароль."
      return
    Access.clear_session_context()
    self.password_box.text = ""
    self.message_label.text = ""
    self.refresh_profile()
    Access.open_window("Form1")

  @handle("admin_access_button", "click")
  def admin_access_button_click(self, **event_args):
    Access.open_window("AdminAccess")

  @handle("signup_button", "click")
  def signup_button_click(self, **event_args):
    email = (self.signup_email_box.text or "").strip().lower()
    password = self.signup_password_box.text or ""
    if not email or "@" not in email:
      self.message_label.text = "Введите корректный email."
      return
    if len(password) < 8:
      self.message_label.text = "Пароль должен содержать не менее 8 символов."
      return
    result = anvil.server.call("register_site_user", email, password)
    if not result["ok"]:
      self.message_label.text = result["message"]
      return
    try:
      anvil.users.login_with_email(email, password, remember=False)
    except anvil.users.AuthenticationFailed:
      self.message_label.text = "Профиль создан. Теперь войдите с указанными email и паролем."
      return
    Access.clear_session_context()
    self.signup_password_box.text = ""
    self.message_label.text = ""
    self.refresh_profile()
    Access.open_window("Form1")

  @handle("logout_button", "click")
  def logout_button_click(self, **event_args):
    anvil.users.logout()
    Access.clear_session_context()
    self.refresh_profile()
    Access.open_window("Form1")
