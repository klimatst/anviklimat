import anvil.server
from anvil.tables import app_tables


@anvil.server.callable
def get_public_home_summary():
  def count(table, **filters):
    try:
      return len(table.search(**filters))
    except Exception:
      return 0

  category_count = count(app_tables.catalog_categories, active=True)
  product_count = count(app_tables.products, active=True)
  formula_count = count(app_tables.formulas, enabled=True)

  return {
    "ok": True,
    "category_count": category_count,
    "product_count": product_count,
    "formula_count": formula_count,
    "engineering_modules": 4,
    "message": "Инженерная платформа готова к работе."
  }
