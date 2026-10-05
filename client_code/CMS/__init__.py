from ._anvil_designer import CMSTemplate
from anvil import confirm, handle
import anvil.server
import json
from .. import Access, NewsCategories


class CMS(CMSTemplate):
  def __init__(self, selected_page_id=None, **properties):
    super().__init__(**properties)
    if not Access.require_permission_form("cms.manage"):
      return
    self._page_id = None
    self._module_id = None
    self._pages = []
    self._page_settings = {}
    self._module_content = {}
    self.news_category_dropdown.items = [
      ("Без рубрики", None)
    ] + NewsCategories.dropdown_options()
    self.module_editor_mode.items = [
      ("Визуально", "visual"), ("HTML и предпросмотр", "html"),
      ("JSON · расширенный режим", "json")
    ]
    self.module_alignment_dropdown.items = [
      ("Слева", "left"), ("По центру", "center"), ("Справа", "right")
    ]
    self.module_style_dropdown.items = [
      ("Обычный блок", "standard"), ("Акцентный", "accent"),
      ("Компактный", "compact")
    ]
    self.page_editor.visible = False
    self.module_editor.visible = False
    self.preview_panel.visible = False
    self._load_pages(selected_page_id=selected_page_id)

  def _load_pages(self, selected_page_id=None):
    result = anvil.server.call("get_cms_pages")
    if not result["ok"]:
      self.cms_message.text = result["message"]
      self.page_rows.items = []
      return
    self._pages = result["rows"]
    self.page_rows.items = self._pages
    self.cms_message.text = "Страниц: {}".format(len(self._pages))
    if selected_page_id:
      self._load_page(selected_page_id)

  def _load_page(self, page_id):
    result = anvil.server.call("get_cms_page", page_id)
    if not result["ok"]:
      self.cms_message.text = result["message"]
      return
    page = result["page"]
    self._page_id = page["id"]
    self._module_id = None
    self.page_editor.visible = True
    self.module_editor.visible = False
    self.page_title_box.text = page["title"]
    self.page_slug_box.text = page["slug"]
    self._page_settings = result["settings"] or {}
    self.news_category_dropdown.selected_value = self._page_settings.get("news_category")
    self.publish_date_box.text = self._page_settings.get("publish_date", "")
    self.excerpt_box.text = self._page_settings.get("excerpt", "")
    self.seo_title_box.text = self._page_settings.get("seo_title", "")
    self.seo_description_box.text = self._page_settings.get("seo_description", "")
    self.keywords_box.text = self._page_settings.get("keywords", "")
    self.canonical_url_box.text = self._page_settings.get("canonical_url", "")
    self.social_image_url_box.text = self._page_settings.get("social_image_url", "")
    advanced_settings = {
      key: value for key, value in self._page_settings.items()
      if key not in {
        "publish_date", "excerpt", "seo_title", "seo_description",
        "keywords", "canonical_url", "social_image_url", "news_category"
      }
    }
    self.page_settings_box.text = json.dumps(
      advanced_settings, ensure_ascii=False, sort_keys=True
    )
    self.page_status_label.text = page["status_title"]
    self.publish_button.enabled = page["status"] != "published"
    modules = result["modules"]
    for module in modules:
      content = module["content"]
      module["content_label"] = (
        content.get("title") or content.get("label") or content.get("text") or ""
      )
      module["admin_state"] = "{} · позиция {}".format(
        module["state_title"], module["position"]
      )
    self.module_rows.items = modules
    self.module_type_dropdown.items = result["module_types"]
    self.cms_message.text = "Модулей: {}".format(len(modules))

  def _new_page(self):
    self._page_id = None
    self._module_id = None
    self.page_editor.visible = True
    self.module_editor.visible = False
    self.page_title_box.text = ""
    self.page_slug_box.text = ""
    self._page_settings = {}
    self.news_category_dropdown.selected_value = None
    self.publish_date_box.text = ""
    self.excerpt_box.text = ""
    self.seo_title_box.text = ""
    self.seo_description_box.text = ""
    self.keywords_box.text = ""
    self.canonical_url_box.text = ""
    self.social_image_url_box.text = ""
    self.page_settings_box.text = "{}"
    self.page_status_label.text = "Черновик"
    self.module_rows.items = []
    self.preview_panel.visible = False

  def _new_module(self):
    if self._page_id is None:
      self.cms_message.text = "Сначала сохраните страницу."
      return
    self._module_id = None
    self._module_content = {}
    self.module_editor.visible = True
    self.module_type_dropdown.selected_value = "text"
    self.module_position_box.text = str(len(list(self.module_rows.items)) * 10)
    self.module_content_box.text = "{}"
    self.module_title_box.text = ""
    self.module_text_box.text = ""
    self.module_image_url_box.text = ""
    self.module_image_alt_box.text = ""
    self.module_link_label_box.text = ""
    self.module_url_box.text = ""
    self.module_html_box.text = ""
    self.module_alignment_dropdown.selected_value = "left"
    self.module_style_dropdown.selected_value = "standard"
    self.module_enabled_dropdown.items = [("Включён", True), ("Выключен", False)]
    self.module_enabled_dropdown.selected_value = True
    self.module_editor_mode.selected_value = "visual"
    self._set_module_editor_mode()
    self.module_message.text = ""

  def _edit_module(self, module_id):
    module = next((item for item in self.module_rows.items if item["id"] == module_id), None)
    if module is None:
      self.module_message.text = "Модуль не найден."
      return
    self._module_id = module["id"]
    self._module_content = dict(module["content"])
    self.module_editor.visible = True
    self.module_type_dropdown.selected_value = module["code"]
    self.module_position_box.text = str(module["position"])
    self.module_content_box.text = json.dumps(
      module["content"], ensure_ascii=False, sort_keys=True
    )
    content = self._module_content
    self.module_title_box.text = content.get("title") or content.get("label") or ""
    self.module_text_box.text = content.get("text") or ""
    self.module_image_url_box.text = content.get("image_url") or ""
    self.module_image_alt_box.text = content.get("image_alt") or ""
    self.module_link_label_box.text = content.get("link_label") or ""
    self.module_url_box.text = content.get("url") or ""
    self.module_html_box.text = content.get("html") or ""
    self.module_alignment_dropdown.selected_value = content.get("align", "left")
    self.module_style_dropdown.selected_value = content.get("style", "standard")
    self.module_enabled_dropdown.items = [("Включён", True), ("Выключен", False)]
    self.module_enabled_dropdown.selected_value = module["enabled"]
    self.module_editor_mode.selected_value = (
      "html" if content.get("html") or module["code"] == "html" else "visual"
    )
    self._set_module_editor_mode()
    self.module_message.text = ""

  def _set_module_editor_mode(self):
    mode = self.module_editor_mode.selected_value or "visual"
    self.module_visual_panel.visible = mode == "visual"
    self.module_html_panel.visible = mode == "html"
    self.module_json_panel.visible = mode == "json"
    self.module_html_preview.format = "html"
    self.module_html_preview.content = self.module_html_box.text or ""
    self.module_html_preview.visible = mode == "html"

  def _content_from_visual_editor(self):
    content = dict(self._module_content)
    content.pop("html", None)
    for key, value in (
      ("title", self.module_title_box.text),
      ("text", self.module_text_box.text),
      ("image_url", self.module_image_url_box.text),
      ("image_alt", self.module_image_alt_box.text),
      ("link_label", self.module_link_label_box.text),
      ("url", self.module_url_box.text)
    ):
      value = (value or "").strip()
      if value:
        content[key] = value
      else:
        content.pop(key, None)
    content["align"] = self.module_alignment_dropdown.selected_value or "left"
    content["style"] = self.module_style_dropdown.selected_value or "standard"
    return content

  def _content_for_save(self):
    mode = self.module_editor_mode.selected_value or "visual"
    if mode == "json":
      try:
        content = json.loads(self.module_content_box.text or "{}")
      except ValueError:
        self.module_message.text = "Проверьте JSON содержимого блока."
        return None
      if not isinstance(content, dict):
        self.module_message.text = "Содержимое блока должно быть JSON-объектом."
        return None
      return content
    content = self._content_from_visual_editor()
    if mode == "html":
      content["html"] = self.module_html_box.text or ""
    return content

  def _preview_page(self):
    if self._page_id is None:
      self.cms_message.text = "Сначала сохраните страницу."
      return
    result = anvil.server.call("preview_cms_page", self._page_id)
    if not result["ok"]:
      self.cms_message.text = result["message"]
      return
    preview_items = []
    for module in result["modules"]:
      content = module["content"]
      title = str(content.get("title") or content.get("label") or module["type_title"])
      body = str(content.get("text") or content.get("url") or content.get("file_id") or "")
      preview_items.append({
        "title": title, "body": body,
        "html": content.get("html", "")
      })
    self.preview_title.text = result["page"]["title"]
    settings = result.get("settings", {})
    self.preview_meta.text = " · ".join(
      value for value in (
        settings.get("seo_title", ""),
        settings.get("publish_date", ""),
        settings.get("excerpt", "")
      ) if value
    )
    self.preview_rows.items = preview_items
    self.preview_panel.visible = True

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_home()

  @handle("new_page_button", "click")
  def new_page_button_click(self, **event_args):
    self._new_page()

  @handle("page_rows", "x-page-edit")
  def page_rows_page_edit(self, page_id, **event_args):
    self._load_page(page_id)

  @handle("save_page_button", "click")
  def save_page_button_click(self, **event_args):
    try:
      settings = json.loads(self.page_settings_box.text or "{}")
    except ValueError:
      self.page_message.text = "Проверьте JSON настроек страницы."
      return
    if not isinstance(settings, dict):
      self.page_message.text = "Настройки страницы должны быть JSON-объектом."
      return
    for key, component in (
      ("publish_date", self.publish_date_box),
      ("excerpt", self.excerpt_box),
      ("seo_title", self.seo_title_box),
      ("seo_description", self.seo_description_box),
      ("keywords", self.keywords_box),
      ("canonical_url", self.canonical_url_box),
      ("social_image_url", self.social_image_url_box)
    ):
      value = (component.text or "").strip()
      if value:
        settings[key] = value
      else:
        settings.pop(key, None)
    category_code = self.news_category_dropdown.selected_value
    if category_code:
      settings["news_category"] = category_code
    else:
      settings.pop("news_category", None)
    result = anvil.server.call(
      "save_cms_page",
      self.page_title_box.text or "",
      self.page_slug_box.text or "",
      settings,
      self._page_id
    )
    self.page_message.text = result["message"]
    if result["ok"]:
      self._page_id = result["page_id"]
      self._load_pages(self._page_id)

  @handle("new_module_button", "click")
  def new_module_button_click(self, **event_args):
    self._new_module()

  @handle("module_rows", "x-module-edit")
  def module_rows_module_edit(self, module_id, **event_args):
    self._edit_module(module_id)

  @handle("module_rows", "x-module-toggle")
  def module_rows_module_toggle(self, module_id, enabled, **event_args):
    result = anvil.server.call("set_cms_module_enabled", module_id, enabled)
    self.module_message.text = result["message"]
    if result["ok"]:
      self._load_page(self._page_id)

  @handle("module_rows", "x-module-move")
  def module_rows_module_move(self, module_id, direction, **event_args):
    result = anvil.server.call(
      "reorder_cms_module", self._page_id, module_id, direction
    )
    self.module_message.text = result["message"]
    if result["ok"]:
      self._load_page(self._page_id)

  @handle("module_rows", "x-module-delete")
  def module_rows_module_delete(self, module_id, **event_args):
    if not confirm("Удалить этот блок? Страница останется черновиком до публикации."):
      return
    result = anvil.server.call("delete_cms_module", module_id)
    self.module_message.text = result["message"]
    if result["ok"]:
      self._load_page(self._page_id)

  @handle("module_editor_mode", "change")
  def module_editor_mode_change(self, **event_args):
    self._set_module_editor_mode()

  @handle("module_html_box", "change")
  def module_html_box_change(self, **event_args):
    self.module_html_preview.format = "html"
    self.module_html_preview.content = self.module_html_box.text or ""

  @handle("module_type_dropdown", "change")
  def module_type_dropdown_change(self, **event_args):
    if self.module_type_dropdown.selected_value == "html":
      self.module_editor_mode.selected_value = "html"
      self._set_module_editor_mode()

  @handle("save_module_button", "click")
  def save_module_button_click(self, **event_args):
    content = self._content_for_save()
    if content is None:
      return
    result = anvil.server.call(
      "save_cms_module",
      self._page_id,
      self.module_type_dropdown.selected_value,
      self.module_position_box.text or "",
      content,
      self.module_enabled_dropdown.selected_value,
      self._module_id
    )
    self.module_message.text = result["message"]
    if result["ok"]:
      self.module_editor.visible = False
      self._load_page(self._page_id)

  @handle("cancel_module_button", "click")
  def cancel_module_button_click(self, **event_args):
    self.module_editor.visible = False

  @handle("preview_button", "click")
  def preview_button_click(self, **event_args):
    self._preview_page()

  @handle("publish_button", "click")
  def publish_button_click(self, **event_args):
    result = anvil.server.call("publish_cms_page", self._page_id)
    self.page_message.text = result["message"]
    if result["ok"]:
      self._load_page(self._page_id)
      self._load_pages()
