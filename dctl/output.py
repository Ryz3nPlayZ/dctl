from __future__ import annotations

import json
import sys
from typing import Any

from dctl.errors import DctlError


def emit_success(data: Any, meta: dict[str, Any]) -> None:
    payload = {
        "status": "ok",
        "data": data,
        "meta": meta,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def emit_error(error: DctlError, meta: dict[str, Any]) -> None:
    payload = {
        "status": "error",
        "error": error.to_dict(),
        "meta": meta,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")

