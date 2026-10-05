from ._anvil_designer import CompatibilityTemplate
from anvil import handle
import anvil.server
import anvil.users
import json
from .. import Access


class Compatibility(CompatibilityTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_permission_form("catalog.manage"):
      return
    self.can_edit = Access.has_permission("catalog.manage")
    self.new_rule_button.visible = self.can_edit
    self.rule_editor.visible = False
    self._record_id = None
    self._records = []
    self._products_by_id = {}
    self._load_records()

  def _load_records(self):
    result = anvil.server.call("get_compatibility_records")
    if not result["ok"]:
      self.compatibility_message.text = result["message"]
      self.rule_rows.items = []
      return
    self._records = result["rows"]
    for row in self._records:
      row["type_title"] = dict(result["types"]).get(row["type"], row["type"])
      row["enabled_title"] = "Включено" if row["enabled"] else "Выключено"
      row["can_edit"] = self.can_edit
    self.rule_rows.items = self._records
    self.compatibility_message.text = "Правил загружено: {}".format(len(self._records))
    self.type_dropdown.items = result["types"]
    self.enabled_dropdown.items = [("Включено", True), ("Выключено", False)]

  def _search_products(self):
    result = anvil.server.call(
      "search_catalog", self.product_search_box.text or "", None, None
    )
    if not result["ok"]:
      self.compatibility_message.text = result["message"]
      return
    self._products_by_id = {row["id"]: row for row in result["rows"]}
    options = [("Выберите товар", None)] + [
      ("{} · {}".format(row["brand"], row["model"]), row["id"])
      for row in result["rows"]
    ]
    self.product_dropdown.items = options
    self.compatible_product_dropdown.items = options
    self.compatibility_message.text = "Найдено товаров: {}".format(len(result["rows"]))

  def _new_rule(self):
    self._record_id = None
    self.rule_editor.visible = True
    self.product_dropdown.selected_value = None
    self.compatible_product_dropdown.selected_value = None
    self.type_dropdown.selected_value = "compatible"
    self.rule_box.text = "{}"
    self.source_box.text = ""
    self.version_box.text = ""
    self.enabled_dropdown.selected_value = True
    self.rule_message.text = ""

  def _edit_rule(self, record_id):
    row = next((item for item in self._records if item["id"] == record_id), None)
    if row is None:
      self.rule_message.text = "Правило не найдено."
      return
    if not self.product_dropdown.items:
      self._search_products()
    self._record_id = row["id"]
    self.rule_editor.visible = True
    options = list(self.product_dropdown.items)
    known_ids = {value for label, value in options}
    for product_id, label in (
      (row["product_id"], row["product"]),
      (row["compatible_product_id"], row["compatible_product"])
    ):
      if product_id and product_id not in known_ids:
        options.append((label, product_id))
        known_ids.add(product_id)
    self.product_dropdown.items = options
    self.compatible_product_dropdown.items = options
    self.product_dropdown.selected_value = row["product_id"]
    self.compatible_product_dropdown.selected_value = row["compatible_product_id"]
    self.type_dropdown.selected_value = row["type"]
    self.rule_box.text = json.dumps(row["rule"], ensure_ascii=False, sort_keys=True)
    self.source_box.text = row["source"] or ""
    self.version_box.text = row["version"] or ""
    self.enabled_dropdown.selected_value = row["enabled"]
    self.rule_message.text = ""

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("projects_button", "click")
  def projects_button_click(self, **event_args):
    Access.open_window("Projects")

  @handle("operations_button", "click")
  def operations_button_click(self, **event_args):
    Access.open_window("Operations")

  @handle("new_rule_button", "click")
  def new_rule_button_click(self, **event_args):
    if not self.product_dropdown.items:
      self._search_products()
    self._new_rule()

  @handle("product_search_button", "click")
  def product_search_button_click(self, **event_args):
    self._search_products()

  @handle("rule_rows", "x-compatibility-edit")
  def rule_rows_compatibility_edit(self, record_id, **event_args):
    self._edit_rule(record_id)

  @handle("save_rule_button", "click")
  def save_rule_button_click(self, **event_args):
    result = anvil.server.call(
      "save_compatibility",
      self.product_dropdown.selected_value,
      self.compatible_product_dropdown.selected_value,
      self.type_dropdown.selected_value,
      self.rule_box.text or "{}",
      self.source_box.text or "",
      self.version_box.text or "",
      self.enabled_dropdown.selected_value,
      self._record_id
    )
    self.rule_message.text = result["message"]
    if result["ok"]:
      self.rule_editor.visible = False
      self._load_records()

  @handle("cancel_rule_button", "click")
  def cancel_rule_button_click(self, **event_args):
    self.rule_editor.visible = False
