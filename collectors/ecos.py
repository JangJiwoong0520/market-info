"""한국은행 ECOS 수집기.

공식 문서: https://ecos.bok.or.kr/api/  (StatisticSearch)
URL 형식: /api/StatisticSearch/{키}/json/kr/{시작행}/{끝행}/{통계표}/{주기}/{시작}/{종료}/{항목}
"""
from __future__ import annotations

from datetime import date

from .common import CollectorError, env_key, get, to_float

BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
PAGE = 10000


def _fmt(d: date, cycle: str) -> str:
    return d.strftime("%Y%m%d") if cycle == "D" else d.strftime("%Y%m")


def _out_date(t: str, cycle: str) -> str:
    if cycle == "D":
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    return f"{t[:4]}-{t[4:6]}"


def fetch(ind: dict, start: date, end: date) -> list[list]:
    key = env_key("ECOS_API_KEY")   # 테스트 때만 ECOS_API_KEY=sample (연습용, 최대 10건)
    cycle = ind.get("cycle", "D")
    page = 10 if key == "sample" else PAGE
    out, first = [], 1
    while True:
        url = (f"{BASE}/{key}/json/kr/{first}/{first + page - 1}/{ind['stat']}/{cycle}/"
               f"{_fmt(start, cycle)}/{_fmt(end, cycle)}/{ind['item']}")
        data = get(url).json()
        if "StatisticSearch" not in data:
            res = data.get("RESULT", {})
            if res.get("CODE") == "INFO-200":          # 해당 데이터 없음
                break
            raise CollectorError(f"ECOS 오류 {res.get('CODE')}: {res.get('MESSAGE', '')[:80]}")
        body = data["StatisticSearch"]
        for r in body["row"]:
            v = to_float(r["DATA_VALUE"])
            if v is not None:
                out.append([_out_date(r["TIME"], cycle), v])
        total = int(body["list_total_count"])
        first += page
        if first > total or key == "sample":
            break
    return out
