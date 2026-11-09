"""Yahoo Finance 수집기 (yfinance).

※ Yahoo 데이터는 개인적·비상업적 이용 조건. config.yaml의 public 스위치로 공개 여부를 끌 수 있다.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from .common import CollectorError

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def fetch(ind: dict, start: date, end: date) -> list[list]:
    import yfinance as yf

    df = yf.Ticker(ind["symbol"]).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False, raise_errors=True,
    )
    if df is None or df.empty:
        raise CollectorError(f"Yahoo 데이터 없음: {ind['symbol']}")
    out = []
    for ts, v in df["Close"].dropna().items():
        out.append([ts.date().isoformat(), float(v)])
    return out
