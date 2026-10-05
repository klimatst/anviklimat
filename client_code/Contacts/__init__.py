from ._anvil_designer import ContactsTemplate
from anvil import handle
import anvil.server


class Contacts(ContactsTemplate):
  def __init__(self, topic=None, **properties):
    super().__init__(**properties)
    details = anvil.server.call("get_public_contact_details")
    self.topic_dropdown.items = [
      ("Подобрать оборудование", "equipment"),
      ("Инженерный расчёт", "calculation"),
      ("Монтаж", "installation"),
      ("Сервис", "service"),
      ("Обслужить оборудование", "maintenance"),
      ("Отремонтировать оборудование", "repair"),
      ("Пусконаладка", "commissioning"),
      ("Провести измерения", "measurement"),
      ("Диагностика неисправности", "diagnosis"),
      ("Сервис увлажнителя", "humidification_maintenance"),
      ("Другое", "other")
    ]
    available_topics = [value for _, value in self.topic_dropdown.items]
    self.topic_dropdown.selected_value = topic if topic in available_topics else "equipment"
    self.contact_organization.text = details["organization_name"]
    self.contact_email.text = details["contact_email"] or "Не опубликован"
    self.contact_phone.text = details["contact_phone"] or "Не опубликован"
    self.contact_address.text = details["contact_address"] or "Не опубликован"

  @handle("submit_button", "click")
  def submit_button_click(self, **event_args):
    self.submit_button.enabled = False
    try:
      result = anvil.server.call("submit_public_enquiry", {
        "name": self.name_box.text or "",
        "company": self.company_box.text or "",
        "email": self.email_box.text or "",
        "phone": self.phone_box.text or "",
        "topic": self.topic_dropdown.selected_value,
        "message": self.message_box.text or ""
      })
    finally:
      self.submit_button.enabled = True
    self.form_message.text = result["message"]
    if result["ok"]:
      self.name_box.text = ""
      self.company_box.text = ""
      self.email_box.text = ""
      self.phone_box.text = ""
      self.message_box.text = ""
