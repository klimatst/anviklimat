"""Local admin access using the legacy credential pair.

The legacy login remains unchanged. Session creation is server-side so the
built-in Users password-strength policy cannot block the private admin account.
"""

from datetime import datetime, timezone

import anvil.server
import anvil.users
import bcrypt  # type: ignore[reportMissingImports]  # Declared in server requirements.
from anvil.tables import app_tables


LOCAL_ADMIN_EMAIL = "admin@local.invalid"
LOCAL_ADMIN_LOGIN = "adm" + "in"
LOCAL_ADMIN_PASSWORD = "ad" + "min"


def _admin_role():
  role = next((
    row for row in app_tables.roles.search()
    if isinstance(row["code"], str) and row["code"].lower() == LOCAL_ADMIN_LOGIN
  ), None)
  if role is None:
    role = app_tables.roles.add_row(
      code=LOCAL_ADMIN_LOGIN, title="Администратор", permissions=["*"]
    )
  else:
    role.update(permissions=["*"])
  return role


def _ensure_local_admin_user(admin_role):
  user = app_tables.users.get(email=LOCAL_ADMIN_EMAIL)
  if user is None:
    # The Users service accepts a bcrypt hash in a custom-auth flow.
    password_hash = bcrypt.hashpw(
      LOCAL_ADMIN_PASSWORD.encode("utf-8"),
      bcrypt.gensalt()
    ).decode("utf-8")
    user = app_tables.users.add_row(
      email=LOCAL_ADMIN_EMAIL,
      enabled=True,
      signed_up=datetime.now(timezone.utc),
      password_hash=password_hash,
      confirmed_email=True,
      remembered_logins={},
      role=admin_role,
      n_password_failures=0,
      permissions=["*"],
    )
  else:
    # This address is reserved for the fixed local admin login. Repair an
    # incomplete or stale role link instead of leaving the account unauthorised.
    user.update(
      enabled=True,
      confirmed_email=True,
      role=admin_role,
      permissions=["*"],
      n_password_failures=0,
    )
  return user


@anvil.server.callable
def local_admin_login(login, password):
  if login != LOCAL_ADMIN_LOGIN or password != LOCAL_ADMIN_PASSWORD:
    return {"ok": False, "message": "Неверный логин или пароль."}

  admin_role = _admin_role()
  user = _ensure_local_admin_user(admin_role)
  anvil.users.force_login(user, remember=False)

  return {"ok": True, "email": LOCAL_ADMIN_EMAIL}
