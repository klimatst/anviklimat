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
    self.order_panel.visible = False
    self._product_id = None
    self._spec_lines = []
    self.gallery_rows.visible = False
    self._order_form_settings = {
      "enabled": True, "phone_required": True,
      "email_required": False, "comment_enabled": True
    }
    try:
      self._order_form_settings = anvil.server.call("get_catalog_order_form_settings")
    except Exception:
      pass
    self.order_phone_box.placeholder = "Телефон{}".format(
      " *" if self._order_form_settings.get("phone_required", True) else ""
    )
    self.order_email_box.placeholder = "Email{}".format(
      " *" if self._order_form_settings.get("email_required", False) else ""
    )
    self.order_comment_box.visible = self._order_form_settings.get(
      "comment_enabled", True
    ) is not False

  def _price_text(self, value, currency):
    if value is None or value == "":
      return "Цена по запросу"
    return "{} {}".format(
      "{:,.2f}".format(value).replace(",", " ").replace(".", ","),
      currency or "₽"
    )

  def _spec_value(self, specs, *keys):
    wanted = {str(key).lower() for key in keys}
    for row in specs:
      if str(row.get("key") or "").lower() in wanted:
        value = str(row.get("value") or "").strip()
        unit = str(row.get("unit") or "").strip()
        if value:
          return "{}{}".format(value, " " + unit if unit else "")
    return "—"

  def load_product(self, product_id):
    self._product_id = product_id
    self.product_content.visible = False
    self.order_panel.visible = False
    self.status_label.text = "Загрузка карточки товара…"
    self.order_message.text = ""
    try:
      result = anvil.server.call("get_product_card", product_id)
    except Exception as exc:
      self.status_label.text = "Не удалось загрузить карточку товара: {}".format(exc)
      return
    if not result.get("ok"):
      self.status_label.text = result.get("message", "Товар недоступен.")
      return

    data = result.get("data", {})
    specs = result.get("specs", [])
    gallery = result.get("gallery", [])
    self.gallery_rows.items = gallery
    self.gallery_rows.visible = len(gallery) > 1

    title = "{} {}".format(data.get("brand", ""), data.get("model", "")).strip()
    self.product_title.text = title or "Товар"
    image_url = data.get("image_url") or ""
    self.product_image.source = image_url
    self.product_image.visible = bool(image_url)
    self.image_placeholder.visible = not bool(image_url)
    self.product_image.alt_text = data.get("image_alt") or title

    self.product_sku.text = "Артикул: {}".format(data.get("sku") or "не указан")
    quantity = data.get("quantity")
    self.product_stock.text = (
      "В наличии" if quantity is not None and quantity > 0
      else "Нет в наличии" if quantity is not None
      else "Наличие уточняйте"
    )
    self.product_price.text = self._price_text(
      data.get("sale_price"), data.get("currency") or "₽"
    )
    self.product_description.text = (
      data.get("description") or "Описание пока не добавлено."
    )

    self.product_brand.text = data.get("brand") or "—"
    self.product_area.text = self._spec_value(
      specs, "Площадь помещения, м²", "Площадь помещения"
    )
    self.product_noise.text = self._spec_value(
      specs, "Уровень шума, Дб", "Уровень шума", "Шум"
    )
    self.product_compressor.text = self._spec_value(specs, "Компрессор")
    self.product_country.text = self._spec_value(specs, "Страна")
    self._spec_lines = []
    for row in specs:
      if row.get("visible") is False:
        continue
      key = str(row.get("key") or "Параметр").strip()
      value = str(row.get("value") or "—").strip()
      unit = str(row.get("unit") or "").strip()
      self._spec_lines.append("{}: {}{}".format(
        key, value, " " + unit if unit else ""
      ))
    self.product_specs.text = "\n".join(self._spec_lines[:100]) or "Характеристики пока не добавлены."
    if result.get("has_more_specs"):
      self.product_specs.text += "\nПоказаны первые 100 характеристик."

    self.document_rows.items = [
      dict(row, can_delete=False)
      for row in result.get("documents", []) + result.get("series_documents", [])
    ]
    self.documents_panel.visible = bool(self.document_rows.items)

    self.admin_pricing.visible = bool(result.get("is_admin"))
    if result.get("is_admin"):
      currency = data.get("currency") or "₽"
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
        "Минимальный остаток: {}".format(minimum)
        if minimum is not None else ""
      )

    self.status_label.text = ""
    self.product_content.visible = True

  @handle("gallery_rows", "x-gallery-select")
  def gallery_rows_select(self, image_url, alt_text, **event_args):
    self.product_image.source = image_url or ""
    self.product_image.visible = bool(image_url)
    self.image_placeholder.visible = not self.product_image.visible
    self.product_image.alt_text = alt_text or self.product_title.text

  @handle("more_specs_button", "click")
  def more_specs_button_click(self, **event_args):
    self.product_specs.visible = True
    self.more_specs_button.visible = False

  @handle("quick_order_button", "click")
  def quick_order_button_click(self, **event_args):
    self.order_panel.visible = True
    self.order_name_box.focus()

  @handle("order_button", "click")
  def order_button_click(self, **event_args):
    self.order_panel.visible = True
    self.order_name_box.focus()

  @handle("send_order_button", "click")
  def send_order_button_click(self, **event_args):
    if not self._product_id:
      self.order_message.text = "Не удалось определить товар. Откройте карточку снова."
      return
    self.send_order_button.enabled = False
    try:
      result = anvil.server.call(
        "create_catalog_order", self._product_id,
        self.order_quantity_box.text or "1",
        self.order_name_box.text or "", self.order_phone_box.text or "",
        self.order_email_box.text or "", self.order_comment_box.text or ""
      )
    except Exception as exc:
      self.order_message.text = "Не удалось отправить заявку: {}".format(exc)
      return
    finally:
      self.send_order_button.enabled = True
    self.order_message.text = result.get("message", "")
    if result.get("ok"):
      self.order_name_box.text = ""
      self.order_phone_box.text = ""
      self.order_email_box.text = ""
      self.order_comment_box.text = ""
      self.order_quantity_box.text = "1"

  @handle("compare_button", "click")
  def compare_button_click(self, **event_args):
    self.status_label.text = "Модель добавлена в сравнение в текущем просмотре."

  @handle("favorite_button", "click")
  def favorite_button_click(self, **event_args):
    self.status_label.text = "Модель отмечена как избранная в текущем просмотре."

  @handle("close_button", "click")
  def close_button_click(self, **event_args):
    self.raise_event("close")
