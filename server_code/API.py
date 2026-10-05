import json
from functools import wraps

import anvil
import anvil.server
from anvil.server import HttpResponse, request, route


MAX_API_BODY = 50000
SERVICE_WORKER = """const CACHE_NAME = 'hvac-pwa-public-v1';
const PUBLIC_FILES = ['/manifest.webmanifest', '/_/theme/pwa-icon.svg'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(PUBLIC_FILES)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('hvac-pwa-') && key !== CACHE_NAME).map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method === 'GET' && url.origin === self.location.origin && PUBLIC_FILES.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
"""
PWA_MANIFEST = {
  "id": "/",
  "name": "ЭКО-КЛИМАТ",
  "short_name": "ЭКО-КЛИМАТ",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#11161a",
  "theme_color": "#c9894a",
  "icons": [{
    "src": "/_/theme/pwa-icon.svg",
    "sizes": "any",
    "type": "image/svg+xml",
    "purpose": "any maskable"
  }]
}


def _response(value, status=200):
  return HttpResponse(
    status=status,
    body=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
    headers={
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    }
  )


def _result_response(result):
  return _response(result, 200 if result.get("ok") else 400)


def _body(max_bytes=MAX_API_BODY):
  if len(request.body or b"") > max_bytes:
    max_kb = (max_bytes + 999) // 1000
    return {}, "Тело запроса превышает {} КБ.".format(max_kb)
  body = request.body_json
  if not isinstance(body, dict):
    return {}, "Передайте JSON-объект."
  return body, None


def _api_route(path, **route_options):
  """Register a versioned API route behind the admin-controlled API switch."""
  def register(handler):
    @wraps(handler)
    def guarded_handler(*args, **kwargs):
      import AdminStudio

      if AdminStudio.get_admin_studio_setting("api.enabled", True) is False:
        return _response({
          "ok": False, "message": "Внешний API временно отключён администратором."
        }, 503)
      return handler(*args, **kwargs)

    return route(path, **route_options)(guarded_handler)
  return register


@route("/manifest.webmanifest", methods=["GET"])
def pwa_manifest():
  return HttpResponse(
    status=200,
    body=json.dumps(PWA_MANIFEST, separators=(",", ":")),
    headers={
      "Content-Type": "application/manifest+json; charset=utf-8",
      "Cache-Control": "public, max-age=86400",
      "X-Content-Type-Options": "nosniff"
    }
  )


@route("/service-worker.js", methods=["GET"])
def pwa_service_worker():
  return HttpResponse(
    status=200,
    body=SERVICE_WORKER,
    headers={
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-cache",
      "Service-Worker-Allowed": "/",
      "X-Content-Type-Options": "nosniff"
    }
  )


@_api_route("/api/v1/catalog", methods=["GET"])
def api_catalog():
  import CatalogService as Catalog

  result = Catalog.search_catalog(
    request.query_params.get("search", ""),
    request.query_params.get("category_id") or None,
    request.query_params.get("cursor") or None
  )
  return _result_response(result)


@_api_route("/api/v1/catalog/categories", methods=["GET", "POST"])
def api_catalog_categories():
  import CatalogService as Catalog

  if request.method == "GET":
    return _result_response(Catalog.get_catalog_categories())
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Catalog.add_catalog_category(
    payload.get("title"), payload.get("parent_id")
  ))


@_api_route("/api/v1/catalog/product", methods=["GET", "POST", "PUT"])
def api_catalog_product():
  import CatalogService as Catalog

  if request.method == "GET":
    product_id = request.query_params.get("product_id")
    if not product_id:
      return _response({"ok": False, "message": "Укажите product_id."}, 400)
    return _result_response(Catalog.get_product_card(product_id))

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  product_id = payload.get("product_id")
  if request.method == "POST" and product_id is not None:
    return _response({"ok": False, "message": "Для создания передавайте POST без product_id."}, 400)
  if request.method == "PUT" and not product_id:
    return _response({"ok": False, "message": "Для обновления укажите product_id."}, 400)
  sections = (payload.get("product"), payload.get("prices"), payload.get("stock"), payload.get("source"))
  if not all(isinstance(value, dict) for value in sections):
    return _response({"ok": False, "message": "Передайте product, prices, stock и source как JSON-объекты."}, 400)
  return _result_response(Catalog.save_product(*sections, product_id))


@_api_route("/api/v1/catalog/prices/bulk", authenticate_users=True, methods=["POST"])
def api_catalog_bulk_prices():
  import CatalogService as Catalog

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Catalog.bulk_update_prices(
    payload.get("product_ids"), payload.get("field"),
    payload.get("value"), payload.get("mode")
  ))


@_api_route("/api/v1/catalog/specifications", authenticate_users=True, methods=["POST", "DELETE"])
def api_catalog_specifications():
  import CatalogService as Catalog

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  if request.method == "DELETE":
    return _result_response(Catalog.delete_product_spec(payload.get("spec_id")))
  return _result_response(Catalog.save_product_spec(
    payload.get("product_id"), payload.get("key"), payload.get("value"),
    payload.get("unit", ""), payload.get("source", "")
  ))


@_api_route("/api/v1/cms/page", methods=["GET"])
def api_published_cms_page():
  import CMSServer as CMS

  slug = request.query_params.get("slug")
  if not slug:
    return _response({"ok": False, "message": "Укажите адрес страницы."}, 400)
  return _result_response(CMS.get_published_cms_page(slug))


@_api_route("/api/v1/calculations", methods=["GET"])
def api_calculations():
  import CalculationsService as Calculations

  return _result_response(Calculations.get_calculation_catalog())


@_api_route("/api/v1/calculations/run", methods=["POST"])
def api_run_calculation():
  import CalculationsService as Calculations

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  if not isinstance(payload.get("inputs"), dict):
    return _response({"ok": False, "message": "Поле inputs должно быть JSON-объектом."}, 400)
  result = Calculations.run_calculation(
    payload.get("code"), payload["inputs"],
    payload.get("save_result", False), payload.get("expected_version"),
    payload.get("project_id"), payload.get("system_id")
  )
  return _result_response(result)


@_api_route("/api/v1/projects", authenticate_users=True, methods=["GET", "POST"])
def api_projects():
  import ProjectsService as Projects

  if request.method == "GET":
    result = Projects.get_projects_page(
      request.query_params.get("search", ""),
      request.query_params.get("cursor") or None
    )
    return _result_response(result)
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  project_data = payload.get("project")
  if not isinstance(project_data, dict):
    return _response({"ok": False, "message": "Поле project должно быть JSON-объектом."}, 400)
  return _result_response(Projects.save_project(project_data, payload.get("project_id")))


@_api_route("/api/v1/project", authenticate_users=True, methods=["GET"])
def api_project_workspace():
  import ProjectsService as Projects

  project_id = request.query_params.get("project_id")
  if not project_id:
    return _response({"ok": False, "message": "Укажите project_id."}, 400)
  return _result_response(Projects.get_project_workspace(project_id))


@_api_route("/api/v1/rooms", authenticate_users=True, methods=["POST", "DELETE"])
def api_project_rooms():
  import ProjectsService as Projects

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  if request.method == "DELETE":
    return _result_response(Projects.delete_room(
      payload.get("project_id"), payload.get("room_id")
    ))
  room_data = payload.get("room")
  if not isinstance(room_data, dict):
    return _response({"ok": False, "message": "Поле room должно быть JSON-объектом."}, 400)
  return _result_response(Projects.save_room(
    payload.get("project_id"), room_data, payload.get("room_id")
  ))


@_api_route("/api/v1/systems", authenticate_users=True, methods=["POST"])
def api_create_system():
  import ConstructorService as Constructor

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Constructor.create_system_for_project(
    payload.get("project_id"), payload.get("system_type"), payload.get("title")
  ))


@_api_route("/api/v1/system/graph", authenticate_users=True, methods=["GET", "POST"])
def api_system_graph():
  import ConstructorService as Constructor

  if request.method == "GET":
    system_id = request.query_params.get("system_id")
    if not system_id:
      return _response({"ok": False, "message": "Укажите system_id."}, 400)
    return _result_response(Constructor.get_system_graph(system_id))
  payload, error = _body(Constructor.MAX_GRAPH_BYTES + 64 * 1024)
  if error:
    return _response({"ok": False, "message": error}, 400)
  if not isinstance(payload.get("graph"), dict):
    return _response({"ok": False, "message": "Поле graph должно быть JSON-объектом."}, 400)
  return _result_response(Constructor.save_system_graph(
    payload.get("system_id"), payload["graph"], payload.get("expected_version")
  ))


@_api_route("/api/v1/compatibility", authenticate_users=True, methods=["GET", "POST"])
def api_compatibility():
  import Engineering

  if request.method == "GET":
    return _result_response(Engineering.get_compatibility_records(
      request.query_params.get("product_id") or None
    ))
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Engineering.save_compatibility(
    payload.get("product_id"), payload.get("compatible_product_id"),
    payload.get("compatibility_type"), payload.get("rule", {}),
    payload.get("source"), payload.get("version"),
    payload.get("enabled", True), payload.get("compatibility_id")
  ))


@_api_route("/api/v1/system/compatibility/check", authenticate_users=True, methods=["POST"])
def api_check_system_compatibility():
  import Engineering

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Engineering.validate_system_compatibility(payload.get("system_id")))


@_api_route("/api/v1/system/routing", authenticate_users=True, methods=["POST"])
def api_system_routing():
  import Engineering

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Engineering.calculate_system_routing(payload.get("system_id")))


@_api_route("/api/v1/system/bom", authenticate_users=True, methods=["GET", "POST"])
def api_system_bom():
  import Engineering

  if request.method == "GET":
    system_id = request.query_params.get("system_id")
    if not system_id:
      return _response({"ok": False, "message": "Укажите system_id."}, 400)
    return _result_response(Engineering.get_system_bom(system_id))
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Engineering.generate_system_bom(payload.get("system_id")))


@_api_route("/api/v1/crm/clients", authenticate_users=True, methods=["GET", "POST"])
def api_crm_clients():
  import OperationsService as Operations

  if request.method == "GET":
    return _result_response(Operations.get_crm_clients())
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  client_data = payload.get("client")
  contact_data = payload.get("contact", {})
  if not isinstance(client_data, dict) or not isinstance(contact_data, dict):
    return _response({"ok": False, "message": "Поля client и contact должны быть объектами."}, 400)
  return _result_response(Operations.save_crm_client(
    client_data, contact_data, payload.get("client_id")
  ))


@_api_route("/api/v1/crm/tasks", authenticate_users=True, methods=["GET", "POST"])
def api_crm_tasks():
  import OperationsService as Operations

  if request.method == "GET":
    return _result_response(Operations.get_crm_tasks())
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  task_data = payload.get("task")
  if not isinstance(task_data, dict):
    return _response({"ok": False, "message": "Поле task должно быть JSON-объектом."}, 400)
  return _result_response(Operations.save_crm_task(task_data, payload.get("task_id")))


@_api_route("/api/v1/estimates", authenticate_users=True, methods=["GET", "POST"])
def api_estimates():
  import OperationsService as Operations

  if request.method == "GET":
    project_id = request.query_params.get("project_id")
    if not project_id:
      return _response({"ok": False, "message": "Укажите project_id."}, 400)
    return _result_response(Operations.get_project_estimate(project_id))
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Operations.build_project_estimate(
    payload.get("project_id"), payload.get("labor_cost"), payload.get("consumables_cost")
  ))


@_api_route("/api/v1/quotes", authenticate_users=True, methods=["GET", "POST"])
def api_quotes():
  import OperationsService as Operations

  if request.method == "GET":
    project_id = request.query_params.get("project_id")
    if not project_id:
      return _response({"ok": False, "message": "Укажите project_id."}, 400)
    return _result_response(Operations.get_project_quotes(project_id))
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Operations.create_project_quote(
    payload.get("project_id"), payload.get("terms", ""), payload.get("expires_at")
  ))


@_api_route("/api/v1/quotes/status", authenticate_users=True, methods=["POST"])
def api_quote_status():
  import OperationsService as Operations

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(Operations.update_quote_status(
    payload.get("quote_id"), payload.get("status")
  ))


@_api_route("/api/v1/service", authenticate_users=True, methods=["GET", "POST"])
def api_service():
  import OperationsService as Operations

  if request.method == "GET":
    project_id = request.query_params.get("project_id")
    if not project_id:
      return _response({"ok": False, "message": "Укажите project_id."}, 400)
    return _result_response(Operations.get_service_records(project_id))
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  service_data = payload.get("service")
  if not isinstance(service_data, dict):
    return _response({"ok": False, "message": "Поле service должно быть JSON-объектом."}, 400)
  return _result_response(Operations.save_service_record(
    service_data, payload.get("record_id")
  ))


@_api_route("/api/v1/ai/operator", authenticate_users=True, methods=["POST"])
def api_ai_operator():
  import AI

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  context = payload.get("payload")
  if not isinstance(context, dict):
    return _response({"ok": False, "message": "Поле payload должно быть JSON-объектом."}, 400)
  return _result_response(AI.ai_operator(payload.get("operation"), context))


@_api_route("/api/v1/imports", authenticate_users=True, methods=["GET", "POST"])
def api_imports():
  import ImportEngineService as ImportEngine

  if request.method == "GET":
    return _result_response(ImportEngine.get_product_imports())
  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(ImportEngine.start_product_import(
    payload.get("source_type"), payload.get("source_name"),
    payload.get("source_url", ""), payload.get("format_name", "auto"),
    payload.get("secret_ref", "")
  ))


@_api_route("/api/v1/imports/upload", authenticate_users=True, methods=["POST"])
def api_import_upload():
  import ImportEngineService as ImportEngine

  data = request.body or b""
  if not data:
    return _response({"ok": False, "message": "Файл пуст."}, 400)
  if len(data) > ImportEngine.MAX_SOURCE_BYTES:
    return _response({"ok": False, "message": "Файл превышает лимит 2 МБ."}, 400)
  file_name = (request.get_header("X-File-Name") or "import").replace("\\", "/")
  file_name = file_name.rsplit("/", 1)[-1].strip()
  if not file_name or len(file_name) > 120:
    return _response({"ok": False, "message": "Укажите имя файла до 120 символов."}, 400)
  media = anvil.BlobMedia("application/octet-stream", data, name=file_name)
  import_id = (request.get_header("X-Import-ID") or "").strip()
  if import_id:
    return _result_response(ImportEngine.resume_product_import(import_id, media))
  source_name = request.get_header("X-Source-Name") or file_name
  format_name = request.get_header("X-Import-Format") or "auto"
  return _result_response(ImportEngine.start_product_import(
    "upload", source_name, "", format_name, "", media
  ))


@_api_route("/api/v1/imports/resume", authenticate_users=True, methods=["POST"])
def api_resume_import():
  import ImportEngineService as ImportEngine

  payload, error = _body()
  if error:
    return _response({"ok": False, "message": error}, 400)
  return _result_response(ImportEngine.resume_product_import(payload.get("import_id")))
