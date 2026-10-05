from ._anvil_designer import AdminUsersTemplate
from anvil import confirm, handle
import anvil.server
from .. import Access


class AdminUsers(AdminUsersTemplate):
  def __init__(self, search_query="", **properties):
    super().__init__(**properties)
    if not Access.require_admin_form():
      return
    self._cursor_stack = []
    self._current_cursor = None
    self._next_cursor = None
    self._rows_by_id = {}
    self._managed_roles_by_id = {}
    self._updating = False
    self._role_options = []
    self.role_dropdown.items = list(self._role_options)
    self.create_role_dropdown.items = list(self._role_options)
    self.managed_role_dropdown.items = []
    self.enabled_dropdown.items = [("Активен", True), ("Заблокирован", False)]
    self.user_dropdown.items = []
    self.activity_box.text = "Выберите пользователя и загрузите журнал активности."
    self.created_password_box.text = ""
    self.delete_button.enabled = False
    self.search_box.text = search_query or ""
    self._load_managed_roles()
    self._load_page()

  def _permission_values(self):
    return [
      value.strip() for value in (self.permissions_box.text or "").replace(",", "\n").splitlines()
      if value.strip()
    ]

  def _load_page(self, cursor=None):
    self._current_cursor = cursor
    result = anvil.server.call(
      "get_admin_users_page", self.search_box.text or "", cursor
    )
    if not result["ok"]:
      self.user_dropdown.items = []
      self.admin_users_message.text = result["message"]
      self.next_button.visible = False
      return
    rows = result["rows"]
    self._role_options = list(result.get("roles") or [])
    self.role_dropdown.items = list(self._role_options)
    self.create_role_dropdown.items = list(self._role_options)
    if self.create_role_dropdown.selected_value is None and self._role_options:
      self.create_role_dropdown.selected_value = next(
        (code for _title, code in self._role_options if code == "user"),
        self._role_options[0][1]
      )
    self._rows_by_id = {row["id"]: row for row in rows}
    self.user_dropdown.items = [
      ("{} · {}{}".format(
        row["email"], row["role_title"], " · заблокирован" if not row["enabled"] else ""
      ), row["id"])
      for row in rows
    ]
    self._next_cursor = result["next_cursor"]
    self.next_button.visible = result["has_more"]
    self.previous_button.visible = bool(self._cursor_stack)
    self.delete_confirmation_checkbox.checked = False
    self.delete_button.enabled = False
    if rows:
      self.user_dropdown.selected_value = rows[0]["id"]
      self._show_selected_user()
    else:
      self.user_status.text = ""
      self.permissions_box.text = ""
      self.activity_box.text = ""
      self.admin_users_message.text = "Учётные записи не найдены."

  def _show_selected_user(self):
    row = self._rows_by_id.get(self.user_dropdown.selected_value)
    if row is None:
      return
    role_options = list(self._role_options)
    if row["role_code"] not in {value for _, value in role_options}:
      role_options.append(("{} · существующая роль".format(row["role_title"]), row["role_code"]))
    self.role_dropdown.items = role_options
    self._updating = True
    try:
      self.role_dropdown.selected_value = row["role_code"]
      self.enabled_dropdown.selected_value = row["enabled"]
      self.permissions_box.text = "\n".join(row["permissions"])
      self.permissions_box.enabled = row["role_code"] != "admin"
    finally:
      self._updating = False
    last_login = row["last_login"] or "Нет данных"
    self.user_status.text = (
      "Email подтверждён: {} · Последний вход: {} · Ошибки пароля: {}"
      .format("да" if row["confirmed_email"] else "нет", last_login,
              row["n_password_failures"])
    )
    self.admin_users_message.text = row["email"]
    self.activity_box.text = "Нажмите «Активность», чтобы загрузить журнал пользователя."
    self.delete_confirmation_checkbox.checked = False
    self.delete_button.enabled = False

  @handle("user_dropdown", "change")
  def user_dropdown_change(self, **event_args):
    self._show_selected_user()

  @handle("search_button", "click")
  def search_button_click(self, **event_args):
    self._cursor_stack = []
    self._load_page()

  @handle("save_user_button", "click")
  def save_user_button_click(self, **event_args):
    user_id = self.user_dropdown.selected_value
    if user_id is None:
      self.admin_users_message.text = "Выберите учётную запись."
      return
    self.save_user_button.enabled = False
    try:
      result = anvil.server.call(
        "update_managed_user", user_id, self.role_dropdown.selected_value,
        self.enabled_dropdown.selected_value, self._permission_values()
      )
    finally:
      self.save_user_button.enabled = True
    self.admin_users_message.text = result["message"]
    if result["ok"]:
      self._load_page(self._current_cursor)

  @handle("create_user_button", "click")
  def create_user_button_click(self, **event_args):
    self.create_user_button.enabled = False
    try:
      result = anvil.server.call(
        "create_managed_user", self.create_email_box.text or "",
        "", self.create_role_dropdown.selected_value,
        self._permission_values_for_create()
      )
    finally:
      self.create_user_button.enabled = True
    self.admin_users_message.text = result["message"]
    if result["ok"]:
      self.created_password_box.text = result["password"]
      self.create_email_box.text = ""
      self._cursor_stack = []
      self._load_page()

  def _permission_values_for_create(self):
    return [
      value.strip() for value in (self.create_permissions_box.text or "").replace(",", "\n").splitlines()
      if value.strip()
    ]

  def _role_permission_values(self):
    return [
      value.strip() for value in (self.managed_role_permissions_box.text or "").replace(",", "\n").splitlines()
      if value.strip()
    ]

  def _load_managed_roles(self, selected_role_id=None):
    result = anvil.server.call("get_managed_roles")
    if not result["ok"]:
      self.admin_users_message.text = result["message"]
      return
    roles = result["roles"]
    self._managed_roles_by_id = {row["id"]: row for row in roles}
    self.managed_role_dropdown.items = [
      ("{} · {} пользователей".format(row["title"], row["assigned_users"]), row["id"])
      for row in roles
    ]
    if selected_role_id not in self._managed_roles_by_id:
      selected_role_id = next(
        (row["id"] for row in roles if row["code"] == "moderator"),
        roles[0]["id"] if roles else None
      )
    self.managed_role_dropdown.selected_value = selected_role_id
    if selected_role_id:
      self._show_managed_role()
    else:
      self.managed_role_code_box.text = ""
      self.managed_role_title_box.text = ""
      self.managed_role_permissions_box.text = ""
      self.managed_role_usage.text = "Роли ещё не созданы."

  def _show_managed_role(self):
    role = self._managed_roles_by_id.get(self.managed_role_dropdown.selected_value)
    if role is None:
      return
    self._editing_role_id = role["id"]
    self.managed_role_code_box.text = role["code"]
    self.managed_role_title_box.text = role["title"]
    self.managed_role_permissions_box.text = "\n".join(role["permissions"])
    self.managed_role_code_box.enabled = False
    self.managed_role_title_box.enabled = not role["protected"]
    self.managed_role_permissions_box.enabled = not role["protected"]
    self.save_role_button.enabled = not role["protected"]
    self.delete_role_button.enabled = not role["built_in"]
    self.role_editor_heading.text = (
      "Системная роль ADMIN · неизменяемая" if role["protected"] else
      "Разрешения роли"
    )
    assigned = role["assigned_users"]
    self.managed_role_usage.text = (
      "Назначена пользователям: {}{}".format(
        assigned, " или больше" if assigned > 1000 else ""
      )
    )
    self.role_editor_status.text = ""

  @handle("managed_role_dropdown", "change")
  def managed_role_dropdown_change(self, **event_args):
    self._show_managed_role()

  @handle("new_role_button", "click")
  def new_role_button_click(self, **event_args):
    self.managed_role_dropdown.selected_value = None
    self._editing_role_id = None
    self.managed_role_code_box.enabled = True
    self.managed_role_title_box.enabled = True
    self.managed_role_permissions_box.enabled = True
    self.managed_role_code_box.text = ""
    self.managed_role_title_box.text = ""
    self.managed_role_permissions_box.text = ""
    self.managed_role_usage.text = "Новая роль пока не назначена пользователям."
    self.role_editor_heading.text = "Новая роль доступа"
    self.save_role_button.enabled = True
    self.delete_role_button.enabled = False
    self.role_editor_status.text = ""

  @handle("save_role_button", "click")
  def save_role_button_click(self, **event_args):
    self.save_role_button.enabled = False
    try:
      result = anvil.server.call(
        "save_managed_role", self._editing_role_id,
        self.managed_role_code_box.text or "",
        self.managed_role_title_box.text or "",
        self._role_permission_values()
      )
    finally:
      self.save_role_button.enabled = True
    self.role_editor_status.text = result["message"]
    if result["ok"]:
      self._editing_role_id = result["role_id"]
      self._load_managed_roles(result["role_id"])
      self._load_page(self._current_cursor)

  @handle("delete_role_button", "click")
  def delete_role_button_click(self, **event_args):
    role_id = self.managed_role_dropdown.selected_value
    role = self._managed_roles_by_id.get(role_id)
    if role is None or role["built_in"]:
      self.role_editor_status.text = "Выберите пользовательскую роль для удаления."
      return
    if not confirm(
      "Удалить роль «{}»? Сначала назначьте её пользователям другую роль.".format(role["title"]),
      title="Удалить роль"
    ):
      return
    result = anvil.server.call("delete_managed_role", role_id)
    self.role_editor_status.text = result["message"]
    if result["ok"]:
      self._editing_role_id = None
      self._load_managed_roles()
      self._load_page(self._current_cursor)

  @handle("create_role_dropdown", "change")
  def create_role_dropdown_change(self, **event_args):
    self.create_permissions_box.enabled = self.create_role_dropdown.selected_value != "admin"
    if self.create_role_dropdown.selected_value == "admin":
      self.create_permissions_box.text = ""

  @handle("role_dropdown", "change")
  def role_dropdown_change(self, **event_args):
    is_admin = self.role_dropdown.selected_value == "admin"
    self.permissions_box.enabled = not is_admin
    if is_admin and not self._updating:
      self.permissions_box.text = ""

  @handle("activity_button", "click")
  def activity_button_click(self, **event_args):
    user_id = self.user_dropdown.selected_value
    if user_id is None:
      self.activity_box.text = "Сначала выберите пользователя."
      return
    result = anvil.server.call("get_managed_user_activity", user_id)
    if not result["ok"]:
      self.activity_box.text = result["message"]
      return
    self.activity_box.text = "\n".join(
      "{} · {} · {} · {}".format(
        row["created_at"], row["actor"], row["action"], row["entity_type"]
      ) for row in result["rows"]
    ) or "Для пользователя пока нет событий."

  @handle("reset_access_button", "click")
  def reset_access_button_click(self, **event_args):
    user_id = self.user_dropdown.selected_value
    if user_id is None:
      self.admin_users_message.text = "Выберите учётную запись."
      return
    self.reset_access_button.enabled = False
    try:
      result = anvil.server.call("reset_managed_user_access", user_id)
    finally:
      self.reset_access_button.enabled = True
    self.admin_users_message.text = result["message"]
    if result["ok"]:
      self._load_page(self._current_cursor)

  @handle("delete_confirmation_checkbox", "change")
  def delete_confirmation_checkbox_change(self, **event_args):
    self.delete_button.enabled = bool(
      self.delete_confirmation_checkbox.checked and self.user_dropdown.selected_value
    )

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    user_id = self.user_dropdown.selected_value
    if not self.delete_confirmation_checkbox.checked or not user_id:
      self.admin_users_message.text = "Подтвердите удаление выбранной учётной записи."
      return
    self.delete_button.enabled = False
    try:
      result = anvil.server.call("delete_managed_user", user_id)
    finally:
      self.delete_button.enabled = False
    self.admin_users_message.text = result["message"]
    if result["ok"]:
      self._cursor_stack = []
      self._load_page()

  @handle("next_button", "click")
  def next_button_click(self, **event_args):
    if self._next_cursor is not None:
      self._cursor_stack.append(self._current_cursor)
      self._load_page(self._next_cursor)

  @handle("previous_button", "click")
  def previous_button_click(self, **event_args):
    if self._cursor_stack:
      self._load_page(self._cursor_stack.pop())
