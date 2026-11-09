"""FRED 수집기.

공식 문서: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
units: lin(원값), chg(전기대비 차이), pch(전기대비 %), pc1(전년동기대비 %)
"""
from __future__ import annotations

from datetime import date

from .common import CollectorError, env_key, get, to_float

BASE = "https://api.stlouisfed.org/fred/series/observations"


def fetch(ind: dict, start: date, end: date) -> list[list]:
    params = {
        "series_id": ind["series"],
        "api_key": env_key("FRED_API_KEY"),
        "file_type": "json",
        "observation_start": start.isoformat(),
        "observation_end": end.isoformat(),
        "units": ind.get("units", "lin"),
    }
    data = get(BASE, params=params).json()
    if "observations" not in data:
        raise CollectorError(f"FRED 오류: {data.get('error_message', data)}")
    monthly = ind.get("cycle") in ("M", "Q")   # 월간·분기는 YYYY-MM
    out = []
    for o in data["observations"]:
        v = to_float(o["value"])
        if v is not None:
            out.append([o["date"][:7] if monthly else o["date"], v])
    return out
