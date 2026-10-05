from ._anvil_designer import FaqItemTemplate


class FaqItem(FaqItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.faq_question.text = str(self.item.get("question", ""))
    self.faq_answer.text = str(self.item.get("answer", ""))
