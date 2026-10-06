"""Small, read-only authentication lookups used by the client UI."""

import anvil.server
import anvil.users
import Core


def _anonymous_access_context():
  return {
    "email": "",
    "role_code": "user",
    "role_title": "Пользователь",
    "permissions": []
  }


@anvil.server.callable
def get_access_context():
  """Return role information for UI navigation without mutating user rows."""
  user = anvil.users.get_user()
  if user is None:
    return _anonymous_access_context()

  email = user["email"] or ""
  if Core._is_admin(user):
    role = user["role"]
    role_title = role["title"] if role is not None else "Администратор"
    if not isinstance(role_title, str) or not role_title:
      role_title = "Администратор"
    return {
      "email": email,
      "role_code": "admin",
      "role_title": role_title,
      "permissions": ["*"]
    }

  role = user["role"]
  raw_role_code = role["code"] if role is not None else "user"
  role_code = (
    raw_role_code.strip().lower()
    if isinstance(raw_role_code, str) else "user"
  )
  if not role_code:
    role_code = "user"
  role_title = role["title"] if role is not None else "Пользователь"
  if not isinstance(role_title, str):
    role_title = "Пользователь"

  if role_code == "admin":
    permissions = ["*"]
  else:
    role_permissions = role["permissions"] if role is not None else []
    user_permissions = user["permissions"] or []
    if not isinstance(role_permissions, (list, tuple, set)):
      role_permissions = []
    if not isinstance(user_permissions, (list, tuple, set)):
      user_permissions = []
    permissions = sorted({
      permission
      for permission in list(role_permissions) + list(user_permissions)
      if isinstance(permission, str)
    })

  return {
    "email": email,
    "role_code": role_code,
    "role_title": role_title,
    "permissions": permissions
  }
