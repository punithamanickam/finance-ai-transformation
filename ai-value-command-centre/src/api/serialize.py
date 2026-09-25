"""Convert engine outputs (numpy / pandas types, NaN) into plain JSON-safe Python values."""
from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass

import numpy as np
import pandas as pd


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return [jsonable(r) for r in obj.to_dict("records")]
    if isinstance(obj, pd.Series):
        return jsonable(obj.to_dict())
    if is_dataclass(obj) and not isinstance(obj, type):
        return jsonable(asdict(obj))
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj
