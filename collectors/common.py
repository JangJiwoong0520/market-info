"""수집기 공통 도구: HTTP 요청(재시도), 로그, 날짜 처리."""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta

import requests

log = logging.getLogger("market-info")

USER_AGENT = "market-info-dashboard/1.0 (personal, non-commercial)"
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class CollectorError(Exception):
    """수집 실패 (해당 지표만 건너뛰고 계속 진행)."""


def get(url: str, params: dict | None = None, timeout: int = 60, retries: int = 3) -> requests.Response:
    """GET 요청. 네트워크 오류·5xx는 2s, 4s, 8s 간격으로 재시도."""
    last = None
    for i in range(retries + 1):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            if i < retries:
                time.sleep(2 ** (i + 1))
    raise CollectorError(f"요청 실패: {_mask(url)} ({_mask(str(last))})")


def _mask(text: str) -> str:
    """로그에 API 키가 찍히지 않도록 가린다."""
    for name in ("ECOS_API_KEY", "FRED_API_KEY", "DATA_GO_KR_API_KEY"):
        v = os.environ.get(name)
        if v:
            text = text.replace(v, "***")
    return text


def env_key(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise CollectorError(f"환경변수 {name} 가 없습니다 (.env 또는 GitHub Secrets 확인)")
    return v


def parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def today_kst() -> date:
    return (datetime.utcnow() + timedelta(hours=9)).date()


def to_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", ".", "-", "NaN", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
