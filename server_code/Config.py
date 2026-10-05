import ipaddress
import os
import socket
from datetime import datetime, timezone

try:
  import anvil.secrets as _anvil_secrets
except ImportError:
  _anvil_secrets = None

from anvil.tables import app_tables


MANAGED_SECRET_PREFIX = "managed_secret."
MANAGED_SECRET_KEY = "new_key"
MANAGED_SECRET_NAMES = {
  "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
  "IMAGEKIT_PRIVATE_KEY", "IMAGEKIT_PUBLIC_KEY", "IMAGEKIT_URL_ENDPOINT",
  "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
  "TELEGRAM_BOT_TOKEN", "SMTP_USERNAME", "SMTP_PASSWORD",
  "GOOGLE_MAPS_API_KEY", "SENTRY_DSN", "WEBHOOK_SIGNING_SECRET",
  "ERP_API_KEY", "ERP_API_URL", "PAYMENT_API_KEY", "PAYMENT_API_SECRET",
  "SEARCH_API_KEY"
}


def get_value(name, default=None):
  return os.environ.get(name, default)


def is_public_host(hostname, port=443):
  if not isinstance(hostname, str) or not hostname:
    return False
  normalized = hostname.rstrip(".").casefold()
  try:
    address = ipaddress.ip_address(normalized.split("%", 1)[0])
  except ValueError:
    try:
      resolved = {
        ipaddress.ip_address(str(item[4][0]).split("%", 1)[0])
        for item in socket.getaddrinfo(normalized, port, type=socket.SOCK_STREAM)
      }
    except (OSError, ValueError):
      return False
    return bool(resolved) and all(item.is_global for item in resolved)
  return address.is_global


def get_secret(name):
  managed = get_managed_secret(name)
  if managed:
    return managed
  if _anvil_secrets is not None:
    try:
      value = _anvil_secrets.get_secret(name)
    except _anvil_secrets.SecretError:
      value = None
    if value:
      return value
  return os.environ.get(name)


def _managed_secret_row(name):
  if not isinstance(name, str) or name not in MANAGED_SECRET_NAMES:
    return None
  return app_tables.system_settings.get(key=MANAGED_SECRET_PREFIX + name)


def get_managed_secret(name):
  row = _managed_secret_row(name)
  if row is None:
    return None
  value = row["value"]
  encrypted = value.get("ciphertext") if isinstance(value, dict) else None
  if not encrypted or _anvil_secrets is None:
    return None
  try:
    return _anvil_secrets.decrypt_with_key(MANAGED_SECRET_KEY, encrypted)
  except _anvil_secrets.SecretError:
    return None


def set_managed_secret(name, value, actor=None):
  if not isinstance(name, str) or name not in MANAGED_SECRET_NAMES:
    return {"ok": False, "message": "Этот секрет не разрешён для панели управления."}
  if not isinstance(value, str) or not value.strip():
    return {"ok": False, "message": "Введите значение секрета."}
  if len(value) > 1000 or any(ord(char) < 32 and char not in "\t\n" for char in value):
    return {"ok": False, "message": "Значение секрета слишком длинное или содержит недопустимые символы."}
  if _anvil_secrets is None:
    return {"ok": False, "message": "Шифрование секретов Anvil недоступно на сервере."}
  try:
    encrypted = _anvil_secrets.encrypt_with_key(MANAGED_SECRET_KEY, value.strip())
  except _anvil_secrets.SecretError:
    return {"ok": False, "message": "Не удалось зашифровать секрет ключом приложения."}
  now = datetime.now(timezone.utc)
  row = _managed_secret_row(name)
  payload = {"ciphertext": encrypted, "updated_at": now.isoformat()}
  if row is None:
    values = {"key": MANAGED_SECRET_PREFIX + name, "value": payload,
              "updated_at": now}
    if actor is not None:
      values["updated_by"] = actor
    app_tables.system_settings.add_row(**values)
  else:
    values = {"value": payload, "updated_at": now}
    if actor is not None:
      values["updated_by"] = actor
    row.update(**values)
  return {"ok": True, "message": "Секрет сохранён в зашифрованном хранилище приложения."}


def clear_managed_secret(name, actor=None):
  row = _managed_secret_row(name)
  if row is None:
    return {"ok": True, "message": "Секрет уже очищен."}
  row.delete()
  return {"ok": True, "message": "Значение секрета удалено из хранилища панели."}


def managed_secret_exists(name):
  return bool(get_managed_secret(name))
