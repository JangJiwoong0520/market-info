"""심리 지표 수집기 (개인 참고용).

1) CNN Fear & Greed — CNN 페이지가 쓰는 데이터 주소 (공식 API 아님)
   https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{시작일}
   → fear_and_greed_historical.data: [{x: ms 타임스탬프, y: 점수}, ...] (약 1년 제공 → 매일 누적)
2) Crypto Fear & Greed — alternative.me 공식 API (출처 표기 조건으로 이용 허용)
   https://api.alternative.me/fng/?limit=0&format=json → 2018년부터 전체
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .common import CollectorError, get, to_float

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*", "Referer": "https://edition.cnn.com/", "Origin": "https://edition.cnn.com"}


def _d(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def fetch_cnn(ind: dict, start: date, end: date) -> list[list]:
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{}"
    try:
        data = get(url.format(start.isoformat()), headers=BROWSER, retries=1).json()
    except CollectorError:                                    # 너무 오래된 시작일은 거절될 수 있음 → 최근 1년
        data = get(url.format((end - timedelta(days=365)).isoformat()), headers=BROWSER).json()
    rows = (data.get("fear_and_greed_historical") or {}).get("data") or []
    out = {}
    for r in rows:
        v = to_float(r.get("y"))
        if v is not None:
            out[_d(r["x"] / 1000)] = round(v, 1)          # 같은 날 여러 개면 마지막 값
    now = data.get("fear_and_greed") or {}
    if now.get("score") is not None and now.get("timestamp"):
        out[now["timestamp"][:10]] = round(float(now["score"]), 1)
    if not out:
        raise CollectorError("CNN 공포·탐욕 데이터 없음")
    return sorted([k, v] for k, v in out.items() if start.isoformat() <= k <= end.isoformat())


def fetch_crypto(ind: dict, start: date, end: date) -> list[list]:
    data = get("https://api.alternative.me/fng/", params={"limit": 0, "format": "json"}).json()
    if (data.get("metadata") or {}).get("error"):
        raise CollectorError(f"alternative.me 오류: {data['metadata']['error']}")
    out = {_d(int(r["timestamp"])): float(r["value"]) for r in data.get("data", [])}
    return sorted([k, v] for k, v in out.items() if start.isoformat() <= k <= end.isoformat())


def fetch_stockhub(ind: dict, start: date, end: date) -> list[list]:
    """StockHub 한국 공포·탐욕 — 최근 30일만 제공 → 매일 실행하며 누적."""
    data = get("https://stockhub.kr/api/fear-greed/history",
               headers=dict(BROWSER, Referer="https://stockhub.kr/fear-greed", Origin="https://stockhub.kr")).json()
    key = ind.get("field", "kr")
    out = {r["date"]: float(r[key]) for r in data.get("data", []) if r.get(key) is not None}
    if not out:
        raise CollectorError("StockHub 데이터 없음")
    return sorted([k, v] for k, v in out.items() if start.isoformat() <= k <= end.isoformat())


def fetch(ind: dict, start: date, end: date) -> list[list]:
    return {"cnn": fetch_cnn, "alternative": fetch_crypto, "stockhub": fetch_stockhub}[ind["source"]](ind, start, end)
