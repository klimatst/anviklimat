from ._anvil_designer import OrderItemTemplate
from anvil import handle


class OrderItem(OrderItemTemplate):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.product_heading.text = "{}{}".format(
      self.item.get("product_name") or "Товар",
      " · " + self.item["model"] if self.item.get("model") else ""
    )
    self.sku_label.text = "Артикул: {}".format(self.item.get("sku") or "не указан")
    category_path = " / ".join(
      value for value in (
        self.item.get("category_name"), self.item.get("subcategory_name")
      ) if value
    )
    series_name = self.item.get("series_name") or ""
    self.catalog_path_label.text = " · ".join(
      value for value in (
        "Категория: " + category_path if category_path else "",
        "Серия: " + series_name if series_name else ""
      ) if value
    ) or "Категория и серия не указаны"
    self.quantity_label.text = "Количество: {}".format(self.item.get("quantity", 1))
    price = self.item.get("unit_price")
    self.price_label.text = (
      "Цена за единицу: уточняется" if price is None or not self.item.get("price_known") else
      "Цена за единицу: {:,.2f} {}".format(
        price, self.item.get("currency") or "RUB"
      ).replace(",", " ").replace(".", ",")
    )
    self.total_label.text = (
      "Сумма: уточняется" if price is None or not self.item.get("price_known") else
      "Сумма: {:,.2f} {}".format(
        price * self.item.get("quantity", 1), self.item.get("currency") or "RUB"
      ).replace(",", " ").replace(".", ",")
    )
    self.customer_label.text = self.item.get("customer_name") or "Имя не указано"
    self.contact_label.text = " · ".join(
      value for value in (self.item.get("phone"), self.item.get("email")) if value
    ) or "Контакт не указан"
    self.comment_label.text = self.item.get("comment") or "Комментарий отсутствует"
    self.created_label.text = self.item.get("created_at") or ""
    self.status_dropdown.items = [
      ("Новый", "new"), ("В обработке", "processing"),
      ("Завершён", "completed"), ("Отменён", "cancelled")
    ]
    self.status_dropdown.selected_value = self.item.get("status") or "new"

  @handle("save_status_button", "click")
  def save_status_button_click(self, **event_args):
    self.parent.raise_event(
      "x-order-status-change", order_id=self.item["id"],
      status=self.status_dropdown.selected_value
    )
