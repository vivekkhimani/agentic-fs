"""agentic-fs core: contracts, DTOs, the key scheme, and the error vocabulary.

Depends on pydantic only — importable without the server.
"""

from afs_core import errors, keys, models

__all__ = ["errors", "keys", "models"]
