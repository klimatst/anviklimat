from ._anvil_designer import Form1Template
from .. import Access
from anvil import alert, handle


class Form1(Form1Template):
  def __init__(self, **properties):
    super().__init__(**properties)
    self.category_count.text = "Оборудование HVAC"
    self.calculation_count.text = "Раздельные инженерные расчёты"
    self.news_status.text = "Новости и публикации"
    self.home_gallery_title.text = "Наши работы"
    self.home_gallery_intro.text = "Проекты по кондиционированию, вентиляции и инженерным системам."
    self.home_gallery_rows.role = [
      "gallery-grid", "gallery-grid-columns-3",
      "gallery-grid-ratio-landscape", "gallery-grid-preview"
    ]
    self.home_gallery_rows.items = []
    self.home_gallery_empty.text = "Откройте полную галерею, чтобы посмотреть реализованные проекты."
    self.home_gallery_empty.visible = True

  @handle("hero_project_button", "click")
  def hero_project_button_click(self, **event_args):
    Access.open_window("Projects")

  @handle("hero_catalog_button", "click")
  def hero_catalog_button_click(self, **event_args):
    Access.open_window("Catalog")

  @handle("catalog_all_button", "click")
  def catalog_all_button_click(self, **event_args):
    Access.open_window("Catalog")

  @handle("vrf_button", "click")
  def vrf_button_click(self, **event_args):
    Access.open_window("Catalog", category_code="vrf-vrv")

  @handle("ventilation_button", "click")
  def ventilation_button_click(self, **event_args):
    Access.open_window("Catalog", category_code="ventilation")

  @handle("conditioning_button", "click")
  def conditioning_button_click(self, **event_args):
    Access.open_window("Catalog", category_code="air-conditioning")

  @handle("calculations_popup_button", "click")
  def calculations_popup_button_click(self, **event_args):
    from ..Calculations import Calculations
    alert(
      Calculations(),
      title="Инженерные расчёты",
      large=True,
      buttons=["Закрыть"],
      role="eco-calculator-dialog"
    )

  @handle("installation_popup_button", "click")
  def installation_popup_button_click(self, **event_args):
    from ..InstallationCalculator import InstallationCalculator
    alert(
      InstallationCalculator(),
      title="Расчёт монтажа",
      large=True,
      buttons=["Закрыть"],
      role="eco-calculator-dialog"
    )

  @handle("ventilation_calculator_button", "click")
  def ventilation_calculator_button_click(self, **event_args):
    Access.open_window("VentilationCalculator")

  @handle("open_gallery_button", "click")
  def open_gallery_button_click(self, **event_args):
    Access.open_window("Gallery")
