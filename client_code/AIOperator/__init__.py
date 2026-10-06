from ._anvil_designer import AIOperatorTemplate
from anvil import handle
import anvil.server
from .. import Access


OPERATIONS = [
  ("Консультация по HVAC", "hvac_consult"),
  ("Оценка тепловой нагрузки", "load_assessment"),
  ("Подбор оборудования по каталогу", "equipment_selection"),
  ("Линейка холодильщика", "refrigerant_lines"),
  ("Анализ вентиляции", "ventilation"),
  ("Планирование монтажа", "installation"),
  ("Диагностика неисправности", "diagnose"),
  ("Анализ данных", "analyze"),
  ("Каталог · определить категорию товара", "catalog_classify"),
  ("Каталог · подготовить описание карточки", "catalog_enrich"),
  ("Каталог · проверить возможные дубли", "duplicate_review"),
  ("Каталог · сравнить характеристики моделей", "spec_compare"),
  ("Монтаж · чек-лист пусконаладки", "commissioning"),
  ("Сервис · план обслуживания", "maintenance_plan"),
  ("Энергетика · аудит потребления", "energy_audit"),
  ("Монтаж · задание бригаде", "work_order"),
  ("Смета · проверить строки и итоги", "quote_audit"),
  ("Холодильный контур · диагностика", "refrigerant_diagnosis")
]
CHAT_MODES = [("Свободный чат", "chat")] + OPERATIONS
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_VISIBLE_MESSAGES = 60
CHAT_CONTEXT_MESSAGES = 12
PROVIDER_TITLES = {
  "primary": "Основной",
  "secondary": "Резервный 1",
  "third": "Резервный 2",
  "local": "Локальный"
}


class AIOperator(AIOperatorTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    context = Access.get_session_context()
    self._is_admin = context["role_code"] == "admin"
    self._chat_messages = []
    self._pending_image = None
    self.home_button.text = "В админ-панель" if self._is_admin else "На главную"
    self.provider_settings_panel.visible = self._is_admin
    self.send_button.enabled = bool(context["email"])
    self.chat_history.items = []
    self.chat_empty_label.visible = True
    self.attachment_preview.visible = False
    if not context["email"]:
      self.ai_status.text = "Войдите в профиль, чтобы открыть AI-помощника."
      self.chat_status.text = ""
      self.question_box.enabled = False
      self.image_loader.enabled = False
      return
    self.operation_dropdown.items = CHAT_MODES
    self.operation_dropdown.selected_value = "chat"
    self._load_status()
    if self._is_admin:
      self._load_providers()

  def _load_status(self):
    try:
      result = anvil.server.call("get_ai_status")
    except anvil.server.RuntimeUnavailableError:
      self.ai_status.text = (
        "Сервер Anvil временно недоступен. Обновите страницу или повторите "
        "загрузку настроек позже."
      )
      return
    if not result["ok"]:
      self.ai_status.text = result["message"]
      return
    configured = [
      "{}: {}".format(item["title"], item["model"] or "не настроен")
      for item in result["providers"]
    ]
    self.ai_status.text = " · ".join(configured) + "\n" + result["local_note"]

  def _load_providers(self):
    self.provider_refresh_button.enabled = False
    self.provider_message.text = "Загружаю настройки моделей…"
    try:
      result = anvil.server.call("get_ai_providers")
    except anvil.server.RuntimeUnavailableError:
      self.provider_rows.items = []
      self.provider_message.text = (
        "Сервер Anvil временно недоступен, настройки не загружены. "
        "Нажмите «Повторить загрузку» после восстановления соединения."
      )
      return
    finally:
      self.provider_refresh_button.enabled = True
    if not result["ok"]:
      self.provider_message.text = result["message"]
      self.provider_rows.items = []
      return
    self.provider_rows.items = result["providers"]
    self.provider_message.text = (
      "API можно добавлять здесь: приложение сразу подключит сохранённые настройки. "
      "Ключ хранится только в закрытых серверных данных и не передаётся браузеру. "
      "Anvil Secrets остаются отдельным разделом платформы."
    )

  @handle("provider_add_button", "click")
  def provider_add_button_click(self, **event_args):
    title = (self.provider_add_name_box.text or "").strip()
    if not title:
      self.provider_message.text = "Введите название API-подключения, например OpenRouter."
      return
    self.provider_add_button.enabled = False
    try:
      result = anvil.server.call("create_ai_provider", title)
    except Exception as exc:
      self.provider_message.text = "Не удалось создать AI-провайдера: {}".format(exc)
      return
    finally:
      self.provider_add_button.enabled = True
    self.provider_message.text = result["message"]
    if result["ok"]:
      self.provider_add_name_box.text = ""
      self._load_status()
      self._load_providers()

  def _refresh_chat(self):
    if len(self._chat_messages) > MAX_VISIBLE_MESSAGES:
      self._chat_messages = self._chat_messages[-MAX_VISIBLE_MESSAGES:]
      if self._chat_messages and self._chat_messages[0]["role"] == "assistant":
        self._chat_messages.pop(0)
    self.chat_history.items = self._chat_messages
    self.chat_empty_label.visible = not self._chat_messages

  @handle("provider_refresh_button", "click")
  def provider_refresh_button_click(self, **event_args):
    self._load_status()
    self._load_providers()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    if self._is_admin:
      Access.open_admin_dashboard()
    else:
      Access.open_window("Form1")

  @handle("provider_rows", "x-ai-provider-saved")
  def provider_rows_ai_provider_saved(self, **event_args):
    self._load_status()
    self._load_providers()

  @handle("provider_rows", "x-ai-provider-deleted")
  def provider_rows_ai_provider_deleted(self, **event_args):
    self._load_status()
    self._load_providers()

  @handle("image_loader", "change")
  def image_loader_change(self, **event_args):
    image = self.image_loader.file
    if image is None:
      self._pending_image = None
      self.attachment_preview.visible = False
      self.attachment_label.text = "Фото не выбрано"
      return
    if image.content_type not in IMAGE_TYPES:
      self.image_loader.clear()
      self._pending_image = None
      self.attachment_preview.visible = False
      self.attachment_label.text = "Формат не поддерживается. Выберите JPEG, PNG или WebP."
      return
    if image.length > MAX_IMAGE_BYTES:
      self.image_loader.clear()
      self._pending_image = None
      self.attachment_preview.visible = False
      self.attachment_label.text = "Фото больше 3 МБ. Уменьшите файл и выберите его снова."
      return
    self._pending_image = image
    self.attachment_preview.source = image
    self.attachment_preview.visible = True
    self.attachment_label.text = "{} · {:.1f} МБ".format(
      image.name or "Фото", image.length / (1024 * 1024)
    )

  @handle("remove_attachment_button", "click")
  def remove_attachment_button_click(self, **event_args):
    self.image_loader.clear()
    self._pending_image = None
    self.attachment_preview.visible = False
    self.attachment_label.text = "Фото не выбрано"

  @handle("new_chat_button", "click")
  def new_chat_button_click(self, **event_args):
    self._chat_messages = []
    self._refresh_chat()
    self.chat_status.text = "Новый диалог готов."
    self.question_box.text = ""
    self.image_loader.clear()
    self._pending_image = None
    self.attachment_preview.visible = False
    self.attachment_label.text = "Фото не выбрано"

  @handle("send_button", "click")
  def send_button_click(self, **event_args):
    question = (self.question_box.text or "").strip()
    image = self._pending_image
    if not question and image is None:
      self.chat_status.text = "Напишите сообщение или прикрепите фото."
      return

    self._chat_messages.append({
      "role": "user",
      "speaker": "Вы",
      "text": question,
      "image": image,
      "provider": "",
      "tokens": 0
    })
    self.question_box.text = ""
    self.image_loader.clear()
    self._pending_image = None
    self.attachment_preview.visible = False
    self.attachment_label.text = "Фото не выбрано"
    self._refresh_chat()

    history = []
    for message in self._chat_messages[-CHAT_CONTEXT_MESSAGES:]:
      history.append({
        "role": message["role"],
        "content": message["text"],
        "image": message.get("image")
      })
    while history and history[0]["role"] != "user":
      history.pop(0)

    self.send_button.enabled = False
    self.question_box.enabled = False
    self.image_loader.enabled = False
    self.chat_status.text = "ИИ анализирует сообщение…"
    try:
      result = anvil.server.call(
        "ai_chat", history, self.operation_dropdown.selected_value
      )
    except anvil.server.RuntimeUnavailableError:
      result = {
        "ok": False,
        "message": "Сервер Anvil временно недоступен. Сообщение осталось в истории; попробуйте отправить его ещё раз позже."
      }
    finally:
      self.send_button.enabled = True
      self.question_box.enabled = True
      self.image_loader.enabled = True

    if not result["ok"]:
      answer = result["message"]
      if result.get("details"):
        answer += "\n" + "\n".join(result["details"])
      self._chat_messages.append({
        "role": "assistant",
        "speaker": "Система",
        "text": answer,
        "image": None,
        "provider": "",
        "tokens": 0
      })
      self.chat_status.text = "Запрос не выполнен."
    else:
      self._chat_messages.append({
        "role": "assistant",
        "speaker": "ЭКО ИИ",
        "text": result["text"],
        "image": None,
        "provider": result["provider"],
        "tokens": result["tokens"]
      })
      provider = PROVIDER_TITLES.get(result["provider"], result["provider"])
      self.chat_status.text = "Ответил {} · {} токенов".format(
        provider, result["tokens"]
      )
    self._refresh_chat()
