"""Small, read-only authentication lookups used by the client UI."""

import anvil.server
import Core


@anvil.server.callable
def get_access_context():
  """Return the same stable access contract used by the core shell."""
  return Core.build_access_context()
