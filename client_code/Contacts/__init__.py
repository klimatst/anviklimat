from ._anvil_designer import ContactsTemplate
from anvil import handle
import anvil.server


class Contacts(ContactsTemplate):
  def __init__(self, topic=None, **properties):
    super().__init__(**properties)
    details = anvil.server.call("get_public_contact_details")
    form_settings = details.get("form", {})
    self._email_required = form_settings.get("email_required", True) is not False
    self._phone_required = form_settings.get("phone_required", True) is not False
    self._message_enabled = form_settings.get("message_enabled", True) is not False
    self._message_limit = form_settings.get("message_limit", 1200)
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
    self.email_box.placeholder = "Электронная почта{}".format(
      " *" if self._email_required else ""
    )
    self.phone_box.placeholder = "Телефон{}".format(
      " *" if self._phone_required else ""
    )
    self.message_box.visible = self._message_enabled
    self.message_box.placeholder = "Задача, объект и условия{}".format(
      " *" if self._message_enabled else ""
    )
    phone = details.get("contact_phone") or ""
    phone_digits = "".join(character for character in phone if character.isdigit())
    prefix = "+" if phone.strip().startswith("+") else ""
    phone_link = self.dom_nodes["contact_phone_link"]
    if phone_digits:
      phone_link.setAttribute("href", "tel:{}{}".format(prefix, phone_digits))
      phone_link.textContent = "Позвонить: {}".format(phone)
      phone_link.removeAttribute("hidden")
    else:
      phone_link.setAttribute("hidden", "hidden")

  @handle("submit_button", "click")
  def submit_button_click(self, **event_args):
    if not (self.name_box.text or "").strip():
      self.form_message.text = "Укажите имя."
      return
    if self._email_required and not (self.email_box.text or "").strip():
      self.form_message.text = "Укажите электронную почту."
      return
    if self._phone_required and not (self.phone_box.text or "").strip():
      self.form_message.text = "Укажите телефон."
      return
    if not (self.email_box.text or "").strip() and not (self.phone_box.text or "").strip():
      self.form_message.text = "Укажите email или телефон для связи."
      return
    message = self.message_box.text or ""
    if self._message_enabled and not message.strip():
      self.form_message.text = "Опишите задачу."
      return
    if len(message) > self._message_limit:
      self.form_message.text = "Описание задачи превышает допустимую длину."
      return
    self.submit_button.enabled = False
    try:
      result = anvil.server.call("submit_public_enquiry", {
        "name": self.name_box.text or "",
        "company": self.company_box.text or "",
        "email": self.email_box.text or "",
        "phone": self.phone_box.text or "",
        "topic": self.topic_dropdown.selected_value,
        "message": message
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
