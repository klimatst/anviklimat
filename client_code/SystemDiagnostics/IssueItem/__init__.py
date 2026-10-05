from ._anvil_designer import IssueItemTemplate
from anvil import handle

from ... import Access


class IssueItem(IssueItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.issue_title.text = self.item["title"]
    self.issue_detail.text = self.item["detail"]
    self.issue_severity.text = {
      "error": "ОШИБКА", "warning": "ПРОВЕРИТЬ", "info": "СВЕДЕНИЯ"
    }.get(self.item["severity"], "ПРОВЕРИТЬ")
    self.issue_severity.role = "diagnostic-severity-" + self.item["severity"]
    self.open_target_button.text = self.item.get("action_label") or "Открыть раздел"
    self.open_target_button.visible = bool(self.item.get("target"))

  @handle("open_target_button", "click")
  def open_target_button_click(self, **event_args):
    target = self.item.get("target")
    target_id = self.item.get("target_id")
    if target == "product" and target_id:
      Access.open_admin_window("Catalog.ProductEditor", product_id=target_id)
    elif target == "category" and target_id:
      Access.open_admin_window("Catalog.Taxonomy", selected_category_id=target_id)
    elif target == "pdf_import" and target_id:
      Access.open_admin_window("ImportEngine", draft_id=target_id)
    elif target in ("import", "pdf_import"):
      Access.open_admin_window("ImportEngine")
