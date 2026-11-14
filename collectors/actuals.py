"""주요 일정의 '실제치' — 발표된 美 지표를 FRED에서 직접 계산 (ForexFactory 파일에는 실제치가 없음).

공식 문서: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- 1) series/vintagedates(https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)로
     발표일(미 동부 날짜)~3일 안에 FRED가 이 시리즈를 새로 올린 날(빈티지)이 있는지 확인
     → 없으면 아직 미반영이므로 실제치를 비워 둔다 (이전 값을 실제치로 착각하지 않게)
  2) 그 빈티지 날짜 기준 값(realtime_start = realtime_end = 빈티지)을 받아 마지막 관측치 = 이번 발표치
- 계산 방식(config.yaml calendar_actuals):
    pct1  전월(전기)비 %      pct12 전년동월비 %
    diff  전월 대비 증감(원 단위 × scale)
    level 값 그대로(× scale)
- 표시 자릿수·단위(%, K, M)는 ForexFactory 예상치 글자 모양을 그대로 따른다 (예: "0.3%", "194K", "7.20M").
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .common import env_key, get, to_float

log = logging.getLogger("market-info")
BASE = "https://api.stlouisfed.org/fred/series/observations"
VINTAGES = "https://api.stlouisfed.org/fred/series/vintagedates"
ET, KST = ZoneInfo("America/New_York"), ZoneInfo("Asia/Seoul")
MULT = {"": 1, "%": 1, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
NUM = re.compile(r"(-?\d+(?:\.\d+)?)\s*([KMBT%]?)")


def parse_num(s: str) -> tuple[float, int, str] | None:
    """'0.3%' → (0.3, 1, '%'), '194K' → (194000, 0, 'K'). 숫자가 없으면 None."""
    m = NUM.search(s or "")
    if not m:
        return None
    txt, suf = m.group(1), m.group(2)
    dec = len(txt.split(".")[1]) if "." in txt else 0
    return float(txt) * MULT[suf], dec, suf


def fmt_like(v: float, like: str) -> str:
    """값 v를 예상치(like)와 같은 단위·자릿수로."""
    p = parse_num(like)
    dec, suf = (p[1], p[2]) if p else (1, "")
    return f"{v / MULT[suf]:.{dec}f}{suf}"


def compare(act: str, fc: str) -> str:
    """실제치가 예상치보다 높으면 'up', 낮으면 'dn', 같으면 'eq' (표시된 자릿수 기준)."""
    a, f = parse_num(act), parse_num(fc)
    if not a or not f:
        return ""
    return "up" if a[0] > f[0] + 1e-9 else "dn" if a[0] < f[0] - 1e-9 else "eq"


def et_date(kst_date: str, kst_time: str) -> str:
    """한국시간 날짜·시각 → 미 동부 날짜 (FRED 실시간 기준일)."""
    try:
        dt = datetime.strptime(f"{kst_date} {kst_time}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    except ValueError:
        return kst_date
    return dt.astimezone(ET).strftime("%Y-%m-%d")


_cache: dict[tuple[str, str], list[dict]] = {}


def release_vintage(series: str, d: str, today: str) -> str | None:
    """발표일 d부터 3일 안(오늘까지)에 FRED가 이 시리즈를 갱신한 첫 날짜. 없으면 None."""
    end = min((date.fromisoformat(d) + timedelta(days=3)).isoformat(), today)
    if end < d:
        return None
    params = {"series_id": series, "api_key": env_key("FRED_API_KEY"), "file_type": "json",
              "realtime_start": d, "realtime_end": end}
    data = get(VINTAGES, params=params).json()
    if "vintage_dates" not in data:
        raise ValueError(f"FRED 오류: {data.get('error_message', data)}")
    vs = [v for v in data["vintage_dates"] if d <= v <= end]
    return vs[0] if vs else None


def vintage(series: str, d: str) -> list[dict]:
    """빈티지 날짜 d 기준으로 알려진 관측값 (최근 15개월)."""
    if (series, d) not in _cache:
        start = (date.fromisoformat(d) - timedelta(days=460)).isoformat()
        params = {"series_id": series, "api_key": env_key("FRED_API_KEY"), "file_type": "json",
                  "realtime_start": d, "realtime_end": d, "observation_start": start}
        obs = get(BASE, params=params).json().get("observations", [])
        _cache[(series, d)] = [o for o in obs if to_float(o["value"]) is not None]
    return _cache[(series, d)]


def compute(rule: dict, d: str, today: str) -> float | None:
    vd = release_vintage(rule["series"], d, today)
    if not vd:                                                # FRED가 아직 안 올림
        return None
    obs = vintage(rule["series"], vd)
    if not obs:
        return None
    log.info("  · 실제치 %s: 빈티지 %s, 관측 %s = %s", rule["series"], vd, obs[-1]["date"], obs[-1]["value"])
    vals = [to_float(o["value"]) for o in obs]
    how, scale = rule.get("calc", "pct1"), float(rule.get("scale", 1))
    if how == "level":
        return vals[-1] * scale
    if how == "diff" and len(vals) >= 2:
        return (vals[-1] - vals[-2]) * scale
    if how == "pct1" and len(vals) >= 2:
        return (vals[-1] / vals[-2] - 1) * 100
    if how == "pct12":                                        # 같은 달 1년 전 값
        last = obs[-1]["date"]
        prev = f"{int(last[:4]) - 1}{last[4:]}"
        base = next((to_float(o["value"]) for o in obs if o["date"] == prev), None)
        return (vals[-1] / base - 1) * 100 if base else None
    return None


def attach(events: list[dict], rules: dict, now: datetime) -> tuple[int, list[str]]:
    """발표 시각이 지난 일정의 ForexFactory 항목(ff)에 실제치(act)·비교(vs)를 붙인다."""
    n, errors = 0, []
    for ev in events:
        if not ev.get("ff") or ev.get("country") != "US":
            continue
        t = ev.get("time") or ""
        if not re.fullmatch(r"\d\d:\d\d", t):
            continue
        if datetime.strptime(f"{ev['date']} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=KST) > now:
            continue
        d = et_date(ev["date"], t)
        for f in ev["ff"]:
            rule = rules.get(f.get("key", ""))
            if not rule or f.get("act"):
                continue
            try:
                v = compute(rule, d, now.strftime("%Y-%m-%d"))
            except Exception as e:  # noqa: BLE001 — 한 항목 실패는 건너뜀
                errors.append(f"{f.get('key')}({rule['series']}): {e}")
                continue
            if v is None:
                log.info("  · 실제치 아직 없음: %s %s (FRED %s)", d, f.get("key"), rule["series"])
                continue
            f["act"] = fmt_like(v, f.get("fc") or f.get("prev") or "")
            f["vs"] = compare(f["act"], f.get("fc", ""))
            f["act_src"] = f"FRED {rule['series']}"
            n += 1
    return n, errors
