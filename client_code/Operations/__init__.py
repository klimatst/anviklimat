from ._anvil_designer import OperationsTemplate
from anvil import handle
import anvil.server
import anvil.users
import json
from .. import Access


class Operations(OperationsTemplate):
  def __init__(self, section=None, **properties):
    super().__init__(**properties)
    context = Access.get_session_context()
    permissions = set(context["permissions"])
    self._can_manage_operations = (
      context["role_code"] == "admin" or "operations.manage" in permissions
    )
    self._can_manage_service = (
      context["role_code"] == "admin" or "service.manage" in permissions
    )
    if not (self._can_manage_operations or self._can_manage_service):
      Access.require_permission_form("operations.manage")
      return
    service_only = section == "service" or not self._can_manage_operations
    self.crm_panel.visible = self._can_manage_operations and not service_only
    self.client_editor.visible = False
    self.project_link_panel.visible = self._can_manage_operations and not service_only
    self.tasks_panel.visible = self._can_manage_operations and not service_only
    self.estimate_panel.visible = self._can_manage_operations and not service_only
    self.quote_panel.visible = self._can_manage_operations and not service_only
    self.service_panel.visible = self._can_manage_service and (
      service_only or section is None
    )
    self.new_client_button.visible = self._can_manage_operations and not service_only
    self._client_id = None
    self._clients = []
    self._projects = []
    self._products_by_id = {}
    self.client_editor.visible = False
    self.quote_message.text = ""
    self.service_message.text = ""
    self.client_type_dropdown.items = [
      ("Организация", "organization"), ("Частный клиент", "individual")
    ]
    self._load_context()

  def _load_context(self, selected_client_id=None):
    try:
      options = anvil.server.call("get_operations_bootstrap")
    except Exception as exc:
      self.crm_message.text = "Не удалось загрузить рабочую среду: {}".format(exc)
      return
    if not options.get("ok"):
      self.crm_message.text = options.get("message", "Рабочая среда недоступна.")
      return
    if self._can_manage_operations:
      self.task_status_dropdown.items = options.get("task_statuses", [])
      self._clients = options.get("clients", [])
      self.client_rows.items = self._clients
      client_options = [("Клиент не назначен", None)] + [
        ("{} · {}".format(row["name"], row["email"] or row["phone"]), row["id"])
        for row in self._clients
      ]
      for dropdown in (self.project_client_dropdown, self.task_client_dropdown):
        dropdown.items = client_options
      self.crm_message.text = "Клиентов: {}".format(len(self._clients))
      self._projects = options.get("projects", [])
      project_options = [("Выберите проект", None)] + [
        ("{} · {}".format(row["code"], row["title"]), row["id"])
        for row in self._projects
      ]
      for dropdown in (
        self.project_link_dropdown, self.task_project_dropdown,
        self.estimate_project_dropdown, self.service_project_dropdown
      ):
        dropdown.items = project_options
      self.project_message.text = "Проектов в списке: {}".format(len(self._projects))
      tasks = options.get("tasks", [])
      for row in tasks:
        row["can_complete"] = row["status"] not in ("done", "cancelled")
      self.task_rows.items = tasks
      self.task_message.text = "Задач: {}".format(len(tasks))
    elif self._can_manage_service:
      projects = options.get("service_projects", [])
      self.service_project_dropdown.items = [("Выберите проект", None)] + [
        ("{} · {}".format(row["code"], row["title"]), row["id"]) for row in projects
      ]
      self.project_message.text = "Проектов на странице: {}".format(len(projects))
    if self._can_manage_service:
      self.service_type_dropdown.items = options.get("service_types", [])
      self.service_status_dropdown.items = options.get("service_statuses", [])
    if selected_client_id:
      self.project_client_dropdown.selected_value = selected_client_id
      self.task_client_dropdown.selected_value = selected_client_id


  def _load_service_projects(self, search_text=""):
    result = anvil.server.call("get_projects_page", search_text, None)
    if not result["ok"]:
      self.project_message.text = result["message"]
      return
    self.service_project_dropdown.items = [("Выберите проект", None)] + [
      ("{} · {}".format(row["code"], row["title"]), row["id"])
      for row in result["rows"]
    ]
    self.project_message.text = "Проектов на странице: {}. Используйте поиск для остальных.".format(
      len(result["rows"])
    )

  def _load_clients(self, selected_client_id=None):
    result = anvil.server.call("get_crm_clients")
    if not result["ok"]:
      self.crm_message.text = result["message"]
      self.client_rows.items = []
      return
    self._clients = result["rows"]
    self.client_rows.items = self._clients
    options = [("Клиент не назначен", None)] + [
      ("{} · {}".format(row["name"], row["email"] or row["phone"]), row["id"])
      for row in self._clients
    ]
    for dropdown in (self.project_client_dropdown, self.task_client_dropdown):
      dropdown.items = options
    self.crm_message.text = "Клиентов: {}".format(len(self._clients))
    if selected_client_id:
      self.project_client_dropdown.selected_value = selected_client_id
      self.task_client_dropdown.selected_value = selected_client_id

  def _load_projects(self, search_text=""):
    result = anvil.server.call("get_projects_page", search_text, None)
    if not result["ok"]:
      self.project_message.text = result["message"]
      return
    self._projects = result["rows"]
    options = [("Выберите проект", None)] + [
      ("{} · {}".format(row["code"], row["title"]), row["id"])
      for row in self._projects
    ]
    self.project_link_dropdown.items = options
    self.task_project_dropdown.items = options
    self.estimate_project_dropdown.items = options
    self.service_project_dropdown.items = options
    self.project_message.text = "Проектов в списке: {}. Введите поиск, чтобы найти остальные.".format(
      len(self._projects)
    )

  def _load_tasks(self):
    result = anvil.server.call("get_crm_tasks")
    if not result["ok"]:
      self.task_message.text = result["message"]
      self.task_rows.items = []
      return
    for row in result["rows"]:
      row["can_complete"] = row["status"] not in ("done", "cancelled")
    self.task_rows.items = result["rows"]
    self.task_message.text = "Задач: {}".format(len(result["rows"]))

  def _load_client(self, client_id):
    result = anvil.server.call("get_crm_client_details", client_id)
    if not result["ok"]:
      self.crm_message.text = result["message"]
      return
    client = result["client"]
    self._client_id = client["id"]
    self.client_editor.visible = True
    for field in (
      "name", "tax_id", "email", "phone", "address", "notes",
      "contact_name", "contact_role", "contact_email", "contact_phone"
    ):
      getattr(self, "client_{}_box".format(field)).text = client[field]
    self.client_type_dropdown.selected_value = client["client_type"]
    self.client_save_message.text = ""

  def _new_client(self):
    self._client_id = None
    self.client_editor.visible = True
    for field in (
      "name", "tax_id", "email", "phone", "address", "notes",
      "contact_name", "contact_role", "contact_email", "contact_phone"
    ):
      getattr(self, "client_{}_box".format(field)).text = ""
    self.client_type_dropdown.selected_value = "organization"
    self.client_save_message.text = ""

  def _save_client(self):
    self.save_client_button.enabled = False
    try:
      result = anvil.server.call(
        "save_crm_client",
        {
          "name": self.client_name_box.text or "",
          "client_type": self.client_type_dropdown.selected_value,
          "tax_id": self.client_tax_id_box.text or "",
          "email": self.client_email_box.text or "",
          "phone": self.client_phone_box.text or "",
          "address": self.client_address_box.text or "",
          "notes": self.client_notes_box.text or ""
        },
        {
          "name": self.client_contact_name_box.text or "",
          "role": self.client_contact_role_box.text or "",
          "email": self.client_contact_email_box.text or "",
          "phone": self.client_contact_phone_box.text or ""
        },
        self._client_id
      )
    except Exception as exc:
      self.client_save_message.text = "Не удалось сохранить клиента: {}".format(exc)
      return
    finally:
      self.save_client_button.enabled = True
    self.client_save_message.text = result["message"]
    if result["ok"]:
      self._client_id = result["client_id"]
      self._load_clients(self._client_id)
      self._load_client(self._client_id)

  def _link_project_client(self):
    result = anvil.server.call(
      "assign_project_client",
      self.project_link_dropdown.selected_value,
      self.project_client_dropdown.selected_value
    )
    self.project_message.text = result["message"]

  def _save_task(self):
    result = anvil.server.call(
      "save_crm_task",
      {
        "title": self.task_title_box.text or "",
        "description": self.task_description_box.text or "",
        "status": self.task_status_dropdown.selected_value,
        "due_at": self.task_due_box.text or "",
        "client_id": self.task_client_dropdown.selected_value,
        "project_id": self.task_project_dropdown.selected_value
      }
    )
    self.task_message.text = result["message"]
    if result["ok"]:
      self.task_title_box.text = ""
      self.task_description_box.text = ""
      self.task_due_box.text = ""
      self._load_tasks()

  def _build_estimate(self):
    project_id = self.estimate_project_dropdown.selected_value
    result = anvil.server.call(
      "build_project_estimate", project_id,
      self.labor_cost_box.text or "", self.consumables_cost_box.text or ""
    )
    self.estimate_message.text = result["message"]
    if result["ok"]:
      self.estimate_summary.text = (
        "Материалы: {} {} · Работы: {} {} · Расходные материалы: {} {} · Итого: {} {} · Версия {}"
      ).format(
        result["materials_cost"], result["currency"], result["labor_cost"],
        result["currency"], result["consumables_cost"], result["currency"],
        result["total"], result["currency"], result["version"]
      )
      self.quote_panel.visible = True
      self._load_quotes(project_id)
    elif result.get("missing"):
      self.estimate_message.text += " " + ", ".join(result["missing"])

  def _load_quotes(self, project_id):
    if not project_id:
      self.quote_rows.items = []
      return
    result = anvil.server.call("get_project_quotes", project_id)
    if result["ok"]:
      for row in result["rows"]:
        row["can_send"] = row["status"] == "draft"
        row["can_approve"] = row["status"] == "sent"
      self.quote_rows.items = result["rows"]
    else:
      self.quote_message.text = result["message"]

  def _create_quote(self):
    result = anvil.server.call(
      "create_project_quote",
      self.estimate_project_dropdown.selected_value,
      self.quote_terms_box.text or "",
      self.quote_expiry_box.text or None
    )
    self.quote_message.text = result["message"]
    if result["ok"]:
      self._load_quotes(self.estimate_project_dropdown.selected_value)

  def _load_service_systems(self):
    project_id = self.service_project_dropdown.selected_value
    if not project_id:
      self.service_system_dropdown.items = [("Не выбрана", None)]
      self.service_rows.items = []
      return
    result = anvil.server.call("get_project_workspace", project_id)
    if not result["ok"]:
      self.service_message.text = result["message"]
      return
    self.service_system_dropdown.items = [("Не выбрана", None)] + [
      ("{} · {}".format(row["type_title"], row["title"]), row["id"])
      for row in result["systems"]
    ]
    self._load_service_records()

  def _load_products(self):
    result = anvil.server.call(
      "search_catalog", self.service_product_search_box.text or "", None, None
    )
    if not result["ok"]:
      self.service_message.text = result["message"]
      return
    self._products_by_id = {row["id"]: row for row in result["rows"]}
    self.service_product_dropdown.items = [("Не привязано", None)] + [
      ("{} · {}".format(row["brand"], row["model"]), row["id"])
      for row in result["rows"]
    ]

  def _load_service_records(self):
    project_id = self.service_project_dropdown.selected_value
    if not project_id:
      return
    result = anvil.server.call("get_service_records", project_id)
    if result["ok"]:
      self.service_rows.items = result["rows"]
      self.service_message.text = "Записей обслуживания: {}".format(len(result["rows"]))

  def _save_service(self):
    try:
      details = json.loads(self.service_details_box.text or "{}")
    except ValueError:
      self.service_message.text = "Проверьте JSON сервисных параметров."
      return
    if not isinstance(details, dict):
      self.service_message.text = "Сервисные параметры должны быть JSON-объектом."
      return
    result = anvil.server.call(
      "save_service_record",
      {
        "project_id": self.service_project_dropdown.selected_value,
        "system_id": self.service_system_dropdown.selected_value,
        "product_id": self.service_product_dropdown.selected_value,
        "serial": self.service_serial_box.text or "",
        "service_type": self.service_type_dropdown.selected_value,
        "status": self.service_status_dropdown.selected_value,
        "scheduled_at": self.service_scheduled_box.text or "",
        "completed_at": self.service_completed_box.text or "",
        "details": details
      }
    )
    self.service_message.text = result["message"]
    if result["ok"]:
      self._load_service_records()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("new_client_button", "click")
  def new_client_button_click(self, **event_args):
    self._new_client()

  @handle("client_rows", "x-client-edit")
  def client_rows_client_edit(self, client_id, **event_args):
    self._load_client(client_id)

  @handle("save_client_button", "click")
  def save_client_button_click(self, **event_args):
    self._save_client()

  @handle("cancel_client_button", "click")
  def cancel_client_button_click(self, **event_args):
    self.client_editor.visible = False

  @handle("project_search_button", "click")
  def project_search_button_click(self, **event_args):
    self._load_projects(self.project_search_box.text or "")

  @handle("link_project_button", "click")
  def link_project_button_click(self, **event_args):
    self._link_project_client()

  @handle("save_task_button", "click")
  def save_task_button_click(self, **event_args):
    self._save_task()

  @handle("task_rows", "x-task-complete")
  def task_rows_task_complete(self, task_id, **event_args):
    result = anvil.server.call("update_crm_task_status", task_id, "done")
    self.task_message.text = result["message"]
    if result["ok"]:
      self._load_tasks()

  @handle("build_estimate_button", "click")
  def build_estimate_button_click(self, **event_args):
    self._build_estimate()

  @handle("create_quote_button", "click")
  def create_quote_button_click(self, **event_args):
    self._create_quote()

  @handle("estimate_project_dropdown", "change")
  def estimate_project_dropdown_change(self, **event_args):
    self._load_quotes(self.estimate_project_dropdown.selected_value)
    self.quote_panel.visible = bool(self.estimate_project_dropdown.selected_value)

  @handle("quote_rows", "x-quote-status")
  def quote_rows_quote_status(self, quote_id, status, **event_args):
    result = anvil.server.call("update_quote_status", quote_id, status)
    self.quote_message.text = result["message"]
    if result["ok"]:
      self._load_quotes(self.estimate_project_dropdown.selected_value)

  @handle("service_project_dropdown", "change")
  def service_project_dropdown_change(self, **event_args):
    self._load_service_systems()

  @handle("service_project_search_button", "click")
  def service_project_search_button_click(self, **event_args):
    self._load_service_projects(self.service_project_search_box.text or "")

  @handle("search_service_products_button", "click")
  def search_service_products_button_click(self, **event_args):
    self._load_products()

  @handle("save_service_button", "click")
  def save_service_button_click(self, **event_args):
    self._save_service()
