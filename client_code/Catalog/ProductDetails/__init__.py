from ._anvil_designer import ProductDetailsTemplate
from anvil import handle
import anvil.server


class ProductDetails(ProductDetailsTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.product_content.visible = False
    self.status_label.text = ""
    self.order_quantity_box.text = "1"
    self.order_message.text = ""
    self._product_id = None
    self.gallery_rows.visible = False

  def _price_text(self, value, currency):
    if value is None or value == "":
      return "Не указана"
    return "{} {}".format("{:,.2f}".format(value).replace(",", " ").replace(".", ","), currency)

  def load_product(self, product_id):
    self._product_id = product_id
    self.product_content.visible = False
    self.status_label.text = "Загрузка карточки товара…"
    self.order_message.text = ""
    result = anvil.server.call("get_product_card", product_id)
    if not result["ok"]:
      self.status_label.text = result["message"]
      return

    data = result["data"]
    gallery = result.get("gallery", [])
    self.gallery_rows.items = gallery
    self.gallery_rows.visible = len(gallery) > 1
    self.product_title.text = "{} {}".format(
      data.get("brand", ""), data.get("model", "")
    ).strip()
    self.product_type.text = data.get("type") or data.get("category") or "Оборудование"
    self.product_image.source = data.get("image_url") or ""
    self.product_image.visible = bool(data.get("image_url"))
    self.image_placeholder.visible = not self.product_image.visible
    self.product_image.alt_text = data.get("image_alt") or self.product_title.text
    self.image_caption.text = (
      "Фотография модели" if data.get("image_is_product") else "Фото модели отсутствует"
    )
    self.product_sku.text = "Артикул: {}".format(data.get("sku") or "не указан")
    category = data.get("category") or "Категория не указана"
    subcategory = data.get("subcategory")
    self.product_category.text = " / ".join(
      value for value in (category, subcategory) if value
    )
    currency = data.get("currency") or "₽"
    self.product_price.text = self._price_text(data.get("sale_price"), currency)
    quantity = data.get("quantity")
    self.product_stock.text = (
      "Остаток: {}".format(quantity) if quantity is not None else "Наличие уточняйте"
    )
    self.product_updated.text = (
      "Обновлено: {}".format(data["updated_at"]) if data.get("updated_at") else ""
    )
    self.product_description.text = data.get("description") or "Описание пока не добавлено."
    self.series_summary.text = " / ".join(
      value for value in (
        data.get("series", ""), data.get("series_power_range", "")
      ) if value
    )
    self.series_summary.visible = bool(self.series_summary.text)
    self.series_description.text = data.get("series_description") or ""
    self.series_description.visible = bool(self.series_description.text)

    specs = result["specs"]
    self.product_specs.text = "\n".join(
      "{}: {} {}".format(row["key"], row["value"], row.get("unit") or "").rstrip()
      for row in specs
    ) or "Характеристики пока не добавлены."
    if result.get("has_more_specs"):
      self.product_specs.text += "\nПоказаны первые 100 характеристик."

    sources = result["sources"]
    self.product_sources.text = "\n".join(
      "{}{}{}".format(
        row.get("publisher") or "Источник",
        " · " + row["url"] if row.get("url") else "",
        " · " + row["checked_at"] if row.get("checked_at") else ""
      )
      for row in sources
    )
    self.sources_heading.visible = bool(sources)
    self.product_sources.visible = bool(sources)
    self.document_rows.items = [
      dict(row, can_delete=False)
      for row in result.get("documents", []) + result.get("series_documents", [])
    ]
    self.documents_panel.visible = bool(self.document_rows.items)

    self.admin_pricing.visible = result["is_admin"]
    if result["is_admin"]:
      self.purchase_price.text = "Закупочная: {}".format(
        self._price_text(data.get("purchase_price"), currency)
      )
      self.special_price.text = "Специальная: {}".format(
        self._price_text(data.get("special_price"), currency)
      )
      self.discount.text = "Скидка: {}".format(data.get("discount") or "не задана")
      self.markup.text = "Наценка: {}".format(data.get("markup") or "не задана")
      self.installation_price.text = "Монтаж: {}".format(
        self._price_text(data.get("installation_price"), currency)
      )
      minimum = data.get("minimum_stock")
      self.minimum_stock.text = (
        "Минимальный остаток: {}".format(minimum) if minimum is not None else ""
      )

    self.status_label.text = ""
    self.product_content.visible = True

  @handle("gallery_rows", "x-gallery-select")
  def gallery_rows_select(self, image_url, alt_text, **event_args):
    self.product_image.source = image_url or ""
    self.product_image.visible = bool(image_url)
    self.image_placeholder.visible = not bool(image_url)
    self.product_image.alt_text = alt_text or self.product_title.text
    self.image_caption.text = "Фотография модели" if image_url else "Фото модели отсутствует"

  @handle("order_button", "click")
  def order_button_click(self, **event_args):
    if not self._product_id:
      self.order_message.text = "Не удалось определить товар. Закройте карточку и откройте её снова."
      return
    self.order_button.enabled = False
    try:
      result = anvil.server.call(
        "create_catalog_order", self._product_id,
        self.order_quantity_box.text or "1",
        self.order_name_box.text or "", self.order_phone_box.text or "",
        self.order_email_box.text or "", self.order_comment_box.text or ""
      )
    finally:
      self.order_button.enabled = True
    self.order_message.text = result["message"]
    if result["ok"]:
      self.order_name_box.text = ""
      self.order_phone_box.text = ""
      self.order_email_box.text = ""
      self.order_comment_box.text = ""
      self.order_quantity_box.text = "1"

  @handle("close_button", "click")
  def close_button_click(self, **event_args):
    self.raise_event("close")
