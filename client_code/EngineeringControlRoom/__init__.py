from ._anvil_designer import EngineeringControlRoomTemplate
from anvil import handle
import anvil.server
from .. import Access


class EngineeringControlRoom(EngineeringControlRoomTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_staff_form():
      return
    self._load()

  def _load(self):
    try:
      result = anvil.server.call("get_engineering_control_room")
    except Exception as exc:
      self.status.text = "Инженерный центр недоступен: {}".format(exc)
      return
    if not result.get("ok"):
      self.status.text = result.get("message", "Недостаточно прав.")
      return
    m = result["metrics"]
    self.projects_metric.text = "ПРОЕКТЫ\n{}".format(m["projects"])
    self.active_metric.text = "В РАБОТЕ\n{}".format(m["active_projects"])
    self.attention_metric.text = "ТРЕБУЮТ ВНИМАНИЯ\n{}".format(m["needs_attention"])
    self.systems_metric.text = "СИСТЕМЫ\n{}".format(m["systems"])
    self.calculations_metric.text = "РАСЧЁТЫ\n{}".format(m["calculations"])
    self.estimates_metric.text = "СМЕТЫ\n{}".format(m["estimates"])
    self.quality_metric.text = "QUALITY GATE\n{} · {} проблем".format("OK" if m.get("quality_gate_ok") else "ATTENTION", m.get("quality_issue_count", 0))
    self.recent_rows.items = result.get("recent_projects", [])
    self.status.text = "Система синхронизирована · Quality Gate: {} критических проблем.".format(m.get("quality_high_count", 0))

  @handle("refresh_button", "click")
  def refresh_button_click(self, **event_args):
    self._load()

  @handle("projects_button", "click")
  def projects_button_click(self, **event_args):
    Access.open_admin_window("Projects", window_title="Проекты и системы")

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
