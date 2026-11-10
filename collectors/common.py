"""수집기 공통 도구: HTTP 요청(재시도), 로그, 날짜 처리."""
from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import quote, quote_plus
from datetime import date, datetime, timedelta

import requests

log = logging.getLogger("market-info")

USER_AGENT = "market-info-dashboard/1.0 (personal, non-commercial)"
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class CollectorError(Exception):
    """수집 실패 (해당 지표만 건너뛰고 계속 진행)."""


def get(url: str, params: dict | None = None, timeout: int = 60, retries: int = 3,
        headers: dict | None = None) -> requests.Response:
    """GET 요청. 네트워크 오류·5xx·429는 2s, 4s, 8s 간격으로 재시도 (4xx는 재시도 안 함)."""
    last = ""
    for i in range(retries + 1):
        try:
            r = _session.get(url, params=params, timeout=timeout, headers=headers)
        except requests.RequestException as e:
            last = f"연결 오류 {type(e).__name__}"
        else:
            if r.status_code < 400:
                return r
            body = " ".join(r.text[:120].split())
            last = f"HTTP {r.status_code}" + (f" {mask(body)}" if body else "")
            if r.status_code < 500 and r.status_code != 429:
                break
        if i < retries:
            time.sleep(2 ** (i + 1))
    raise CollectorError(f"요청 실패: {safe_url(url)} ({last})")


def safe_url(url: str) -> str:
    """주소에서 쿼리(?뒤, 키가 들어감)를 지우고, 경로에 든 키도 가린다."""
    return mask(url.split("?", 1)[0])


def mask(text: str) -> str:
    """로그·JSON에 API 키가 찍히지 않도록 가린다 (원문·URL 인코딩 형태 모두)."""
    text = re.sub(r"\?[^\s)]*", "?…", text)
    for name in ("ECOS_API_KEY", "FRED_API_KEY", "DATA_GO_KR_API_KEY"):
        v = os.environ.get(name, "").strip()
        if len(v) >= 6:
            for form in {v, quote(v, safe=""), quote_plus(v)}:
                text = text.replace(form, "***")
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
