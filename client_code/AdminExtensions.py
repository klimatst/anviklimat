"""Load the administrator-approved CSS/JavaScript site extensions."""

from anvil.js.window import document
import anvil.server


_APPLIED_REVISION = None
_APPLIED_EXTENSION_IDS = []


def apply_saved_extensions(force=False):
  """Apply the public extension bundle once per revision in this session."""
  global _APPLIED_REVISION, _APPLIED_EXTENSION_IDS
  if not force and _APPLIED_REVISION is not None:
    return
  try:
    bundle = anvil.server.call("get_public_site_extensions")
  except Exception:
    return
  revision = bundle.get("revision", 0)
  for extension_id in _APPLIED_EXTENSION_IDS:
    node = document.querySelector(
      "[data-eco-site-extension='{}']".format(extension_id)
    )
    if node is not None and node.parentNode is not None:
      node.parentNode.removeChild(node)

  head = document.head
  if head is None:
    return

  applied_ids = []
  for extension in bundle.get("extensions", []):
    if extension.get("kind") not in ("css", "javascript"):
      continue
    tag = "style" if extension["kind"] == "css" else "script"
    node = document.createElement(tag)
    node.setAttribute("data-eco-site-extension", extension["id"])
    if extension["kind"] == "javascript":
      node.setAttribute("type", "text/javascript")
    node.textContent = extension.get("code", "")
    head.appendChild(node)
    applied_ids.append(extension["id"])
  _APPLIED_EXTENSION_IDS = applied_ids
  _APPLIED_REVISION = revision
