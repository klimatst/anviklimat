from ._anvil_designer import SystemDiagnosticsTemplate
from anvil import handle
import anvil.server

from .. import Access


class SystemDiagnostics(SystemDiagnosticsTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_admin_form():
      return
    self.diagnostics_severity.items = [
      ("Все проблемы", "all"), ("Ошибки", "error"),
      ("Предупреждения", "warning"), ("Сведения", "info")
    ]
    self.diagnostics_severity.selected_value = "all"
    self.diagnostic_summary.items = []
    self.diagnostic_issues.items = []
    self.diagnostics_empty.visible = False
    self._load_diagnostics()

  def _load_diagnostics(self):
    result = anvil.server.call(
      "get_system_diagnostics", self.diagnostics_search.text or "",
      self.diagnostics_severity.selected_value or "all", 500
    )
    if not result["ok"]:
      self.diagnostic_summary.items = []
      self.diagnostic_issues.items = []
      self.diagnostics_status.text = result["message"]
      self.diagnostics_empty.visible = False
      return
    self.diagnostic_summary.items = [
      {"value": row["count"], "label": row["title"]}
      for row in result["summary"]
    ]
    self.diagnostic_issues.items = result["issues"]
    self.diagnostics_status.text = (
      "Показано: {} из {} · {}".format(
        len(result["issues"]), result["total"], result["message"]
      )
    )
    self.diagnostics_empty.visible = not bool(result["issues"])
    self.diagnostics_limit_note.visible = bool(result["has_more"])

  @handle("diagnostics_search_button", "click")
  def diagnostics_search_button_click(self, **event_args):
    self._load_diagnostics()

  @handle("diagnostics_search", "pressed_enter")
  def diagnostics_search_pressed_enter(self, **event_args):
    self._load_diagnostics()

  @handle("diagnostics_severity", "change")
  def diagnostics_severity_change(self, **event_args):
    self._load_diagnostics()

  @handle("diagnostics_refresh_button", "click")
  def diagnostics_refresh_button_click(self, **event_args):
    self.diagnostics_refresh_button.enabled = False
    try:
      self._load_diagnostics()
    finally:
      self.diagnostics_refresh_button.enabled = True

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
