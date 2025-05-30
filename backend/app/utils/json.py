"""Unified JSON helpers – work with or without orjson."""
from typing import Any, Callable
import json
from datetime import date, datetime
from decimal import Decimal

try:
    import orjson  # type: ignore
    HAS_ORJSON = True

    def _dumps(obj: Any, **_) -> str:
        # identical output API – always Unicode str
        return orjson.dumps(
            obj,
            option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_SERIALIZE_DATACLASS | orjson.OPT_UTC_Z,
        ).decode()

    _loads: Callable[[str | bytes], Any] = orjson.loads

except ImportError:  # Python 3.12: wheel missing
    HAS_ORJSON = False

    def _dumps(obj: Any, **_) -> str:
        def default(o):
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            elif isinstance(o, Decimal):
                return float(o)
            return str(o)
        
        return json.dumps(obj, default=default, ensure_ascii=False)

    def _loads(s: str | bytes) -> Any:
        if isinstance(s, bytes):
            s = s.decode('utf-8')
        return json.loads(s)

# Export unified interface
json_dumps = _dumps
json_loads = _loads
dumps = _dumps
loads = _loads

def sanitize_for_jsonb(data: Any) -> Any:
    """Recursively sanitize data for JSONB storage."""
    if isinstance(data, dict):
        return {k: sanitize_for_jsonb(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_jsonb(item) for item in data]
    elif isinstance(data, (datetime, date)):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return float(data)
    else:
        return data

__all__ = ["dumps", "loads", "json_dumps", "json_loads", "sanitize_for_jsonb", "HAS_ORJSON"]