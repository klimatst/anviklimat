from ._anvil_designer import ProjectsTemplate
from anvil import handle
import anvil.server
import anvil.users
import json
from .. import Access


class Projects(ProjectsTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_user_form():
      return
    context = Access.get_session_context()
    self.compatibility_button.visible = (
      context["role_code"] == "admin" or "catalog.manage" in context["permissions"]
    )
    self._project_id = None
    self._room_id = None
    self._cursor_stack = []
    self._current_cursor = None
    self._next_cursor = None
    self.project_editor.visible = False
    self.project_calculation_button.visible = False
    self.rooms_panel.visible = False
    self.room_editor.visible = False
    self.save_project_button.enabled = True
    self.save_room_button.enabled = True
    self._load_page()

  def _load_page(self, cursor=None):
    self._current_cursor = cursor
    result = anvil.server.call(
      "get_projects_page", self.project_search_box.text or "", cursor
    )
    if not result["ok"]:
      self.project_rows.items = []
      self.next_button.visible = False
      self.projects_message.text = result["message"]
      return
    self.project_rows.items = result["rows"]
    self._next_cursor = result["next_cursor"]
    self.next_button.visible = result["has_more"]
    self.previous_button.visible = bool(self._cursor_stack)
    self.projects_message.text = "Проектов на странице: {}".format(len(result["rows"]))
    if not self.project_type_dropdown.items:
      self.project_type_dropdown.items = result["object_types"]
      self.project_status_dropdown.items = result["statuses"]
      self.system_type_dropdown.items = result["system_types"]

  def _start_project(self):
    self._project_id = None
    self._room_id = None
    self.project_editor.visible = True
    self.rooms_panel.visible = False
    self.systems_panel.visible = False
    self.room_editor.visible = False
    self.project_code_label.text = "Новый проект"
    self.project_title_box.text = ""
    self.object_name_box.text = ""
    self.object_address_box.text = ""
    self.object_parameters_box.text = "{}"
    self.project_calculation_button.visible = False
    self.project_type_dropdown.selected_value = "other"
    self.project_status_dropdown.selected_value = "draft"
    self.project_message.text = ""

  def _open_project(self, project_id):
    result = anvil.server.call("get_project_workspace", project_id)
    if not result["ok"]:
      self.projects_message.text = result["message"]
      return
    project = result["project"]
    self._project_id = project["id"]
    self._room_id = None
    self.project_editor.visible = True
    self.project_calculation_button.visible = True
    self.rooms_panel.visible = True
    self.systems_panel.visible = True
    self.room_editor.visible = False
    self.project_code_label.text = project["code"]
    self.project_title_box.text = project["title"]
    self.object_name_box.text = project["object_name"]
    self.object_address_box.text = project["address"]
    self.object_parameters_box.text = json.dumps(
      project["object_parameters"], ensure_ascii=False, indent=2
    )
    self.project_type_dropdown.items = result["object_types"]
    self.project_type_dropdown.selected_value = project["object_type"]
    self.project_status_dropdown.items = result["statuses"]
    self.project_status_dropdown.selected_value = project["status"]
    self.room_rows.items = result["rooms"]
    self.system_rows.items = result["systems"]
    self.project_message.text = ""
    self.room_message.text = "Помещений: {}".format(len(result["rooms"]))

  def _save_project(self):
    self.save_project_button.enabled = False
    try:
      result = anvil.server.call(
        "save_project",
        {
          "title": self.project_title_box.text or "",
          "object_name": self.object_name_box.text or "",
          "object_type": self.project_type_dropdown.selected_value,
          "address": self.object_address_box.text or "",
          "object_parameters": self.object_parameters_box.text or "{}",
          "status": self.project_status_dropdown.selected_value
        },
        self._project_id
      )
    except Exception as exc:
      self.project_message.text = "Не удалось сохранить проект: {}".format(exc)
      return
    finally:
      self.save_project_button.enabled = True
    self.project_message.text = result["message"]
    if result["ok"]:
      self._project_id = result["project_id"]
      self._open_project(self._project_id)
      self._cursor_stack = []
      self._load_page()

  def _start_room(self):
    self._room_id = None
    self.room_editor.visible = True
    self.room_name_box.text = ""
    self.room_area_box.text = ""
    self.room_height_box.text = ""
    self.room_parameters_box.text = "{}"
    self.room_message.text = ""

  def _edit_room(self, room_id, name, area, height, parameters):
    self._room_id = room_id
    self.room_editor.visible = True
    self.room_name_box.text = name
    self.room_area_box.text = str(area)
    self.room_height_box.text = str(height or "")
    self.room_parameters_box.text = json.dumps(
      parameters or {}, ensure_ascii=False, indent=2
    )

  def _save_room(self):
    self.save_room_button.enabled = False
    try:
      result = anvil.server.call(
        "save_room",
        self._project_id,
        {
          "name": self.room_name_box.text or "",
          "area": self.room_area_box.text or "",
          "height": self.room_height_box.text or "",
          "parameters": self.room_parameters_box.text or "{}"
        },
        self._room_id
      )
    except Exception as exc:
      self.room_message.text = "Не удалось сохранить помещение: {}".format(exc)
      return
    finally:
      self.save_room_button.enabled = True
    self.room_message.text = result["message"]
    if result["ok"]:
      self._open_project(self._project_id)

  def _create_system(self):
    result = anvil.server.call(
      "create_system_for_project",
      self._project_id,
      self.system_type_dropdown.selected_value,
      self.system_title_box.text or ""
    )
    self.system_message.text = result["message"]
    if result["ok"]:
      self._open_project(self._project_id)
      Access.open_window("Constructor", system_id=result["system_id"])

  @handle("project_calculation_button", "click")
  def project_calculation_button_click(self, **event_args):
    if self._project_id:
      Access.open_window("Calculations", project_id=self._project_id)


  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("catalog_button", "click")
  def catalog_button_click(self, **event_args):
    Access.open_window("Catalog")

  @handle("calculations_button", "click")
  def calculations_button_click(self, **event_args):
    Access.open_window("Calculations")

  @handle("compatibility_button", "click")
  def compatibility_button_click(self, **event_args):
    Access.open_window("Compatibility")

  @handle("new_project_button", "click")
  def new_project_button_click(self, **event_args):
    self._start_project()

  @handle("project_search_button", "click")
  def project_search_button_click(self, **event_args):
    self._cursor_stack = []
    self._load_page()

  @handle("project_rows", "x-project-open")
  def project_rows_project_open(self, project_id, **event_args):
    self._open_project(project_id)

  @handle("save_project_button", "click")
  def save_project_button_click(self, **event_args):
    self._save_project()

  @handle("cancel_project_button", "click")
  def cancel_project_button_click(self, **event_args):
    self.project_editor.visible = False
    self.rooms_panel.visible = False

  @handle("add_room_button", "click")
  def add_room_button_click(self, **event_args):
    self._start_room()

  @handle("save_room_button", "click")
  def save_room_button_click(self, **event_args):
    self._save_room()

  @handle("cancel_room_button", "click")
  def cancel_room_button_click(self, **event_args):
    self.room_editor.visible = False

  @handle("room_rows", "x-room-edit")
  def room_rows_room_edit(self, room_id, name, area, height, parameters, **event_args):
    self._edit_room(room_id, name, area, height, parameters)

  @handle("room_rows", "x-room-changed")
  def room_rows_room_changed(self, **event_args):
    self._open_project(self._project_id)

  @handle("create_system_button", "click")
  def create_system_button_click(self, **event_args):
    self._create_system()

  @handle("next_button", "click")
  def next_button_click(self, **event_args):
    if self._next_cursor is None:
      return
    self._cursor_stack.append(self._current_cursor)
    self._load_page(self._next_cursor)

  @handle("previous_button", "click")
  def previous_button_click(self, **event_args):
    if not self._cursor_stack:
      return
    cursor = self._cursor_stack.pop()
    self._load_page(cursor)
