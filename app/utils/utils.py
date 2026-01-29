from __future__ import annotations

from uuid import uuid4


def get_uuid(remove_hyphen: bool = False) -> str:
    u = str(uuid4())
    if remove_hyphen:
        u = u.replace("-", "")
    return u
