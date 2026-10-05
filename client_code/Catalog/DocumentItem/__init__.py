from ._anvil_designer import DocumentItemTemplate
from anvil import confirm, handle
import anvil.server


class DocumentItem(DocumentItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.document_link.text = self.item.get("title") or "Документ"
    self.document_link.url = self.item.get("url") or ""
    self.document_kind.text = self.item.get("kind") or "Документ"
    self.document_delete_button.visible = bool(self.item.get("can_delete"))

  @handle("document_delete_button", "click")
  def document_delete_button_click(self, **event_args):
    if not confirm("Удалить этот документ из каталога?", title="Удалить документ"):
      return
    result = anvil.server.call("delete_catalog_document", self.item["id"])
    if result["ok"]:
      self.parent.raise_event("x-document-deleted", document_id=self.item["id"])
