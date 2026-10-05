from ._anvil_designer import NewsTemplate
from .. import Access
from .. import NewsCategories
from anvil import handle
from anvil.js.window import document
import anvil.server


class News(NewsTemplate):
  def __init__(self, category_code=None, **properties):
    super().__init__(**properties)
    self._set_document_metadata()
    self._pages = []
    self.article_details_overlay.visible = False
    self.category_dropdown.items = [("Все рубрики", None)] + NewsCategories.dropdown_options()
    if any(code == category_code for _, code in self.category_dropdown.items):
      self.category_dropdown.selected_value = category_code
    result = anvil.server.call("get_published_cms_pages")
    if not result["ok"]:
      self.news_message.text = result["message"]
      self.news_cards.items = []
      return
    self._pages = result["rows"]
    self._show_pages()

  def _show_pages(self):
    pages = [
      page for page in self._pages
      if NewsCategories.matches(
        self.category_dropdown.selected_value, page.get("news_category")
      )
    ]
    category_titles = {category["code"]: category["title"] for category in NewsCategories.CATEGORIES}
    self.news_cards.items = [
      {
        "slug": page["slug"],
        "title": page["title"],
        "date": page.get("publish_date") or page.get("updated_at") or "Дата не указана",
        "excerpt": page.get("excerpt") or "Откройте материал, чтобы прочитать подробности.",
        "category": category_titles.get(page.get("news_category"), "Новости")
      }
      for page in pages
    ]
    if not pages:
      self.news_message.text = "В этой рубрике пока нет опубликованных материалов."
      self._set_document_metadata()
      return
    self.news_message.text = "Материалов в рубрике: {}".format(len(pages))

  def _open_article(self, slug):
    result = anvil.server.call("get_published_cms_page", slug)
    if not result["ok"]:
      self.news_message.text = result["message"]
      self._set_document_metadata()
      return

    page = result["page"]
    article = result.get("article", {})
    sections = []
    for module in result["modules"]:
      content = module["content"] or {}
      title = content.get("title") or content.get("label") or module["type_title"]
      sections.append({
        "title": "" if title == page["title"] else title,
        "text": content.get("text") or content.get("url") or content.get("file_id") or "",
        "html": content.get("html") or "",
        "image_url": content.get("image_url") or "",
        "image_alt": content.get("image_alt") or ""
      })

    self._set_document_metadata(page, article)
    self.article_details_form.load_article(
      page["title"],
      article.get("publish_date") or page.get("updated_at"),
      article.get("excerpt", ""),
      sections
    )
    self.article_details_overlay.visible = True

  def _set_meta(self, selector, key_attribute, key_value, content):
    element = document.querySelector(selector)
    if element is None:
      element = document.createElement("meta")
      element.setAttribute(key_attribute, key_value)
      head = document.head
      if head is not None:
        head.appendChild(element)
    element.setAttribute("content", content or "")

  def _set_document_metadata(self, page=None, article=None):
    page = page or {}
    article = article or {}
    title = article.get("seo_title") or page.get("title") or "Новости"
    description = article.get("seo_description") or article.get("excerpt", "")
    document.title = "{} | ЭКО-Климат".format(title)
    self._set_meta('meta[name="description"]', "name", "description", description)
    self._set_meta('meta[name="keywords"]', "name", "keywords", article.get("keywords", ""))
    self._set_meta('meta[property="og:title"]', "property", "og:title", title)
    self._set_meta('meta[property="og:description"]', "property", "og:description", description)
    self._set_meta('meta[property="og:image"]', "property", "og:image", article.get("social_image_url", ""))
    canonical = document.querySelector('link[rel="canonical"]')
    canonical_url = article.get("canonical_url", "")
    if canonical is None and canonical_url:
      canonical = document.createElement("link")
      canonical.setAttribute("rel", "canonical")
      head = document.head
      if head is not None:
        head.appendChild(canonical)
    if canonical is not None:
      if canonical_url:
        canonical.setAttribute("href", canonical_url)
      else:
        canonical.removeAttribute("href")

  @handle("news_cards", "x-open-article")
  def news_cards_open_article(self, slug, **event_args):
    self._open_article(slug)

  @handle("article_details_form", "close")
  def article_details_form_close(self, **event_args):
    self.article_details_overlay.visible = False
    self._set_document_metadata()

  @handle("category_dropdown", "change")
  def category_dropdown_change(self, **event_args):
    self._show_pages()

  @handle("home_button", "click")
  def home_button_click(self, **event_args):
    Access.open_window("Form1")
