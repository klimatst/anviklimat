from ._anvil_designer import AdminSettingsTemplate
from anvil import confirm, handle
from anvil.js.window import document
import anvil.server

from .. import Access, AdminExtensions


WIDGET_GROUP_ROUTES = {
  "Каталог": "Catalog",
  "Медиа": "Catalog.Media",
  "Заказы": "Catalog.Orders",
  "Контент": "CMS",
  "Рабочие процессы": "Operations",
  "Проекты": "Projects",
  "Пользователи": "AdminUsers",
  "Интеграции": "AIOperator",
  "Импорт и экспорт": "ImportEngine",
  "Система": "SystemDiagnostics"
}


class AdminSettings(AdminSettingsTemplate):
  """Settings studio for the site's modules, dashboard and extensions."""

  def __init__(self, **properties):
    super().__init__(**properties)
    if not Access.require_admin_form():
      return
    self._sections = []
    self._widgets = []
    self._extensions = []
    self._saved_extensions = []
    self._draft_fields = []
    self._ai_tools = []
    self._selected_section_id = None
    self._editing_extension_id = None
    self._initial_view = properties.get("start_tab", "settings")
    self._initial_section_id = properties.get("start_section")
    self._initial_open_editor = bool(properties.get("open_editor"))
    self._load_studio()

  def _load_studio(self):
    result = anvil.server.call("get_admin_studio")
    if not result["ok"]:
      self.settings_status.text = result["message"]
      return
    self._sections = result["sections"]
    self._widgets = result["widgets"]
    groups = sorted({section["group"] for section in self._sections})
    self.settings_group_filter.items = [("Все подкатегории", "all")] + [
      (group, group) for group in groups
    ]
    self.settings_group_filter.selected_value = "all"
    self._extensions = [dict(item) for item in result["extensions"]]
    self._saved_extensions = [dict(item) for item in self._extensions]
    setting_count = sum(len(section["fields"]) for section in self._sections)
    self.section_count.text = "{} категорий · {} настроек".format(
      len(self._sections), setting_count
    )
    self.widget_count.text = "{} виджетов в библиотеке".format(len(self._widgets))
    self.extension_rows.items = self._extensions
    self._show_sections(self._sections)
    if self._sections:
      self._select_section(self._sections[0]["id"])
    self._load_integration_snapshot()
    initial_view = self._initial_view if self._initial_view in (
      "settings", "widgets", "extensions", "ai_tools"
    ) else "settings"
    if initial_view == "ai_tools":
      self._load_ai_tools()
    self._show_view(initial_view)
    if initial_view == "settings" and self._initial_section_id:
      self._select_section(self._initial_section_id)
      if self._initial_open_editor:
        self._open_settings_editor()

  def _load_integration_snapshot(self):
    try:
      result = anvil.server.call("get_admin_media_storage_status")
    except anvil.server.RuntimeUnavailableError:
      self.media_storage_status.text = "Сервер временно недоступен"
      self.media_storage_destination.text = "Не удалось загрузить маршрут фото."
      self.media_storage_credentials.text = "Обновите статус после восстановления соединения с сервером."
      return
    if result.get("ok"):
      ready = ", ".join(result.get("ready", [])) or "ни одно облако не настроено"
      self.media_storage_status.text = "{} · доступно: {}".format(
        result.get("route", "Маршрут не задан"), ready
      )
      self.media_storage_destination.text = result.get("destination", "")
      self.media_storage_credentials.text = result.get("credentials", "")
    else:
      self.media_storage_status.text = result.get("message", "Статус недоступен")
      self.media_storage_destination.text = "Маршрут фото недоступен."
      self.media_storage_credentials.text = "Проверьте доступ администратора и обновите статус."

  @handle("refresh_media_status_button", "click")
  def refresh_media_status_button_click(self, **event_args):
    self._load_integration_snapshot()

  @handle("open_media_settings_button", "click")
  def open_media_settings_button_click(self, **event_args):
    self._navigate_to_section("integrations.media.storage", open_editor=True)

  @handle("open_api_settings_button", "click")
  def open_api_settings_button_click(self, **event_args):
    self._navigate_to_section("integrations.api", open_editor=True)

  @handle("open_provider_settings_button", "click")
  def open_provider_settings_button_click(self, **event_args):
    Access.open_admin_window("AIOperator", window_title="API и модели AI")

  @handle("open_ai_settings_button", "click")
  def open_ai_settings_button_click(self, **event_args):
    self._load_ai_tools()
    self._show_view("ai_tools")

  def _show_view(self, view_name):
    self.settings_workspace.visible = view_name == "settings"
    self.widgets_workspace.visible = view_name == "widgets"
    self.extensions_workspace.visible = view_name == "extensions"
    self.ai_tools_workspace.visible = view_name == "ai_tools"
    self.settings_tab.role = "studio-tab-active" if view_name == "settings" else "studio-tab"
    self.widgets_tab.role = "studio-tab-active" if view_name == "widgets" else "studio-tab"
    self.extensions_tab.role = "studio-tab-active" if view_name == "extensions" else "studio-tab"
    self.ai_tools_tab.role = "studio-tab-active" if view_name == "ai_tools" else "studio-tab"

  def _navigate_to_section(self, section_id, open_editor=False):
    self.settings_search.text = ""
    self.settings_group_filter.selected_value = "all"
    self._refresh_settings_navigation()
    self._show_view("settings")
    self._select_section(section_id)
    if open_editor:
      self._open_settings_editor()

  def _show_sections(self, sections):
    selected_id = self._selected_section_id
    rows = []
    for section in sections:
      item = dict(section)
      item["selected"] = item["id"] == selected_id
      rows.append(item)
    self.settings_sections.items = rows

  def _select_section(self, section_id):
    section = next((item for item in self._sections if item["id"] == section_id), None)
    if section is None:
      return
    self._selected_section_id = section_id
    self.section_title.text = section["title"]
    self.section_description.text = section["description"]
    self.section_group.text = section["group"]
    self.section_summary.text = "{} параметров настройки".format(
      len(section["fields"])
    )
    self.module_enabled.checked = bool(section.get("enabled", True))
    self.settings_status.text = ""
    self._show_sections(self._filtered_sections())

  def _open_settings_editor(self):
    section = next((item for item in self._sections
                    if item["id"] == self._selected_section_id), None)
    if section is None:
      return
    self._draft_fields = [dict(field) for field in section["fields"]]
    self.editor_section_title.text = section["title"]
    self.editor_section_description.text = section["description"]
    self.settings_fields.items = self._draft_fields
    self.settings_status.text = ""
    self.settings_workspace.visible = False
    self.settings_tab.enabled = False
    self.widgets_tab.enabled = False
    self.extensions_tab.enabled = False
    self.ai_tools_tab.enabled = False
    self.settings_editor_overlay.visible = True
    self.settings_editor.visible = True

  def _discard_settings_editor(self):
    self.settings_editor.visible = False
    self.settings_editor_overlay.visible = False
    self._draft_fields = []
    self.settings_fields.items = []
    self.settings_workspace.visible = True
    self.settings_tab.enabled = True
    self.widgets_tab.enabled = True
    self.extensions_tab.enabled = True
    self.ai_tools_tab.enabled = True

  def _filtered_sections(self):
    term = str(self.settings_search.text or "").strip().lower()
    selected_group = self.settings_group_filter.selected_value or "all"
    sections = [section for section in self._sections
                if selected_group == "all" or section["group"] == selected_group]
    if not term:
      return sections
    return [section for section in self._sections
            if (selected_group == "all" or section["group"] == selected_group)
            if term in str(section.get("title") or "").lower()
            or term in str(section.get("group") or "").lower()
            or term in str(section.get("description") or "").lower()
            or any(term in str(field.get("label") or "").lower()
                   or term in str(field.get("key") or "").lower()
                   or term in str(field.get("hint") or "").lower()
                   for field in section["fields"])]

  def _filtered_widgets(self):
    term = str(self.widget_search.text or "").strip().lower()
    if not term:
      return self._widgets
    return [widget for widget in self._widgets
            if term in str(widget.get("label") or "").lower()
            or term in str(widget.get("group") or "").lower()
            or term in str(widget.get("description") or "").lower()]

  def _apply_theme_to_current_page(self, theme_code):
    Access.set_site_theme(theme_code)
    shell = document.querySelector(".eco-site-shell")
    if shell is None:
      return
    for code in ("blue", "graphite", "ice", "amber", "crimson", "violet"):
      shell.classList.remove("site-theme--" + code)
    shell.classList.add("site-theme--" + theme_code)

  @handle("settings_tab", "click")
  def settings_tab_click(self, **event_args):
    self._show_view("settings")

  @handle("widgets_tab", "click")
  def widgets_tab_click(self, **event_args):
    self.widget_rows.items = self._filtered_widgets()
    self._show_view("widgets")

  @handle("extensions_tab", "click")
  def extensions_tab_click(self, **event_args):
    self._show_view("extensions")

  @handle("ai_tools_tab", "click")
  def ai_tools_tab_click(self, **event_args):
    self._load_ai_tools()
    self._show_view("ai_tools")

  @handle("settings_search", "change")
  def settings_search_change(self, **event_args):
    self._refresh_settings_navigation()

  @handle("settings_group_filter", "change")
  def settings_group_filter_change(self, **event_args):
    self._refresh_settings_navigation()

  def _refresh_settings_navigation(self):
    sections = self._filtered_sections()
    visible_ids = {section["id"] for section in sections}
    if sections and self._selected_section_id not in visible_ids:
      self._select_section(sections[0]["id"])
    else:
      self._show_sections(sections)

  def _load_ai_tools(self):
    result = anvil.server.call("get_admin_ai_tools")
    if not result["ok"]:
      self.ai_tools_status.text = result["message"]
      return
    self._ai_tools = result["tools"]
    available_count = result.get("available_count", len(self._ai_tools))
    self.ai_tools_tab.text = "AI Studio · {} инструментов".format(available_count)
    self.ai_tools_intro.text = (
      "{} специализированных помощников по сайту, каталогу, настройкам и работе команды. "
      "Результаты остаются черновиками и требуют проверки."
    ).format(available_count)
    groups = sorted({tool["group"] for tool in self._ai_tools})
    self.ai_tool_group.items = [(group, group) for group in groups]
    if groups:
      if self.ai_tool_group.selected_value not in groups:
        self.ai_tool_group.selected_value = groups[0]
      self._show_ai_tools_for_group()
    else:
      self.ai_tool_picker.items = []
      self.ai_tool_description.text = "Все AI-инструменты отключены в настройках."

  def _show_ai_tools_for_group(self):
    group = self.ai_tool_group.selected_value
    tools = [tool for tool in self._ai_tools if tool["group"] == group]
    self.ai_tool_picker.items = [(tool["title"], tool["id"]) for tool in tools]
    if tools:
      self.ai_tool_picker.selected_value = tools[0]["id"]
      self._show_ai_tool_details()

  def _show_ai_tool_details(self):
    selected_id = self.ai_tool_picker.selected_value
    tool = next((item for item in self._ai_tools if item["id"] == selected_id), None)
    if tool is None:
      return
    self.ai_tool_description.text = tool["description"]
    self.ai_tool_input_box.placeholder = tool["input_hint"]
    self.ai_tools_status.text = (
      "Результат будет черновиком. Проверьте его перед публикацией или ответом клиенту."
    )

  @handle("ai_tool_group", "change")
  def ai_tool_group_change(self, **event_args):
    self._show_ai_tools_for_group()

  @handle("ai_tool_picker", "change")
  def ai_tool_picker_change(self, **event_args):
    self._show_ai_tool_details()

  @handle("run_ai_tool_button", "click")
  def run_ai_tool_button_click(self, **event_args):
    tool_id = self.ai_tool_picker.selected_value
    source_text = (self.ai_tool_input_box.text or "").strip()
    if not tool_id or not source_text:
      self.ai_tools_status.text = "Выберите инструмент и добавьте исходные данные."
      return
    self.run_ai_tool_button.enabled = False
    self.ai_tools_status.text = "ИИ обрабатывает текст…"
    try:
      result = anvil.server.call("run_admin_ai_tool", tool_id, source_text)
    finally:
      self.run_ai_tool_button.enabled = True
    if not result["ok"]:
      details = result.get("details", [])
      self.ai_tools_status.text = result["message"] + (
        "\n" + "\n".join(details) if details else ""
      )
      return
    self.ai_tool_output_box.text = result["answer"]
    self.ai_tools_status.text = (
      "Черновик готов · модель: {}. Проверьте факты и примените вручную."
    ).format(result.get("provider", ""))

  @handle("clear_ai_tool_button", "click")
  def clear_ai_tool_button_click(self, **event_args):
    self.ai_tool_input_box.text = ""
    self.ai_tool_output_box.text = ""
    self.ai_tools_status.text = "Поля очищены."

  @handle("edit_settings_button", "click")
  def edit_settings_button_click(self, **event_args):
    self._open_settings_editor()

  @handle("close_settings_editor_button", "click")
  def close_settings_editor_button_click(self, **event_args):
    self._discard_settings_editor()

  @handle("cancel_settings_editor_button", "click")
  def cancel_settings_editor_button_click(self, **event_args):
    self._discard_settings_editor()

  @handle("reset_settings_button", "click")
  def reset_settings_button_click(self, **event_args):
    accepted = confirm(
      "Поля этого раздела будут заполнены исходными значениями. Изменения применятся после сохранения.",
      title="Вернуть исходные значения?",
      buttons=["Продолжить", "Отмена"], role="warning"
    )
    if not accepted:
      return
    for field in self._draft_fields:
      field["value"] = field["default"]
    self.settings_fields.items = self._draft_fields
    self.settings_status.text = "Исходные значения подставлены. Сохраните раздел, чтобы применить их."

  @handle("settings_sections", "x-select-settings-section")
  def settings_sections_select(self, section_id, **event_args):
    self._select_section(section_id)

  @handle("save_section_button", "click")
  def save_section_button_click(self, **event_args):
    section = next((item for item in self._sections
                    if item["id"] == self._selected_section_id), None)
    if section is None or not self._draft_fields:
      return
    values = {
      field["key"]: field.get("value")
      for field in self._draft_fields
    }
    self.save_section_button.enabled = False
    try:
      result = anvil.server.call(
        "save_admin_studio_section", section["id"], values,
        self.module_enabled.checked
      )
    finally:
      self.save_section_button.enabled = True
    self.settings_status.text = result["message"]
    if result["ok"]:
      section["fields"] = [dict(field) for field in self._draft_fields]
      if section["id"] == "site.appearance":
        theme = values.get("site_theme", "blue")
        self._apply_theme_to_current_page(theme)
      if "extensions.allow_css" in values or "extensions.allow_javascript" in values:
        AdminExtensions.apply_saved_extensions(force=True)
      if any(key.startswith("ai_tool.") for key in values):
        self._load_ai_tools()
      section["enabled"] = self.module_enabled.checked
      self._show_sections(self._filtered_sections())

  @handle("widget_search", "change")
  def widget_search_change(self, **event_args):
    self.widget_rows.items = self._filtered_widgets()

  @handle("widget_rows", "x-open-widget")
  def widget_rows_open_widget(self, widget, **event_args):
    if not isinstance(widget, dict):
      return
    widget_id = str(widget.get("id") or "")
    title = str(widget.get("label") or "Рабочий раздел")
    if widget_id == "media_without_source":
      Access.open_admin_window(
        "AdminSettings", window_title="Фото и хранилище",
        start_section="integrations.media.storage", open_editor=True
      )
      return
    if widget_id == "settings_total":
      Access.open_admin_window(
        "AdminSettings", window_title="Центр настроек",
        start_section="system.widgets", open_editor=True
      )
      return
    target = WIDGET_GROUP_ROUTES.get(widget.get("group"), "AdminSettings")
    properties = {"window_title": title}
    if target == "Operations":
      properties["section"] = "service" if widget_id.startswith("service_") else "crm"
    Access.open_admin_window(target, **properties)

  @handle("save_widgets_button", "click")
  def save_widgets_button_click(self, **event_args):
    widget_settings = [{
      "id": item["id"], "active": bool(item.get("active")),
      "size": item.get("size", "normal")
    } for item in self._widgets]
    self.save_widgets_button.enabled = False
    try:
      result = anvil.server.call("save_admin_dashboard_widgets", widget_settings)
    finally:
      self.save_widgets_button.enabled = True
    self.widgets_status.text = result["message"]
    if result["ok"]:
      self._widgets = [dict(item) for item in self._widgets]

  @handle("default_widgets_button", "click")
  def default_widgets_button_click(self, **event_args):
    for item in self._widgets:
      item["active"] = bool(item.get("default"))
      item["size"] = "normal"
    self.widget_rows.items = self._filtered_widgets()
    self.widgets_status.text = "Базовый набор выбран. Нажмите «Сохранить виджеты»."

  @handle("new_extension_button", "click")
  def new_extension_button_click(self, **event_args):
    self._clear_extension_editor()
    self.extension_editor.visible = True

  def _clear_extension_editor(self):
    self._editing_extension_id = None
    self.extension_title_box.text = ""
    self.extension_description_box.text = ""
    self.extension_type_dropdown.items = [
      ("CSS · оформление сайта", "css"),
      ("JavaScript · логика сайта", "javascript")
    ]
    self.extension_type_dropdown.selected_value = "css"
    self.extension_code_box.text = ""
    self.extension_enabled_checkbox.checked = False
    self.extension_editor_status.text = ""
    self.extension_save_button.text = "Добавить расширение"

  @handle("extension_rows", "x-edit-extension")
  def extension_rows_edit(self, extension, **event_args):
    self._editing_extension_id = extension["id"]
    self.extension_title_box.text = extension["title"]
    self.extension_description_box.text = extension.get("description", "")
    self.extension_type_dropdown.items = [
      ("CSS · оформление сайта", "css"),
      ("JavaScript · логика сайта", "javascript")
    ]
    self.extension_type_dropdown.selected_value = extension["kind"]
    self.extension_code_box.text = extension["code"]
    self.extension_enabled_checkbox.checked = bool(extension["enabled"])
    self.extension_save_button.text = "Сохранить изменения"
    self.extension_editor.visible = True

  @handle("extension_rows", "x-delete-extension")
  def extension_rows_delete(self, extension_id, **event_args):
    extension = next((item for item in self._extensions
                      if item["id"] == extension_id), None)
    if extension is None:
      return
    accepted = confirm(
      "Расширение «{}» будет удалено из сайта.".format(extension["title"]),
      title="Удалить расширение?", buttons=["Удалить", "Отмена"],
      role="warning"
    )
    if not accepted:
      return
    updated = [dict(item) for item in self._saved_extensions
               if item["id"] != extension_id]
    self._persist_extensions(updated)

  @handle("extension_save_button", "click")
  def extension_save_button_click(self, **event_args):
    title = (self.extension_title_box.text or "").strip()
    code = self.extension_code_box.text or ""
    if not title:
      self.extension_editor_status.text = "Укажите название расширения."
      return
    if not code.strip():
      self.extension_editor_status.text = "Добавьте код CSS или JavaScript."
      return
    extension = {
      "id": self._editing_extension_id or "",
      "title": title,
      "description": (self.extension_description_box.text or "").strip(),
      "kind": self.extension_type_dropdown.selected_value or "css",
      "code": code,
      "enabled": self.extension_enabled_checkbox.checked
    }
    updated = [dict(item) for item in self._saved_extensions]
    if self._editing_extension_id:
      updated = [extension if item["id"] == self._editing_extension_id else item
                 for item in updated]
    else:
      updated.append(extension)
    self._persist_extensions(updated, close_editor=True)

  @handle("extension_cancel_button", "click")
  def extension_cancel_button_click(self, **event_args):
    self.extension_editor.visible = False
    self._clear_extension_editor()

  @handle("extension_rows", "x-extension-toggle")
  def extension_rows_toggle(self, **event_args):
    self._persist_extensions([dict(item) for item in self._extensions])

  def _persist_extensions(self, extensions=None, close_editor=False):
    candidate = extensions if extensions is not None else self._extensions
    self.extension_save_button.enabled = False
    try:
      result = anvil.server.call("save_admin_studio_extensions", candidate)
    finally:
      self.extension_save_button.enabled = True
    self.extensions_status.text = result["message"]
    self.extension_editor_status.text = result["message"]
    if not result["ok"]:
      self._extensions = [dict(item) for item in self._saved_extensions]
      self.extension_rows.items = self._extensions
      return
    self._extensions = result["extensions"]
    self._saved_extensions = [dict(item) for item in self._extensions]
    self.extension_rows.items = self._extensions
    AdminExtensions.apply_saved_extensions(force=True)
    if close_editor:
      self.extension_editor.visible = False
      self._clear_extension_editor()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_admin_dashboard()
