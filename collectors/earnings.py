"""실적발표 일정 (개인 참고용).

국내: KRX KIND 'IR 일정' (기업설명회 일정 중 실적발표만) + 네이버 금융 분기 실적(FnGuide 컨센서스)
  - KIND: POST https://kind.krx.co.kr/corpgeneral/irschedule.do  method=searchIRScheduleSub, forward=searchirschedule_sub
  - 네이버: https://m.stock.naver.com/api/stock/{종목코드}/finance/quarter  (isConsensus=Y 열이 컨센서스, 단위 억원)
미국: Nasdaq 실적 캘린더 https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD (시가총액 기준으로 추림)
"""
from __future__ import annotations

import html as htmllib
import logging
import re
from datetime import date, timedelta

from .common import get, to_float

log = logging.getLogger("market-info")
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
KIND = "https://kind.krx.co.kr/corpgeneral/irschedule.do"
EARN = re.compile(r"실적|Earnings|결산", re.I)
HANGUL = re.compile(r"[가-힣]")


def _cells(tr: str) -> list[str]:
    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
    return [re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", t))).strip() for t in tds]


def _post(data: dict) -> str:
    import requests
    h = dict(BROWSER, **{"Referer": KIND + "?method=searchIRScheduleMain&gubun=iRSchedule", "X-Requested-With": "XMLHttpRequest"})
    r = requests.post(KIND, data=data, headers=h, timeout=60)
    r.raise_for_status()
    return r.text


def kr_schedule(start: date, end: date, max_pages: int = 10) -> list[dict]:
    rows, seen_log = [], False
    for page in range(1, max_pages + 1):
        text = _post({"method": "searchIRScheduleSub", "forward": "searchirschedule_sub", "currentPageSize": "100",
                      "pageIndex": str(page), "fromDate": start.isoformat(), "toDate": end.isoformat(),
                      "searchFromDate": start.isoformat(), "searchToDate": end.isoformat(), "marketType": "",
                      "searchCorpName": "", "searchCodeType": "", "repIsuSrtCd": ""})
        trs = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
        got = 0
        for tr in trs:
            c = _cells(tr)
            if len(c) < 5 or not re.match(r"\d{4}-\d{2}-\d{2}", c[-1]):
                continue
            if not seen_log:
                log.info("  KIND 행 예시: %s | %s", c, re.findall(r"\d{6}", tr)[:3])
                seen_log = True
            got += 1
            dt = c[-1]
            code = (re.findall(r"(?:isurCd|repIsuSrtCd|companyCode|['\"])\s*[:=,(]?\s*['\"]?A?(\d{6})", tr) or re.findall(r"\b(\d{6})\b", tr) or [""])[0]
            rows.append({"company": c[1], "title": c[2], "place": c[3], "date": dt[:10],
                         "time": dt[11:16].replace("--:--", "") if len(dt) > 10 else "", "code": code})
        if got < 100:
            break
    # 실적발표만, 같은 회사·날짜는 한글 제목 하나만
    out = {}
    for r in rows:
        if not EARN.search(r["title"]) or re.search(r"NDR|Non-Deal|컨퍼런스|Conference", r["title"], re.I):
            continue
        key = (r["company"], r["date"])
        if key not in out or (HANGUL.search(r["title"]) and not HANGUL.search(out[key]["title"])):
            out[key] = r
    return sorted(out.values(), key=lambda r: (r["date"], r["time"] or "99:99", r["company"]))


def naver_quarter(code: str) -> dict:
    """네이버 분기 실적: 컨센서스 분기 영업이익·매출, 전년 동기 실적 (억원)."""
    d = get(f"https://m.stock.naver.com/api/stock/{code}/finance/quarter", headers=BROWSER, retries=1, timeout=20).json()
    info = d.get("financeInfo") or {}
    cols = info.get("trTitleList") or []
    cons = next((c for c in cols if c.get("isConsensus") == "Y"), None)
    rows = {r.get("title"): r.get("columns") or {} for r in info.get("rowList") or []}
    out = {}
    if cons:
        k = cons["key"]
        ly = f"{int(k[:4]) - 1}{k[4:]}"
        for name, tag in (("영업이익", "op"), ("매출액", "rev")):
            col = rows.get(name, {})
            out[f"{tag}_cons"] = to_float((col.get(k) or {}).get("value"))
            out[f"{tag}_ly"] = to_float((col.get(ly) or {}).get("value"))
        out["quarter"] = cons.get("title", "").rstrip(".")
    return out


def us_schedule(start: date, end: date, min_cap: float) -> list[dict]:
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            data = get(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}",
                       headers=dict(BROWSER, Origin="https://www.nasdaq.com", Referer="https://www.nasdaq.com/"),
                       retries=1, timeout=30).json()
            for r in ((data.get("data") or {}).get("rows") or []):
                cap = to_float(re.sub(r"[$,]", "", r.get("marketCap") or "")) or 0
                if cap < min_cap or "." in (r.get("symbol") or ""):      # 같은 회사 다른 주식(PBR.A 등) 제외
                    continue
                out.append({"date": d.isoformat(), "symbol": r["symbol"], "name": r.get("name", ""),
                            "when": {"time-pre-market": "개장 전", "time-after-hours": "장 마감 후"}.get(r.get("time"), ""),
                            "cap_b": round(cap / 1e9, 1), "quarter": r.get("fiscalQuarterEnding", ""),
                            "eps_cons": r.get("epsForecast") or "", "eps_ly": r.get("lastYearEPS") or "",
                            "n_est": r.get("noOfEsts") or ""})
        d += timedelta(days=1)
    return sorted(out, key=lambda r: (r["date"], -r["cap_b"]))


def collect(cfg: dict, today: date) -> tuple[dict, list[str]]:
    """반환: ({kr: [...], us: [...]}, 실패 메시지). 출처 하나가 실패해도 나머지는 그대로."""
    ec = cfg.get("earnings") or {}
    days = int(ec.get("days", 21))
    result, errors = {"kr": [], "us": []}, []
    if ec.get("kr", True):
        try:
            kr = kr_schedule(today, today + timedelta(days=days))
            for r in kr[: int(ec.get("kr_max_consensus", 80))]:      # 네이버 조회는 너무 많지 않게
                if r["code"]:
                    try:
                        r.update(naver_quarter(r["code"]))
                    except Exception as e:  # noqa: BLE001
                        r["cons_error"] = type(e).__name__
            result["kr"] = kr
        except Exception as e:  # noqa: BLE001
            errors.append(f"국내 실적 일정: {e}")
    if ec.get("us", True):
        try:
            result["us"] = us_schedule(today, today + timedelta(days=int(ec.get("us_days", 14))), float(ec.get("us_min_cap_b", 30)) * 1e9)
        except Exception as e:  # noqa: BLE001
            errors.append(f"미국 실적 일정: {e}")
    return result, errors
