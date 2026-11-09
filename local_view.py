"""내 PC 전용 보기 — 주요 일정에 ForexFactory 컨센서스(이전·예상)를 붙여서 대시보드를 연다.

사용법 (Windows PowerShell, market-info 폴더에서):
    python local_view.py

- ForexFactory가 사용자용으로 제공하는 '이번 주 일정 내보내기' 파일을 이 PC로만 받는다 (개인 이용).
- 결과는 docs/local/ 에만 저장되고, .gitignore로 GitHub에 올라가지 않는다.
- 화면은 이 PC(127.0.0.1)에서만 열린다. 같은 와이파이의 다른 기기도 접속할 수 없다.
- ⚠️ 받은 컨센서스를 공개 페이지·고객 자료에 옮기지 않는다 (ForexFactory 약관상 재배포 금지).

외부 패키지 없이 파이썬 기본 기능만 쓴다.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
LOCAL = DOCS / "local"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
PAGES_CAL = "https://jangjiwoong0520.github.io/market-info/data/calendar.json"
KST = timezone(timedelta(hours=9))
CACHE_MIN = 30          # ForexFactory 파일은 30분에 한 번만 새로 받음 (서버 배려)

# ForexFactory 제목 → 한글
KO = {
    "CPI m/m": "CPI 전월비", "Core CPI m/m": "근원 CPI 전월비", "CPI y/y": "CPI 전년비", "Core CPI y/y": "근원 CPI 전년비",
    "PPI m/m": "PPI 전월비", "Core PPI m/m": "근원 PPI 전월비",
    "Retail Sales m/m": "소매판매 전월비", "Core Retail Sales m/m": "근원 소매판매 전월비",
    "Non-Farm Employment Change": "비농업 고용", "Unemployment Rate": "실업률",
    "Average Hourly Earnings m/m": "시간당 임금 전월비", "Unemployment Claims": "신규 실업수당청구",
    "Advance GDP q/q": "GDP 속보 (전기비 연율)", "Prelim GDP q/q": "GDP 잠정 (전기비 연율)", "Final GDP q/q": "GDP 확정 (전기비 연율)",
    "Core PCE Price Index m/m": "근원 PCE 전월비", "Personal Income m/m": "개인소득 전월비", "Personal Spending m/m": "개인지출 전월비",
    "Federal Funds Rate": "FOMC 기준금리", "FOMC Statement": "FOMC 성명", "FOMC Press Conference": "FOMC 기자회견",
    "FOMC Meeting Minutes": "FOMC 의사록", "Fed Chair Powell Speaks": "연준 의장 연설",
    "ISM Manufacturing PMI": "ISM 제조업 PMI", "ISM Services PMI": "ISM 서비스업 PMI",
    "Prelim UoM Consumer Sentiment": "미시간대 소비자심리 (예비)", "Revised UoM Consumer Sentiment": "미시간대 소비자심리 (확정)",
    "JOLTS Job Openings": "JOLTS 구인건수", "ADP Non-Farm Employment Change": "ADP 민간고용", "CB Consumer Confidence": "컨퍼런스보드 소비자신뢰",
}


def ko(title: str) -> str:
    if title in KO:
        return KO[title]
    if title.startswith("FOMC Member ") and title.endswith(" Speaks"):
        return f"FOMC 위원 연설 ({title[12:-7]})"
    return title


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "market-info-local/1.0 (personal use)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_ff() -> list[dict]:
    cache = LOCAL / "ff_thisweek.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_MIN * 60:
        print(f"· ForexFactory: 저장해둔 파일 사용 ({CACHE_MIN}분 이내에 받은 것)")
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        raw = fetch(FF_URL)
        data = json.loads(raw)
        cache.write_bytes(raw)
        print(f"· ForexFactory: 이번 주 일정 {len(data)}건 받음")
        return data
    except Exception as e:  # noqa: BLE001
        if cache.exists():
            print(f"· ForexFactory 받기 실패({e}) → 예전에 받은 파일 사용")
            return json.loads(cache.read_text(encoding="utf-8"))
        print(f"· ForexFactory 받기 실패({e}) → 컨센서스 없이 표시")
        return []


def load_calendar() -> list[dict]:
    try:
        cal = json.loads(fetch(PAGES_CAL))
        print(f"· 공개 페이지 일정 {len(cal.get('events', []))}건 받음")
    except Exception as e:  # noqa: BLE001
        p = DOCS / "data" / "calendar.json"
        print(f"· 공개 페이지 일정 받기 실패({e}) → 이 PC의 {p.relative_to(ROOT)} 사용")
        cal = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"events": []}
    return cal.get("events", [])


def merge(events: list[dict], ff: list[dict], today: str) -> list[dict]:
    """우리 일정(미국) 중 같은 한국시간 날짜·시각의 ForexFactory 항목을 붙이고, 남는 중요 항목은 별도 줄로."""
    rows = []
    for e in ff:
        if e.get("country") != "USD" or e.get("impact") not in ("High", "Medium"):
            continue
        dt = datetime.fromisoformat(e["date"]).astimezone(KST)
        rows.append({"date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M"),
                     "name": ko(e["title"]), "prev": e.get("previous") or "", "fc": e.get("forecast") or "",
                     "importance": 3 if e["impact"] == "High" else 2})
    used = set()
    out = [dict(e) for e in events if e["date"] >= today]
    for ev in out:
        if ev.get("country") != "US":
            continue
        hits = [i for i, r in enumerate(rows) if r["date"] == ev["date"] and r["time"] == ev.get("time")]
        if hits:
            hits.sort(key=lambda i: ("근원" in rows[i]["name"], rows[i]["name"]))   # 헤드라인 먼저, 근원 다음
            ev["ff"] = [{"name": rows[i]["name"], "prev": rows[i]["prev"], "fc": rows[i]["fc"]} for i in hits]
            used.update(hits)
    for i, r in enumerate(rows):
        if i in used or r["date"] < today:
            continue
        out.append({"date": r["date"], "time": r["time"], "country": "US", "event": r["name"], "importance": r["importance"],
                    "extra": True, "ff": [{"name": "", "prev": r["prev"], "fc": r["fc"]}] if (r["prev"] or r["fc"]) else []})
    out.sort(key=lambda e: (e["date"], e.get("time") or "99:99"))
    return out


def free_port(start: int = 8000) -> int:
    for port in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("비어 있는 포트를 찾지 못했습니다")


def main() -> int:
    LOCAL.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    today, until = now.strftime("%Y-%m-%d"), (now + timedelta(days=21)).strftime("%Y-%m-%d")
    print("[내 PC 전용 보기] 준비 중…")
    events = merge(load_calendar(), load_ff(), today)
    events = [e for e in events if e["date"] <= until]
    (LOCAL / "calendar_local.json").write_text(json.dumps(
        {"updated_at": now.strftime("%Y-%m-%d %H:%M"), "source": "ForexFactory 이번 주 일정 내보내기 (개인 이용)", "events": events},
        ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(1 for e in events if e.get("ff"))
    print(f"· 컨센서스가 붙은 일정 {n}건 → docs/local/calendar_local.json (GitHub에 안 올라감)")

    port = free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(DOCS))
    handler.log_message = lambda *a, **k: None          # 접속 로그 숨김
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)   # 이 PC에서만 접속 가능
    url = f"http://127.0.0.1:{port}/#calendar"
    print(f"\n열기: {url}\n(창을 닫아도 이 프로그램은 계속 실행됩니다. 끝내려면 이 창에서 Ctrl + C)\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
