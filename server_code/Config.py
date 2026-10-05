import ipaddress
import os
import socket

try:
  import anvil.secrets as _anvil_secrets
except ImportError:
  _anvil_secrets = None


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
  if _anvil_secrets is not None:
    try:
      value = _anvil_secrets.get_secret(name)
    except _anvil_secrets.SecretError:
      value = None
    if value:
      return value
  return os.environ.get(name)
