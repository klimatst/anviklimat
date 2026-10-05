from ._anvil_designer import ProcessItemTemplate


class ProcessItem(ProcessItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    item = self.item
    order = item.get("order", 0)
    self.process_number.text = "{:02d}".format(order) if isinstance(order, int) else ""
    self.process_title.text = str(item.get("title", ""))
    self.process_text.text = str(item.get("text", ""))
