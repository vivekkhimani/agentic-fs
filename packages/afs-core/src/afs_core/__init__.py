"""agentic-fs core: contracts, DTOs, the key scheme, and the error vocabulary.

Depends on pydantic only — importable without the server. (``afs_core.testing``
is intentionally not imported here: it depends on pytest and is opt-in.)
"""

from afs_core import contracts, errors, keys, models

__all__ = ["contracts", "errors", "keys", "models"]
