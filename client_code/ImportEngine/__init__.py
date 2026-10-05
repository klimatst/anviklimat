from ._anvil_designer import ImportEngineTemplate
from anvil import BlobMedia, confirm, handle
import anvil.server
from anvil.js.window import Uint8Array, crypto
from .. import Access


MAX_XLSX_UPLOAD_BYTES = 1024 * 1024 * 1024


class ImportEngine(ImportEngineTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self._import_id = None
    self._preview_token = None
    if not Access.require_permission_form("import.manage"):
      return
    self.source_type_dropdown.items = [
      ("Файл", "upload"), ("URL feed", "url"), ("API", "api")
    ]
    self.source_type_dropdown.selected_value = "upload"
    self.format_dropdown.items = [
      ("Автоопределение", "auto"), ("CSV", "csv"),
      ("XLSX", "xlsx"), ("XML", "xml"), ("JSON", "json")
    ]
    self.format_dropdown.selected_value = "auto"
    self.continue_button.visible = False
    self.start_button.enabled = False
    self.preview_rows.items = []
    self._pdf_draft_id = None
    self._pdf_categories = []
    self._pdf_image_options = []
    self._pdf_page_count = 0
    self._xlsx_selected_file = None
    self._xlsx_upload_id = None
    self._xlsx_pause_requested = False
    self.xlsx_upload_button.enabled = False
    self.pdf_review_panel.visible = False
    self._load_pdf_drafts()
    self._load_imports()
    requested_draft_id = properties.get("draft_id")
    if isinstance(requested_draft_id, str) and requested_draft_id:
      self._open_pdf_draft(requested_draft_id)

  def _show_progress(self, result):
    if not result["ok"]:
      self.import_message.text = result["message"]
      self.continue_button.visible = False
      self._load_imports()
      return
    self._import_id = result["import_id"]
    self.progress_label.text = (
      "Обработано: {processed} из {total}; добавлено/обновлено: {imported}; "
      "пропущено: {skipped}."
    ).format(**result)
    self.import_message.text = result["message"]
    self.continue_button.visible = result["has_more"]
    self._load_imports()

  def _invalidate_preview(self):
    self._preview_token = None
    self.start_button.enabled = False
    self.preview_summary.text = "Источник или формат изменился. Проверьте предпросмотр перед импортом."

  @handle("source_type_dropdown", "change")
  def source_type_dropdown_change(self, **event_args):
    self._invalidate_preview()

  @handle("format_dropdown", "change")
  def format_dropdown_change(self, **event_args):
    self._invalidate_preview()

  @handle("source_name_box", "change")
  def source_name_box_change(self, **event_args):
    self._invalidate_preview()

  @handle("source_url_box", "change")
  def source_url_box_change(self, **event_args):
    self._invalidate_preview()

  @handle("secret_ref_box", "change")
  def secret_ref_box_change(self, **event_args):
    self._invalidate_preview()

  @handle("file_loader", "change")
  def file_loader_change(self, **event_args):
    self._invalidate_preview()

  def _load_imports(self):
    result = anvil.server.call("get_product_imports")
    self.import_rows.items = result["rows"] if result["ok"] else []

  def _load_pdf_drafts(self):
    result = anvil.server.call("get_pdf_catalog_drafts")
    self.pdf_draft_rows.items = result["rows"] if result["ok"] else []

  def _render_pdf_products(self):
    self.pdf_product_rows.items = self._pdf_products
    for row in self.pdf_product_rows.get_components():
      getattr(row, "set_categories")(self._pdf_categories)
      getattr(row, "set_media")(self._pdf_image_options)

  def _open_pdf_draft(self, draft_id):
    result = anvil.server.call("get_pdf_catalog_draft", draft_id)
    if not result["ok"]:
      self.pdf_review_message.text = result["message"]
      return
    self._pdf_draft_id = result["id"]
    self._pdf_categories = result["category_options"]
    self._pdf_image_options = result.get("image_options", [])
    defaults = {
      "brand": "", "model": "", "sku": "", "type": "",
      "series": "",
      "description": "", "category_code": "", "subcategory_code": "",
      "specs_json": "{}", "sale_price": "", "currency": "",
      "purchase_price": "", "special_price": "", "discount": "",
      "markup": "", "installation_price": "", "minimum_stock": "",
      "quantity": "", "image_url": "", "extra_image_urls": "",
      "documents_json": "[]", "source_page": None,
      "confidence": None, "evidence": ""
    }
    self._pdf_products = []
    for product in result["products"]:
      normalized = dict(defaults)
      normalized.update(product)
      self._pdf_products.append(normalized)
    source_format = result.get("format", "pdf").upper()
    self.pdf_review_heading.text = "{} · Проверка: {} · {:.1f} МБ".format(
      source_format,
      result["source_name"], (result.get("file_size", 0) or 0) / (1024.0 * 1024.0)
    )
    warnings = list(result["warnings"])
    if result.get("error"):
      warnings.insert(0, result["error"])
    self.pdf_review_warnings.text = "\n".join(warnings)
    self._pdf_page_count = result.get("page_count", 0) or 0
    self.pdf_page_dropdown.items = [
      ("Страница {}".format(number), number)
      for number in range(1, self._pdf_page_count + 1)
    ]
    if source_format == "XLSX":
      self.catalog_file_summary.text = (
        "Листов: {sheets} · строк обработано: {done}/{total} · найдено товаров: {products} · "
        "изображений: {uploaded}/{images} · без фото: {missing} · предупреждений: {warnings}."
      ).format(sheets=result.get("sheet_count", 0),
               done=result.get("row_progress", 0), total=result.get("row_count", 0),
               products=len(self._pdf_products),
               uploaded=result.get("image_uploaded", 0),
               images=result.get("image_count", 0),
               missing=sum(1 for item in self._pdf_products if not item.get("image_url")),
               warnings=len(result.get("warnings", [])))
      self.pdf_source_panel.visible = False
    else:
      self.catalog_file_summary.text = (
        "Страниц обработано: {done}/{total} · найдено товаров: {products} · "
        "ошибок страниц: {errors}."
      ).format(done=result.get("page_progress", 0), total=self._pdf_page_count,
               products=len(self._pdf_products), errors=len(result.get("failed_pages", [])))
      self.pdf_page_summary.text = (
        "Готово: {percent}% · страниц: {done}/{total} · товаров: {products} · "
        "без фото: {missing} · облачных изображений: {uploaded}/{images} · "
        "страниц с ошибкой: {errors}."
      ).format(percent=result.get("progress_percent", 0),
               done=result.get("page_progress", 0), total=self._pdf_page_count,
               products=len(self._pdf_products),
               missing=sum(1 for item in self._pdf_products if not item.get("image_url")),
               uploaded=result.get("image_uploaded", 0),
               images=result.get("image_count", 0),
               errors=len(result.get("failed_pages", [])))
      self.pdf_source_panel.visible = True
    self.unassigned_images_box.text = "\n".join(
      "Страница {} · {}".format(item.get("page", "?"), item.get("url", ""))
      for item in result.get("unassigned_images", []) if item.get("url")
    )
    self.pdf_review_panel.visible = True
    editable = result["status"] in ("pdf_draft", "xlsx_draft")
    processing = result["status"] in (
      "pdf_processing", "xlsx_processing", "xlsx_images_processing"
    )
    paused = result["status"] in ("pdf_paused", "xlsx_paused")
    self.add_pdf_product_button.visible = editable
    self.save_pdf_draft_button.visible = editable
    self.approve_pdf_draft_button.visible = editable
    transfer_ready = result.get("status") not in (
      "pdf_processing", "xlsx_uploading", "xlsx_processing", "xlsx_images_processing"
    )
    self.transfer_images_button.visible = transfer_ready and bool(
      result.get("image_count") or result.get("image_uploaded") or result.get("unassigned_images")
    )
    self.reject_pdf_draft_button.visible = editable
    self.refresh_pdf_status_button.visible = processing
    self.pause_pdf_button.visible = bool(result.get("pause_available"))
    self.resume_pdf_button.visible = bool(result.get("resume_available"))
    self.retry_pdf_button.visible = bool(result.get("retry_available")) and not paused
    self.pause_pdf_button.text = (
      "Остановить после пакета строк" if source_format == "XLSX"
      else "Остановить после страницы"
    )
    self.resume_pdf_button.text = (
      "Продолжить с сохранённой строки" if source_format == "XLSX"
      else "Продолжить с сохранённой страницы"
    )
    self.pdf_review_message.text = (
      "Загрузка XLSX остановлена на сохранённой части. Повторно выберите эту же книгу выше, чтобы продолжить без повтора переданных частей."
      if source_format == "XLSX" and result["status"] == "xlsx_uploading"
      and result.get("upload_paused") else
      "XLSX передаётся частями. Чтобы продолжить после перерыва, выберите тот же файл ещё раз."
      if source_format == "XLSX" and result["status"] == "xlsx_uploading" else
      "Обработка продолжается пакетами. Обновите статус через несколько секунд."
      if processing else
      "Импорт остановлен на контрольной точке. Его можно продолжить с сохранённой страницы или строки."
      if paused else
      "Черновик можно исправить перед утверждением."
      if editable else
      "Для повторной обработки доступен исходный файл."
      if result.get("retry_available") else
      "Эта запись уже закрыта. Товары в каталоге не изменятся."
    )
    if source_format == "PDF" and self._pdf_page_count:
      self.pdf_page_dropdown.selected_value = 1
      self._load_pdf_page(1)
    else:
      self.pdf_source_text.text = result.get("extracted_text", "")
      self.pdf_page_images.items = []
    self._render_pdf_products()

  def _load_pdf_page(self, page_number):
    if not self._pdf_draft_id or not page_number:
      return
    result = anvil.server.call(
      "get_pdf_catalog_draft_page", self._pdf_draft_id, page_number
    )
    if not result["ok"]:
      self.pdf_source_text.text = result["message"]
      self.pdf_page_images.items = []
      self.pdf_page_images_label.text = ""
      return
    self.pdf_source_text.text = result["text"] or "На странице не найден текстовый слой."
    self.pdf_page_images.items = result.get("images", [])
    self.pdf_page_images_label.text = (
      "Извлечено изображений: {}".format(len(self.pdf_page_images.items))
      if self.pdf_page_images.items else
      "На странице нет фотографий либо облачное хранилище не настроено."
    )

  def _current_pdf_products(self):
    return [getattr(row, "get_product_data")() for row in self.pdf_product_rows.get_components()]

  def _save_pdf_draft(self, action):
    if not self._pdf_draft_id:
      self.pdf_review_message.text = "Сначала откройте черновик импорта."
      return
    products = self._current_pdf_products() if action != "reject" else []
    result = anvil.server.call(
      "save_pdf_catalog_draft", self._pdf_draft_id, products, action
    )
    if not result["ok"]:
      details = result.get("errors", [])
      self.pdf_review_message.text = result["message"]
      if details:
        self.pdf_review_message.text += "\n" + "\n".join(details)
      return
    self.pdf_review_message.text = result["message"]
    self._load_pdf_drafts()
    if action in ("approve", "reject"):
      self.pdf_review_panel.visible = False
      self._pdf_draft_id = None

  @handle("parse_pdf_button", "click")
  def parse_pdf_button_click(self, **event_args):
    uploaded_files = list(self.pdf_file_loader.files or [])
    if not uploaded_files and self.pdf_file_loader.file is not None:
      uploaded_files = [self.pdf_file_loader.file]
    if not uploaded_files:
      self.pdf_intake_message.text = "Выберите PDF-файл перед обработкой."
      return
    if len(uploaded_files) > 5:
      self.pdf_intake_message.text = "За один запуск можно отправить не более пяти PDF. Остальные выберите следующим запуском."
      return
    self.parse_pdf_button.enabled = False
    started_ids = []
    messages = []
    try:
      for uploaded_file in uploaded_files:
        result = anvil.server.call("start_catalog_file_draft", uploaded_file)
        messages.append("{}: {}".format(uploaded_file.name or "Файл", result["message"]))
        if result["ok"]:
          started_ids.append(result["draft_id"])
    finally:
      self.parse_pdf_button.enabled = True
    self.pdf_intake_message.text = "\n".join(messages)
    self.pdf_file_loader.files = []
    self.pdf_file_loader.file = None
    if started_ids:
      self._load_pdf_drafts()
      self._open_pdf_draft(started_ids[-1])

  def xlsx_file_change(self, event):
    files = event.target.files
    self._xlsx_selected_file = files.item(0) if files and files.length else None
    self._xlsx_upload_id = None
    if self._xlsx_selected_file is None:
      self.xlsx_file_label.text = "Файл не выбран"
      self.xlsx_upload_progress.text = ""
      self.xlsx_upload_button.enabled = False
      return
    file_size = int(self._xlsx_selected_file.size)
    self.xlsx_file_label.text = "{} · {:.1f} МБ".format(
      self._xlsx_selected_file.name, file_size / (1024.0 * 1024.0)
    )
    self.xlsx_upload_progress.text = (
      "Файл больше 1 ГБ. Разделите его на книги до 1 ГБ."
      if file_size > MAX_XLSX_UPLOAD_BYTES else
      "Выбрана большая книга. Она будет передаваться по частям и сохраняться в черновик."
    )
    self.xlsx_upload_button.enabled = 0 < file_size <= MAX_XLSX_UPLOAD_BYTES

  def _hash_xlsx_chunk(self, browser_file, chunk_index, chunk_size, total_size):
    offset = chunk_index * chunk_size
    end = min(total_size, offset + chunk_size)
    buffer = browser_file.slice(offset, end).arrayBuffer()
    chunk_data = bytes(Uint8Array(buffer))
    digest = crypto.subtle.digest("SHA-256", chunk_data)
    return "".join("{:02x}".format(value) for value in bytes(Uint8Array(digest)))

  @handle("xlsx_upload_button", "click")
  def xlsx_upload_button_click(self, **event_args):
    browser_file = self._xlsx_selected_file
    if browser_file is None:
      self.xlsx_upload_progress.text = "Выберите книгу XLSX."
      return
    self._xlsx_pause_requested = False
    self.xlsx_upload_button.enabled = False
    self.xlsx_pause_button.visible = True
    self.xlsx_pause_button.enabled = True
    try:
      result = anvil.server.call(
        "begin_xlsx_catalog_upload", browser_file.name,
        int(browser_file.size), int(browser_file.lastModified)
      )
      self._xlsx_upload_id = result.get("upload_id")
      if not result["ok"]:
        self.xlsx_upload_progress.text = result["message"]
        return
      if result["status"] != "xlsx_uploading":
        self.xlsx_upload_progress.text = result["message"]
        self._load_pdf_drafts()
        self._open_pdf_draft(result["upload_id"])
        return
      chunk_size = int(result["chunk_size"])
      total_size = int(browser_file.size)
      total_chunks = (total_size + chunk_size - 1) // chunk_size
      start_chunk = max(0, int(result.get("next_chunk", 0) or 0))
      current_result = result
      upload_allowed = True
      if start_chunk:
        saved_hashes = []
        for chunk_index in range(start_chunk):
          if self._xlsx_pause_requested:
            paused = anvil.server.call("cancel_xlsx_catalog_upload", self._xlsx_upload_id)
            self.xlsx_upload_progress.text = paused["message"]
            self._load_pdf_drafts()
            upload_allowed = False
            break
          saved_hashes.append(self._hash_xlsx_chunk(
            browser_file, chunk_index, chunk_size, total_size
          ))
          self.xlsx_upload_progress.text = "Проверено частей: {} из {}. Данные повторно не передаются.".format(
            chunk_index + 1, start_chunk
          )
        if upload_allowed:
          verified = anvil.server.call(
            "verify_xlsx_catalog_chunks", self._xlsx_upload_id, saved_hashes
          )
          if not verified["ok"]:
            self.xlsx_upload_progress.text = verified["message"]
            upload_allowed = False
          else:
            start_chunk = int(verified.get("next_chunk", start_chunk) or 0)
            self.xlsx_upload_progress.text = verified["message"]
      if upload_allowed:
        for chunk_index in range(start_chunk, total_chunks):
          if self._xlsx_pause_requested:
            paused = anvil.server.call(
              "cancel_xlsx_catalog_upload", self._xlsx_upload_id
            )
            self.xlsx_upload_progress.text = paused["message"]
            self._load_pdf_drafts()
            current_result = None
            break
          offset = chunk_index * chunk_size
          end = min(total_size, offset + chunk_size)
          chunk_buffer = browser_file.slice(offset, end).arrayBuffer()
          chunk_data = bytes(Uint8Array(chunk_buffer))
          chunk_media = BlobMedia(
            "application/octet-stream", chunk_data,
            name="xlsx-{}-{}.part".format(self._xlsx_upload_id, chunk_index)
          )
          current_result = anvil.server.call(
            "upload_xlsx_catalog_chunk", self._xlsx_upload_id,
            chunk_index, chunk_media
          )
          if not current_result["ok"]:
            self.xlsx_upload_progress.text = current_result["message"]
            break
          uploaded_bytes = current_result.get("uploaded_bytes", end)
          percent = int(uploaded_bytes * 100 / total_size)
          self.xlsx_upload_progress.text = (
            "Передано {percent}% · {done:.1f}/{total:.1f} МБ. Части отправляются "
            "по одной; после завершения книга будет обработана пакетами строк в черновик."
          ).format(percent=percent,
                   done=uploaded_bytes / (1024.0 * 1024.0),
                   total=total_size / (1024.0 * 1024.0))
          if current_result.get("complete"):
            self.xlsx_upload_progress.text = current_result["message"]
            break
      if current_result and current_result.get("complete"):
        self._load_pdf_drafts()
        self._open_pdf_draft(self._xlsx_upload_id)
    finally:
      self.xlsx_upload_button.enabled = self._xlsx_selected_file is not None
      self.xlsx_pause_button.visible = False
      self.xlsx_pause_button.enabled = True

  @handle("xlsx_pause_button", "click")
  def xlsx_pause_button_click(self, **event_args):
    self._xlsx_pause_requested = True
    self.xlsx_pause_button.enabled = False
    self.xlsx_upload_progress.text = "Остановка после сохранения текущей части…"

  @handle("pdf_draft_rows", "x-pdf-draft-open")
  def pdf_draft_rows_pdf_draft_open(self, draft_id, **event_args):
    self._open_pdf_draft(draft_id)

  @handle("pdf_product_rows", "x-pdf-product-remove")
  def pdf_product_rows_pdf_product_remove(self, product, **event_args):
    for index, current in enumerate(self._pdf_products):
      if current is product or current == product:
        del self._pdf_products[index]
        break
    else:
      return
    self._render_pdf_products()

  @handle("add_pdf_product_button", "click")
  def add_pdf_product_button_click(self, **event_args):
    self._pdf_products = self._current_pdf_products()
    self._pdf_products.append({
      "brand": "", "model": "", "sku": "", "type": "",
      "series": "",
      "description": "", "category_code": "", "subcategory_code": "",
      "specs_json": "{}", "sale_price": "", "currency": "RUB",
      "purchase_price": "", "special_price": "", "discount": "",
      "markup": "", "installation_price": "", "minimum_stock": "",
      "quantity": "", "image_url": "", "extra_image_urls": "",
      "documents_json": "[]", "source_page": None,
      "confidence": None, "evidence": ""
    })
    self._render_pdf_products()

  @handle("save_pdf_draft_button", "click")
  def save_pdf_draft_button_click(self, **event_args):
    self._save_pdf_draft("save")

  @handle("approve_pdf_draft_button", "click")
  def approve_pdf_draft_button_click(self, **event_args):
    self._save_pdf_draft("approve")

  @handle("transfer_images_button", "click")
  def transfer_images_button_click(self, **event_args):
    if not self._pdf_draft_id:
      return
    if not confirm(
      "Все найденные HTTPS-фото этого импорта будут добавлены в галерею сайта и опубликованы. Продолжить?",
      title="Перенести фото на сайт", buttons=["Перенести", "Отмена"], role="warning"
    ):
      return
    self.transfer_images_button.enabled = False
    try:
      result = anvil.server.call("transfer_import_images_to_site", self._pdf_draft_id, True)
    finally:
      self.transfer_images_button.enabled = True
    self.pdf_review_message.text = result.get("message", "")

  @handle("reject_pdf_draft_button", "click")
  def reject_pdf_draft_button_click(self, **event_args):
    self._save_pdf_draft("reject")

  @handle("close_pdf_review_button", "click")
  def close_pdf_review_button_click(self, **event_args):
    self.pdf_review_panel.visible = False
    self._pdf_draft_id = None

  @handle("pdf_page_dropdown", "change")
  def pdf_page_dropdown_change(self, **event_args):
    self._load_pdf_page(self.pdf_page_dropdown.selected_value)

  @handle("refresh_pdf_drafts_button", "click")
  def refresh_pdf_drafts_button_click(self, **event_args):
    self._load_pdf_drafts()

  @handle("refresh_pdf_status_button", "click")
  def refresh_pdf_status_button_click(self, **event_args):
    if self._pdf_draft_id:
      self._open_pdf_draft(self._pdf_draft_id)
      self._load_pdf_drafts()

  @handle("retry_pdf_button", "click")
  def retry_pdf_button_click(self, **event_args):
    if not self._pdf_draft_id:
      return
    self.retry_pdf_button.enabled = False
    try:
      result = anvil.server.call("retry_pdf_catalog_draft", self._pdf_draft_id)
    finally:
      self.retry_pdf_button.enabled = True
    self.pdf_review_message.text = result["message"]
    if result["ok"]:
      self._open_pdf_draft(self._pdf_draft_id)
      self._load_pdf_drafts()

  @handle("pause_pdf_button", "click")
  def pause_pdf_button_click(self, **event_args):
    if not self._pdf_draft_id:
      return
    self.pause_pdf_button.enabled = False
    try:
      result = anvil.server.call("pause_pdf_catalog_draft", self._pdf_draft_id)
    finally:
      self.pause_pdf_button.enabled = True
    self.pdf_review_message.text = result["message"]
    if result["ok"]:
      self._load_pdf_drafts()

  @handle("resume_pdf_button", "click")
  def resume_pdf_button_click(self, **event_args):
    if not self._pdf_draft_id:
      return
    self.resume_pdf_button.enabled = False
    try:
      result = anvil.server.call("resume_pdf_catalog_draft", self._pdf_draft_id)
    finally:
      self.resume_pdf_button.enabled = True
    self.pdf_review_message.text = result["message"]
    if result["ok"]:
      self._open_pdf_draft(self._pdf_draft_id)
      self._load_pdf_drafts()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_context_window("Catalog")

  @handle("import_rows", "x-import-resume")
  def import_rows_import_resume(self, import_id, **event_args):
    self._import_id = import_id
    self.progress_label.text = "Выбран checkpoint. Для загрузки файла выберите тот же исходный файл."
    self.continue_button.visible = True

  @handle("start_button", "click")
  def start_button_click(self, **event_args):
    if not self._preview_token:
      self.import_message.text = "Сначала проверьте предпросмотр файла или источника."
      return
    source_type = self.source_type_dropdown.selected_value
    source_url = self.source_url_box.text or ""
    source_name = (self.source_name_box.text or "").strip()
    if not source_name:
      source_name = self.file_loader.file.name if self.file_loader.file else source_url
    self.start_button.enabled = False
    preview_token = self._preview_token
    self._preview_token = None
    try:
      result = anvil.server.call(
        "start_product_import", source_type, source_name, source_url,
        self.format_dropdown.selected_value, self.secret_ref_box.text or "",
        self.file_loader.file, preview_token
      )
    finally:
      self.start_button.enabled = False
    self._show_progress(result)

  @handle("preview_button", "click")
  def preview_button_click(self, **event_args):
    source_type = self.source_type_dropdown.selected_value
    source_url = self.source_url_box.text or ""
    source_name = (self.source_name_box.text or "").strip()
    if not source_name:
      source_name = self.file_loader.file.name if self.file_loader.file else source_url
    self.preview_button.enabled = False
    self.start_button.enabled = False
    self._preview_token = None
    try:
      result = anvil.server.call(
        "preview_product_import", source_type, source_name, source_url,
        self.format_dropdown.selected_value, self.secret_ref_box.text or "",
        self.file_loader.file
      )
    finally:
      self.preview_button.enabled = True
    self.preview_summary.text = result["message"]
    if not result["ok"]:
      self.preview_rows.items = []
      self.mapping_summary.text = ""
      return
    self._preview_token = result["preview_token"]
    self.start_button.enabled = True
    self.preview_rows.items = result["preview_rows"]
    self.mapping_summary.text = "Распознанные поля: " + ", ".join(
      "{} ← {}".format(row["field"], row["source_column"])
      for row in result["mapping"]
    )

  @handle("continue_button", "click")
  def continue_button_click(self, **event_args):
    if self._import_id is None:
      self.import_message.text = "Выберите импорт из истории или создайте новый."
      return
    self.continue_button.enabled = False
    try:
      result = anvil.server.call(
        "resume_product_import", self._import_id, self.file_loader.file
      )
    finally:
      self.continue_button.enabled = True
    self._show_progress(result)
