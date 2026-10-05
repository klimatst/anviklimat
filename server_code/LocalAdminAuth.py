"""Local-only admin credentials for this project's private development setup."""

import anvil.server
import anvil.users
from anvil.tables import app_tables


LOCAL_ADMIN_EMAIL = "admin@local.invalid"


def _admin_role():
  role = next((
    row for row in app_tables.roles.search()
    if isinstance(row["code"], str) and row["code"].lower() == "admin"
  ), None)
  if role is None:
    role = app_tables.roles.add_row(
      code="admin", title="Администратор", permissions=["*"]
    )
  return role


@anvil.server.callable
def local_admin_login(login, password):
  if login != "admin" or password != "admin":
    return {"ok": False, "message": "Неверный логин или пароль."}

  admin_role = _admin_role()
  user = app_tables.users.get(email=LOCAL_ADMIN_EMAIL)
  if user is not None:
    role = user["role"]
    role_code = role["code"] if role is not None else ""
    if not isinstance(role_code, str) or role_code.casefold() != "admin":
      return {
        "ok": False,
        "message": "Зарезервированная учётная запись уже используется. Обратитесь к владельцу приложения."
      }
    try:
      anvil.users.login_with_email(
        LOCAL_ADMIN_EMAIL, password, remember=False
      )
    except anvil.users.AuthenticationFailed:
      return {"ok": False, "message": "Неверный логин или пароль."}

  if user is None:
    try:
      anvil.users.signup_with_email(
        LOCAL_ADMIN_EMAIL, password, remember=False
      )
    except anvil.users.UserExists:
      return {
        "ok": False,
        "message": "Административная учётная запись создаётся. Повторите вход."
      }
    except anvil.users.PasswordNotAcceptable:
      return {
        "ok": False,
        "message": "Anvil Users отклонил пароль admin при создании аккаунта."
      }
    user = app_tables.users.get(email=LOCAL_ADMIN_EMAIL)
    if user is None:
      raise RuntimeError("The local administrator account was not created.")

  user.update(
    enabled=True,
    confirmed_email=True,
    role=admin_role,
    permissions=["*"],
    n_password_failures=0,
  )
  return {"ok": True}
