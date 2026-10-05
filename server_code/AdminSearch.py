import anvil.server
from anvil.tables import app_tables, order_by, query as q
import Core


RESULTS_PER_KIND = 6
MAX_QUERY_LENGTH = 100


def _can(user, permission):
  return Core._is_admin(user) or Core.has_permission(user, permission)


@anvil.server.callable(require_user=True)
def search_admin_workspace(search_text):
  """Search only records the current staff member is allowed to manage."""
  user = Core.require_staff_user()
  if not isinstance(search_text, str):
    return {"ok": False, "results": [], "message": "Введите текст для поиска."}
  term = search_text.strip()
  if len(term) < 2:
    return {"ok": True, "results": [], "message": "Введите не менее двух символов."}
  if len(term) > MAX_QUERY_LENGTH:
    return {"ok": False, "results": [], "message": "Слишком длинный поисковый запрос."}

  pattern = "%{}%".format(term)
  results = []

  def add(kind, row, title, detail):
    if len(results) < 30:
      results.append({
        "kind": kind, "id": row.get_id(),
        "title": str(title or "Без названия")[:160],
        "detail": str(detail or "")[:220]
      })

  if _can(user, "catalog.manage"):
    category_rows = list(app_tables.catalog_categories.search(
      q.fetch_only("title", "code", "parent", "active"),
      q.any_of(title=q.ilike(pattern), code=q.ilike(pattern)),
      order_by("sort_order")
    )[:RESULTS_PER_KIND])
    for row in category_rows:
      parent = row["parent"]
      detail = "Подкатегория" if parent is not None else "Категория"
      add("category", row, row["title"], detail)

    brand_rows = list(app_tables.brands.search(
      q.fetch_only("name"), order_by("name"), name=q.ilike(pattern)
    )[:RESULTS_PER_KIND])
    for row in brand_rows:
      add("brand", row, row["name"], "Бренд каталога")

    product_filter = q.any_of(
      model=q.ilike(pattern), sku=q.ilike(pattern),
      type=q.ilike(pattern), description=q.ilike(pattern)
    )
    product_rows = list(app_tables.products.search(
      q.fetch_only("model", "sku", "type", "brand", brand=q.fetch_only("name")),
      product_filter, order_by("identity_key")
    )[:RESULTS_PER_KIND])
    for row in product_rows:
      brand = row["brand"]
      detail = " · ".join(
        part for part in (row["sku"] or "", brand["name"] if brand else "") if part
      )
      add("product", row, row["model"] or row["type"], detail or "Карточка товара")

    order_filter = q.any_of(
      product_name=q.ilike(pattern), model=q.ilike(pattern),
      sku=q.ilike(pattern), customer_name=q.ilike(pattern),
      phone=q.ilike(pattern), email=q.ilike(pattern)
    )
    order_rows = list(app_tables.catalog_orders.search(
      q.fetch_only("product_name", "model", "sku", "status", "created_at"),
      order_filter, order_by("created_at", ascending=False)
    )[:RESULTS_PER_KIND])
    for row in order_rows:
      detail = " · ".join(
        part for part in (row["model"] or row["sku"] or "", row["status"] or "Новая заявка")
        if part
      )
      add("order", row, row["product_name"] or "Заявка каталога", detail)

  if _can(user, "cms.manage"):
    page_rows = list(app_tables.cms_pages.search(
      q.fetch_only("title", "slug", "status"),
      q.any_of(title=q.ilike(pattern), slug=q.ilike(pattern)),
      order_by("title")
    )[:RESULTS_PER_KIND])
    for row in page_rows:
      add("page", row, row["title"], "{} · /{}".format(row["status"], row["slug"]))

  if Core._is_admin(user):
    user_rows = list(app_tables.users.search(
      q.fetch_only("email"), order_by("email"), email=q.ilike(pattern)
    )[:RESULTS_PER_KIND])
    for row in user_rows:
      add("user", row, row["email"], "Учётная запись")

  return {"ok": True, "results": results, "message": "Найдено: {}".format(len(results))}
