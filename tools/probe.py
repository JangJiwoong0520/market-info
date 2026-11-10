"""임시 점검용: 각 출처가 GitHub Actions에서 응답하는지, 응답 형식이 어떤지 확인 (확인 후 삭제)."""
import json, sys, urllib.request
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
today = date.today()

def get(url, extra=None, n=700):
    h = dict(UA); h.update(extra or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            body = r.read()
            print(f"\n=== {url}\n    HTTP {r.status} {r.headers.get('content-type')} {len(body)}B")
            return body
    except Exception as e:
        print(f"\n=== {url}\n    ERROR {e}")
        return b""

def show(b, n=700):
    print("   ", b[:n].decode("utf-8", "replace").replace("\n", " "))

b = get(f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{(today - timedelta(days=400)).isoformat()}",
        {"Referer": "https://edition.cnn.com/", "Origin": "https://edition.cnn.com"})
if b:
    try:
        d = json.loads(b); fg = d.get("fear_and_greed", {})
        print("    keys:", list(d.keys())); print("    fear_and_greed:", fg)
        h = d.get("fear_and_greed_historical", {}).get("data", [])
        print("    historical n=", len(h), "first", h[:1], "last", h[-1:])
    except Exception as e: show(b); print("    parse", e)

b = get("https://api.alternative.me/fng/?limit=3&format=json"); show(b, 400)
b = get("https://api.alternative.me/fng/?limit=0&format=json")
if b:
    d = json.loads(b); print("    crypto n=", len(d.get("data", [])), "oldest", d["data"][-1])

for dd in [today, today + timedelta(days=1)]:
    b = get(f"https://api.nasdaq.com/api/calendar/earnings?date={dd.isoformat()}", {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    if b:
        try:
            d = json.loads(b); rows = (d.get("data") or {}).get("rows") or []
            print("    rows", len(rows), "headers", (d.get("data") or {}).get("headers")); print("    sample", rows[:3])
        except Exception as e: show(b); print("    parse", e)

b = get("https://m.stock.naver.com/api/stock/005930/finance/quarter"); show(b, 1500)
b = get("https://m.stock.naver.com/api/stock/005930/integration"); show(b, 600)

b = get("https://stockhub.kr/"); show(b, 300)
import re
if b:
    s = b.decode("utf-8", "replace")
    print("    stockhub links:", sorted(set(re.findall(r'(?:href|src)="([^"]*(?:fear|greed|api|sentiment|공포)[^"]*)"', s, re.I)))[:20])
    print("    api-like:", sorted(set(re.findall(r'["\'](/api/[^"\']+|https?://[^"\']*api[^"\']*)["\']', s)))[:20])

b = get("https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain&gubun=iRMaterials"); show(b, 300)
