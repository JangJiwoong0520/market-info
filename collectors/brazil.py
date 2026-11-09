"""브라질 수집기.

1) 중앙은행 SGS: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{코드}/dados?formato=json
   - 일별 시리즈는 한 번에 최대 10년만 조회 가능 → 5년씩 나눠 받는다.
   - Selic(432)은 다음 회의 전까지 미래 날짜가 채워져 있어 오늘 이후는 버린다.
2) 국고청 Tesouro Direto 금리 CSV (ODbL 라이선스)
   - NTN-F(Tesouro Prefixado com Juros Semestrais) 중 잔존만기가 10년에 가장 가까운 종목.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from .common import CollectorError, get, today_kst, to_float

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
TD_DATASET = "df56aa42-484a-4a59-8184-7676580c81e3"   # Taxas dos Títulos Ofertados pelo Tesouro Direto


def _br_date(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%Y").date()


def _sgs_call(code, s: date, e: date) -> list[dict]:
    """SGS는 가끔 특정 날짜 조합에 빈 응답(HTTP 304)을 준다 → 날짜를 하루씩 옮겨 재시도."""
    one = timedelta(days=1)
    for s2, e2 in ((s, e), (s - one, e), (s + one, e), (s, e - one)):
        params = {"formato": "json", "dataInicial": s2.strftime("%d/%m/%Y"), "dataFinal": e2.strftime("%d/%m/%Y")}
        r = get(SGS.format(code=code), params=params)
        if r.status_code == 200 and r.content.strip():
            rows = r.json()
            if isinstance(rows, dict):
                raise CollectorError(f"SGS 오류: {rows}")
            return rows
    raise CollectorError(f"SGS {code}: 빈 응답 ({s}~{e})")


def fetch_sgs(ind: dict, start: date, end: date) -> list[list]:
    end = min(end, today_kst())
    monthly = ind.get("cycle") == "M"
    out, s = {}, start
    while s <= end:
        e = min(date(s.year + 5, s.month, 1), end) if not monthly else end
        rows = _sgs_call(ind["sgs"], s, e)
        for row in rows:
            d = _br_date(row["data"])
            v = to_float(row["valor"])
            if v is None or d > end:
                continue
            out[d.strftime("%Y-%m") if monthly else d.isoformat()] = v
        if monthly or e >= end:
            break
        s = date(e.year, e.month, e.day)
    return sorted([k, v] for k, v in out.items())


def _td_csv_url() -> str:
    meta = get(CKAN, params={"id": TD_DATASET}).json()
    for res in meta["result"]["resources"]:
        if res.get("format", "").upper() == "CSV":
            return res["url"]
    raise CollectorError("Tesouro CSV 주소를 찾지 못함")


def fetch_tesouro(ind: dict, start: date, end: date) -> list[list]:
    text = get(_td_csv_url(), timeout=180).content.decode("latin-1")
    target = ind.get("target_years", 10)
    want = ind["title_type"]
    best: dict[date, tuple[float, float]] = {}   # 기준일 → (만기와 목표의 차이, 금리)
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if row["Tipo Titulo"] != want:
            continue
        base = _br_date(row["Data Base"])
        if base < start or base > end:
            continue
        rate = to_float(row["Taxa Compra Manha"].replace(",", ".")) or to_float(row["Taxa Venda Manha"].replace(",", "."))
        if not rate:
            continue
        years = (_br_date(row["Data Vencimento"]) - base).days / 365.25
        gap = abs(years - target)
        if base not in best or gap < best[base][0]:
            best[base] = (gap, rate)
    return [[d.isoformat(), v[1]] for d, v in sorted(best.items())]


def fetch(ind: dict, start: date, end: date) -> list[list]:
    return fetch_tesouro(ind, start, end) if ind["source"] == "tesouro" else fetch_sgs(ind, start, end)
