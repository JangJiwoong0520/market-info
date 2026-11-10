"""임시 점검용 (확인 후 삭제)."""
import json, re, urllib.request, urllib.parse
from datetime import date, timedelta
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "ko-KR,ko;q=0.9"}
def req(url, data=None, extra=None):
    h = dict(UA); h.update(extra or {})
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=30) as r:
            b = r.read(); print(f"\n=== {'POST' if data else 'GET'} {url} {data or ''}\n    HTTP {r.status} {r.headers.get('content-type')} {len(b)}B"); return b.decode('utf-8','replace')
    except Exception as e:
        print(f"\n=== {url}\n    ERROR {e}"); return ""
def text(s, n=1500):
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', s, flags=re.S); t = re.sub(r'<[^>]+>', ' ', t); t = re.sub(r'\s+', ' ', t); print("    TEXT:", t[:n])
t = date.today(); f, e = t.isoformat(), (t + timedelta(days=21)).isoformat()
ref = {"Referer": "https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain&gubun=iRMaterials", "X-Requested-With": "XMLHttpRequest"}
# 메인 페이지의 스크립트에서 조회 함수 단서
s = req("https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain&gubun=iRMaterials")
for m in re.finditer(r'function\s+(fnSearch|search\w*|goSearch\w*)\s*\([^)]*\)\s*\{(.{0,900})', s, re.S):
    print("    JS", m.group(1), re.sub(r'\s+', ' ', m.group(2))[:900])
print("    hidden:", re.findall(r'<input[^>]+type="hidden"[^>]*>', s)[:25])
for data in [
    {"method": "searchIRScheduleSub", "forward": "irschedule_sub", "currentPageSize": "100", "pageIndex": "1", "orderMode": "1", "orderStat": "A", "searchFromDate": f, "searchToDate": e, "fromDate": f, "toDate": e, "marketType": "", "searchCodeType": "", "searchCorpName": "", "gubun": "iRMaterials"},
    {"method": "searchIRScheduleSub", "forward": "irschedule_sub", "currentPageSize": "100", "pageIndex": "1", "searchFromDate": f, "searchToDate": e},
]:
    text(req("https://kind.krx.co.kr/corpgeneral/irschedule.do", data, ref), 1800)
# StockHub 한국 공포탐욕 이력
for u in ["https://stockhub.kr/api/fear-greed/history", "https://stockhub.kr/api/fear-greed/history?market=kr", "https://stockhub.kr/api/composite-gauge"]:
    b = req(u, extra={"Accept": "application/json", "Referer": "https://stockhub.kr/fear-greed"}); print("   ", b[:900].replace("\n", " "))
c = req("https://stockhub.kr/_next/static/chunks/app/fear-greed/page-ea5b37fd788b74d6.js")
i = c.find("/api/fear-greed/history"); print("    JS around:", c[max(0,i-700):i+500])
