"""주요 일정 수집기.

1) FRED 발표 예정일 (美 CPI·고용·PPI·소매판매·PCE·GDP)
   공식 문서: https://fred.stlouisfed.org/docs/api/fred/release_dates.html
   include_release_dates_with_no_data=true → 아직 발표 전인 예정일까지 포함
2) 브라질 중앙은행 공식 달력 API (Copom 회의)
   https://www.bcb.gov.br/api/servico/sitebcb/calendar?inicioAgenda='YYYY-MM-DD'&fimAgenda='YYYY-MM-DD'&lista=Reuniões do Copom
3) config.yaml의 수동 입력 일정 (FOMC, 한은 금통위 등 — 공식 홈페이지에서 확인 후 입력)

시간: 美 일정은 동부시간(time_et)으로 적으면 한국시간으로 자동 변환 (서머타임 반영).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .common import env_key, get

log = logging.getLogger("market-info")
ET, KST = ZoneInfo("America/New_York"), ZoneInfo("Asia/Seoul")
FRED_URL = "https://api.stlouisfed.org/fred/release/dates"
BCB_URL = "https://www.bcb.gov.br/api/servico/sitebcb/calendar"


def et_to_kst(d: str, hhmm: str) -> tuple[str, str]:
    """美 동부시간 → 한국시간 (날짜가 하루 넘어갈 수 있음)."""
    dt = datetime.strptime(f"{d} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=ET).astimezone(KST)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def normalize(ev: dict) -> dict:
    """수동/자동 일정을 같은 형식으로: date·time은 한국시간."""
    d, t = str(ev["date"]), str(ev.get("time", "") or "")
    if ev.get("time_et"):
        d, t = et_to_kst(d, str(ev["time_et"]))
    return {"date": d, "time": t, "country": ev.get("country", ""), "event": ev["event"],
            "importance": int(ev.get("importance", 1)), "source": ev.get("source", "")}


def fred_events(items: list[dict], start: date, end: date) -> list[dict]:
    key = env_key("FRED_API_KEY")
    out = []
    for it in items:
        params = {"release_id": it["release_id"], "api_key": key, "file_type": "json",
                  "realtime_start": start.isoformat(), "realtime_end": end.isoformat(),
                  "include_release_dates_with_no_data": "true", "sort_order": "asc"}
        data = get(FRED_URL, params=params).json()
        for r in data.get("release_dates", []):
            if start.isoformat() <= r["date"] <= end.isoformat():
                out.append(normalize({**it, "date": r["date"], "country": "US", "source": "FRED"}))
    return out


def copom_events(start: date, end: date) -> list[dict]:
    params = {"inicioAgenda": f"'{start.isoformat()}'", "fimAgenda": f"'{end.isoformat()}'",
              "lista": "Reuniões do Copom"}
    rows = get(BCB_URL, params=params).json().get("conteudo", [])
    rows = [r for r in rows if "Copom" in r.get("evento", "")]
    # 이틀 회의 중 둘째 날(설명에 'Day 2')에 금리 결정 발표 (브라질 장 마감 후 → 한국시간 다음날 아침)
    day2 = sorted({r["dataEvento"][:10] for r in rows if re.search(r"Day\W*2", re.sub(r"<[^>]+>|&#160;|\u200b", " ", r.get("descricao") or ""))})
    return [normalize({"date": d, "country": "BR", "event": "브라질 Copom 기준금리 결정 (현지 날짜)",
                       "importance": 2, "source": "브라질 중앙은행"}) for d in day2]
    return out


def collect(cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """반환: (일정 목록, 실패 메시지 목록). 한 출처가 실패해도 나머지는 그대로."""
    auto = cfg.get("calendar_auto") or {}
    end = today + timedelta(days=60)
    events, errors = [], []
    try:
        events += fred_events(auto.get("fred_releases") or [], today, end)
    except Exception as e:  # noqa: BLE001
        errors.append(f"FRED 일정: {e}")
    if auto.get("copom"):
        try:
            events += copom_events(today, end)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Copom 일정: {e}")
    for ev in cfg.get("calendar") or []:
        try:
            events.append(normalize(ev))
        except Exception as e:  # noqa: BLE001
            errors.append(f"수동 일정 형식 오류 {ev}: {e}")
    events = [e for e in events if e["date"] >= today.isoformat()]      # 지난 일정 제외
    events.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
    return events, errors
