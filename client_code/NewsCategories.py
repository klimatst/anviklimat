import anvil.server
"""Shared news categories used by the navigation, public news, and CMS editor."""


CATEGORIES = (
  {"code": "company", "title": "Новости компании", "parent": None},
  {"code": "company_events", "title": "События", "parent": "company"},
  {"code": "company_projects", "title": "Новые объекты", "parent": "company"},
  {"code": "equipment", "title": "Оборудование", "parent": None},
  {"code": "air_conditioning", "title": "Кондиционеры", "parent": "equipment"},
  {"code": "vrf_vrv", "title": "VRV / VRF", "parent": "equipment"},
  {"code": "ventilation", "title": "Вентиляция", "parent": "equipment"},
  {"code": "guides", "title": "Полезное", "parent": None},
  {"code": "selection", "title": "Подбор оборудования", "parent": "guides"},
  {"code": "operation", "title": "Эксплуатация", "parent": "guides"},
  {"code": "maintenance", "title": "Обслуживание", "parent": "guides"}
)


def build_tree(menu_mode=False):
  nodes = {
    category["code"]: {
      "id": category["code"],
      "code": category["code"],
      "title": category["title"],
      "parent_code": category["parent"],
      "children": [],
      "menu_mode": menu_mode
    }
    for category in CATEGORIES
  }
  roots = []
  for category in CATEGORIES:
    node = nodes[category["code"]]
    parent_code = category["parent"]
    if parent_code in nodes:
      nodes[parent_code]["children"].append(node)
    else:
      roots.append(node)
  for node in nodes.values():
    node["has_children"] = bool(node["children"])
    node["expand_icon"] = "›" if node["children"] else ""
  return roots


def dropdown_options():
  categories_by_code = {category["code"]: category for category in CATEGORIES}
  options = []
  for category in CATEGORIES:
    parts = [category["title"]]
    parent_code = category["parent"]
    while parent_code in categories_by_code:
      parent = categories_by_code[parent_code]
      parts.insert(0, parent["title"])
      parent_code = parent["parent"]
    options.append((" / ".join(parts), category["code"]))
  return options


def matches(selected_code, article_code):
  if not selected_code:
    return True
  current_code = article_code
  categories_by_code = {category["code"]: category for category in CATEGORIES}
  while current_code in categories_by_code:
    if current_code == selected_code:
      return True
    current_code = categories_by_code[current_code]["parent"]
  return False
