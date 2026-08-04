from __future__ import annotations


def backend_name(backend: object) -> str:
    for attribute in ("name", "value"):
        value = getattr(backend, attribute, None)
        if isinstance(value, str) and value:
            return value
    return repr(backend)
