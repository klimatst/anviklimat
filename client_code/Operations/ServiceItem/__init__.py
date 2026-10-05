from ._anvil_designer import ServiceItemTemplate
import anvil.server


class ServiceItem(ServiceItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
