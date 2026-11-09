"""미 재무부 일일 국채 금리 (Daily Treasury Par Yield Curve Rates).

공식 페이지: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve
CSV: .../daily-treasury-rates.csv/{연도}/all?type=daily_treasury_yield_curve&field_tdr_date_value={연도}&page&_format=csv
- 미국 정부 자료(공개). FRED의 DGS2·DGS10·DGS30과 같은 숫자이며, 재무부는 당일 장 마감 후 바로 올린다(FRED는 하루 늦음).
- 열 이름(예: "10 Yr")으로 찾는다 — 연도마다 열 구성이 다르다(30년물은 2002~2006년 발행 중단으로 빈칸).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from .common import CollectorError, get, to_float

URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
       "{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
_cache: dict[int, list[dict]] = {}     # 한 번 실행하는 동안 연도별 파일 재사용 (2년·10년·30년이 같은 파일)


def _year(y: int) -> list[dict]:
    if y not in _cache:
        text = get(URL.format(y=y), timeout=90).text
        if not text.lstrip().startswith("Date"):
            raise CollectorError(f"재무부 {y}년 파일 형식이 예상과 다름: {text[:60]!r}")
        _cache[y] = list(csv.DictReader(io.StringIO(text)))
    return _cache[y]


def fetch(ind: dict, start: date, end: date) -> list[list]:
    col = ind["column"]
    out = {}
    for y in range(start.year, end.year + 1):
        for row in _year(y):
            d = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            v = to_float(row.get(col))
            if v is not None and start <= d <= end:
                out[d.isoformat()] = v
    if not out:
        raise CollectorError(f"재무부 '{col}' 데이터 없음 ({start}~{end})")
    return sorted([k, v] for k, v in out.items())
