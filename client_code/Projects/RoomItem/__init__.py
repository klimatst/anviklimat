from ._anvil_designer import RoomItemTemplate
from anvil import handle
import anvil.server


class RoomItem(RoomItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)

  @handle("edit_button", "click")
  def edit_button_click(self, **event_args):
    self.parent.raise_event(
      "x-room-edit",
      room_id=self.item["id"],
      name=self.item["name"],
      area=self.item["area"],
      height=self.item["height"],
      parameters=self.item["parameters"]
    )

  @handle("delete_button", "click")
  def delete_button_click(self, **event_args):
    result = anvil.server.call(
      "delete_room", self.item["project_id"], self.item["id"]
    )
    self.room_status.text = result["message"]
    if result["ok"]:
      self.parent.raise_event("x-room-changed")
