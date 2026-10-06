from ._anvil_designer import PlanStudioTemplate


class PlanStudio(PlanStudioTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
