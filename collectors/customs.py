"""관세청 품목별 수출입실적 (공공데이터포털).

공식 페이지: https://www.data.go.kr/data/15101609/openapi.do
요청: https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList
      ?serviceKey=&strtYymm=YYYYMM&endYymm=YYYYMM&hsSgn=HS코드
응답(XML): item{year(기간), hsCode, statKor(품목명), expDlr(수출금액 달러), ...}
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from urllib.parse import unquote

from .common import CollectorError, env_key, get, to_float

log = logging.getLogger("market-info")
URL = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
CHUNK_MONTHS = 12
_logged_sample = False


def _ym(d: date) -> int:
    return d.year * 100 + d.month


def _add_months(ym: int, n: int) -> int:
    y, m = divmod(ym, 100)
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return y * 100 + m


def _period(text: str) -> str | None:
    digits = re.sub(r"\D", "", text or "")
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return None   # '총계' 등


def _call(key: str, hs: str, s: int, e: int) -> list[dict]:
    global _logged_sample
    r = get(URL, params={"serviceKey": key, "strtYymm": s, "endYymm": e, "hsSgn": hs}, timeout=90)
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        raise CollectorError(f"관세청 응답 해석 실패: {r.text[:120]}")
    code = root.findtext(".//resultCode")
    if code not in (None, "00", "0", "000"):
        raise CollectorError(f"관세청 오류 {code}: {root.findtext('.//resultMsg')}")
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    if items and not _logged_sample:
        log.info("  관세청 응답 예시: %s", items[:3])
        _logged_sample = True
    return items


def fetch(ind: dict, start: date, end: date) -> list[list]:
    key = env_key("DATA_GO_KR_API_KEY")
    if "%" in key:          # Encoding 키를 넣었으면 Decoding 형태로 되돌림 (요청 시 자동 인코딩되므로)
        key = unquote(key)
    hs = ind["hs"]
    rows: list[dict] = []
    s, last = _ym(start), _ym(end)
    while s <= last:
        e = min(_add_months(s, CHUNK_MONTHS - 1), last)
        rows += _call(key, hs, s, e)
        s = _add_months(e, 1)

    # 같은 달에 4단위 합계 행이 있으면 그것을, 없으면 하위 코드 합산
    exact, sub = defaultdict(float), defaultdict(float)
    for it in rows:
        p = _period(it.get("year", ""))
        v = to_float(it.get("expDlr"))
        code = re.sub(r"\D", "", it.get("hsCode", ""))
        if not p or v is None or (code and not code.startswith(hs)):
            continue
        (exact if code == hs else sub)[p] += v
    months = sorted(set(exact) | set(sub))
    return [[m, round((exact[m] if m in exact else sub[m]) / 1e8, 3)] for m in months]   # 억 달러
