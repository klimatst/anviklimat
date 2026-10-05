from ._anvil_designer import SpecItemTemplate
from anvil import confirm, handle
import anvil.server


class SpecItem(SpecItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.key_box.text = self.item.get("key") or ""
    self.value_box.text = self.item.get("value") or ""
    self.unit_box.text = self.item.get("unit") or ""
    self.source_box.text = self.item.get("source") or ""
    self.order_box.text = str(self.item.get("sort_order") or 0)
    self.visible_checkbox.checked = bool(self.item.get("visible", True))

  @handle("save_button", "click")
  def save_button_click(self, **event_args):
    result = anvil.server.call(
      "save_product_spec", self.item["product_id"],
      self.key_box.text or "", self.value_box.text or "",
      self.unit_box.text or "", self.source_box.text or "",
      self.order_box.text or "0", self.visible_checkbox.checked,
      self.item["id"]
    )
    self.spec_status.text = result["message"]
    if result["ok"]:
      self.parent.raise_event("x-specs-changed")

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    if not confirm("Удалить строку характеристики?", title="Удалить характеристику"):
      return
    result = anvil.server.call("delete_product_spec", self.item["id"])
    self.spec_status.text = result["message"]
    if result["ok"]:
      self.parent.raise_event("x-specs-changed")
