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


def fetch_intraday(symbol: str, scale: float = 1.0) -> list[list]:
    """최근 24시간 5분 단위 값 (한국시간 'YYYY-MM-DDTHH:MM'). 1일(1D) 차트용."""
    import yfinance as yf
    from datetime import timedelta as _td

    df = yf.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=False)
    if df is None or df.empty:
        raise CollectorError(f"Yahoo 장중 데이터 없음: {symbol}")
    s = df["Close"].dropna()
    s = s[s.index >= s.index[-1] - _td(hours=24)]
    # 장이 끊기는 지표(주식 등): 4시간 넘게 비는 곳 이후 = 마지막 장만 (24시간 시장의 짧은 공백은 무시)
    gaps = [i for i in range(1, len(s)) if s.index[i] - s.index[i - 1] > _td(hours=4)]
    if gaps:
        s = s.iloc[gaps[-1]:]
    s.index = s.index.tz_convert("Asia/Seoul")
    return [[ts.strftime("%Y-%m-%dT%H:%M"), round(float(v) * scale, 4)] for ts, v in s.items()]
