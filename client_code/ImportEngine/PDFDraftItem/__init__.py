from ._anvil_designer import PDFDraftItemTemplate
import anvil.server
from anvil import handle


class PDFDraftItem(PDFDraftItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    confidence = self.item.get("confidence")
    self.confidence_label.text = (
      "Уверенность ИИ: {:.0%}".format(confidence)
      if isinstance(confidence, (int, float)) else "Уверенность ИИ: не оценена"
    )
    self.evidence_label.text = self.item.get("evidence") or "В PDF не найден цитируемый фрагмент."
    page_number = self.item.get("source_page")
    if page_number:
      self.evidence_label.text += " · Источник: страница {}.".format(page_number)
    image_url = self.item.get("image_url") or ""
    self.product_image.source = image_url if image_url else ""
    self.product_image.visible = bool(image_url)
    self._categories = []

  def set_categories(self, categories):
    self._categories = categories
    self._categories_by_code = {item["code"]: item for item in categories}
    roots = [item for item in categories if not item.get("parent_code")]
    self.category_dropdown.items = [("Выберите раздел", None)] + [
      (item["title"], item["code"]) for item in roots
    ]
    self.category_dropdown.selected_value = self.item.get("category_code")
    self._set_subcategories(self.item.get("subcategory_code"))
    suggestion = self.item.get("category_suggestion")
    if isinstance(suggestion, dict):
      source_category = self.item.get("source_category") or self.item.get("source_subcategory")
      self.category_suggestion_label.text = "Источник: {} · возможная категория: {} · совпадение {}%{}".format(
        source_category or "не указан",
        suggestion.get("title", ""),
        int((suggestion.get("confidence") or 0) * 100),
        " · проверьте вручную" if not suggestion.get("safe_to_apply") else ""
      )
      self.apply_category_suggestion_button.visible = bool(
        suggestion.get("category_code") and suggestion.get("safe_to_apply")
      ) and not self.item.get("added_to_catalog")
    else:
      source_category = self.item.get("source_category") or self.item.get("source_subcategory")
      self.category_suggestion_label.text = (
        "Источник: {} · категория не распознана — выберите вручную.".format(source_category)
        if source_category else "Категория не распознана — выберите вручную."
      )
      self.apply_category_suggestion_button.visible = False
    alternatives = self.item.get("category_alternatives") or []
    self.category_alternatives_label.text = "Варианты: " + " · ".join(
      "{} ({}%)".format(item.get("title", ""), int((item.get("confidence") or 0) * 100))
      for item in alternatives[:3] if isinstance(item, dict) and item.get("title")
    ) if alternatives else ""
    if self.item.get("added_to_catalog"):
      self.catalog_add_status.text = "Товар уже добавлен в каталог."
      self.add_to_catalog_button.visible = False
      self.add_to_catalog_button.enabled = False
      self.remove_button.visible = False
      for component_name in (
        "brand_box", "model_box", "sku_box", "type_box", "category_dropdown",
        "subcategory_dropdown", "price_box", "purchase_price_box", "special_price_box",
        "discount_box", "markup_box", "installation_price_box", "currency_box",
        "quantity_box", "minimum_stock_box", "series_box", "description_box",
        "specs_box", "media_image_dropdown", "set_primary_image_button",
        "add_gallery_image_button", "image_url_box", "extra_images_box", "documents_box"
      ):
        getattr(self, component_name).enabled = False
    else:
      self.catalog_add_status.text = ""
      self.add_to_catalog_button.visible = bool(self.item.get("can_add_to_catalog"))
      self.add_to_catalog_button.enabled = True
      self.remove_button.visible = True
      for component_name in (
        "brand_box", "model_box", "sku_box", "type_box", "category_dropdown",
        "subcategory_dropdown", "price_box", "purchase_price_box", "special_price_box",
        "discount_box", "markup_box", "installation_price_box", "currency_box",
        "quantity_box", "minimum_stock_box", "series_box", "description_box",
        "specs_box", "media_image_dropdown", "set_primary_image_button",
        "add_gallery_image_button", "image_url_box", "extra_images_box", "documents_box"
      ):
        getattr(self, component_name).enabled = True

  def set_media(self, images):
    self.media_image_dropdown.items = [("Выберите фото из исходного файла", None)] + [
      ("Страница {} · {}".format(image.get("page"), image.get("name", "Изображение"))
       if image.get("page") else image.get("name", "Изображение"), image["url"])
      for image in images if image.get("url")
    ]
    self.media_image_dropdown.selected_value = None

  def _set_subcategories(self, selected_code=None):
    root_code = self.category_dropdown.selected_value
    descendants = set([root_code]) if root_code else set()
    options = []
    changed = True
    while changed:
      changed = False
      for item in self._categories:
        if item["code"] in descendants or item.get("parent_code") not in descendants:
          continue
        descendants.add(item["code"])
        options.append(item)
        changed = True
    self.subcategory_dropdown.items = [("Без подкатегории", None)] + [
      (item["title"], item["code"]) for item in options
    ]
    self.subcategory_dropdown.selected_value = selected_code

  def get_product_data(self):
    product = dict(self.item)
    product.update({
      "brand": self.brand_box.text or "",
      "model": self.model_box.text or "",
      "sku": self.sku_box.text or "",
      "type": self.type_box.text or "",
      "description": self.description_box.text or "",
      "category_code": self.category_dropdown.selected_value or "",
      "subcategory_code": self.subcategory_dropdown.selected_value or "",
      "sale_price": self.price_box.text or "",
      "purchase_price": self.purchase_price_box.text or "",
      "special_price": self.special_price_box.text or "",
      "discount": self.discount_box.text or "",
      "markup": self.markup_box.text or "",
      "installation_price": self.installation_price_box.text or "",
      "series": self.series_box.text or "",
      "currency": self.currency_box.text or "",
      "quantity": self.quantity_box.text or "",
      "minimum_stock": self.minimum_stock_box.text or "",
      "image_url": self.image_url_box.text or "",
      "extra_image_urls": self.extra_images_box.text or "",
      "documents_json": self.documents_box.text or "[]",
      "specs_json": self.specs_box.text or "{}"
    })
    return product

  @handle("category_dropdown", "change")
  def category_dropdown_change(self, **event_args):
    self._set_subcategories()

  @handle("apply_category_suggestion_button", "click")
  def apply_category_suggestion_button_click(self, **event_args):
    suggestion = self.item.get("category_suggestion")
    if not isinstance(suggestion, dict) or not suggestion.get("safe_to_apply"):
      return
    root_code = suggestion.get("category_code")
    if root_code not in self._categories_by_code:
      return
    root = self._categories_by_code[root_code]
    if root.get("parent_code"):
      return
    self.category_dropdown.selected_value = root_code
    self._set_subcategories(suggestion.get("subcategory_code") or None)
    self.apply_category_suggestion_button.visible = False
    self.category_suggestion_label.text = "Подсказка применена. Проверьте выбор и сохраните черновик."

  @handle("add_to_catalog_button", "click")
  def add_to_catalog_button_click(self, **event_args):
    draft_id = self.item.get("_draft_id")
    draft_item_id = self.item.get("_draft_item_id")
    if not draft_id or not draft_item_id:
      self.catalog_add_status.text = "Сначала сохраните черновик, чтобы товар получил отдельную запись."
      return
    product = self.get_product_data()
    self.add_to_catalog_button.enabled = False
    self.parent.raise_event(
      "x-pdf-product-add-to-catalog", draft_id=draft_id,
      draft_item_id=draft_item_id, position=self.item.get("_draft_position"),
      product=product
    )

  @handle("image_url_box", "change")
  def image_url_box_change(self, **event_args):
    image_url = self.image_url_box.text or ""
    self.product_image.source = image_url if image_url else ""
    self.product_image.visible = bool(image_url)

  def _selected_pdf_image_url(self):
    return self.media_image_dropdown.selected_value

  @handle("set_primary_image_button", "click")
  def set_primary_image_button_click(self, **event_args):
    image_url = self._selected_pdf_image_url()
    if not image_url:
      return
    self.image_url_box.text = image_url
    self.product_image.source = image_url
    self.product_image.visible = True

  @handle("add_gallery_image_button", "click")
  def add_gallery_image_button_click(self, **event_args):
    image_url = self._selected_pdf_image_url()
    if not image_url:
      return
    image_urls = [url.strip() for url in (self.extra_images_box.text or "").splitlines() if url.strip()]
    if image_url != (self.image_url_box.text or "").strip() and image_url not in image_urls:
      image_urls.append(image_url)
    self.extra_images_box.text = "\n".join(image_urls)

  @handle("remove_button", "click")
  def remove_button_click(self, **event_args):
    self.parent.raise_event("x-pdf-product-remove", product=self.item)
