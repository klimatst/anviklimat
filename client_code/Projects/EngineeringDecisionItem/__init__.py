from ._anvil_designer import EngineeringDecisionItemTemplate

class EngineeringDecisionItem(EngineeringDecisionItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    item = self.item or {}
    self.decision_badge.text = item.get("decision_label", "Кандидат")
    self.decision_score.text = item.get("score_label", "Оценка —")
    self.decision_capacity.text = item.get("capacity_label", "Характеристики не определены")
    self.decision_status.text = item.get("readiness_label", "")
    self.decision_reasons.text = item.get("reasons_label", "")
    self.decision_warnings.text = item.get("warnings_label", "")
