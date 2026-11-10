"""임시 점검용 (확인 후 삭제)."""
import json, re, urllib.request, urllib.parse
from datetime import date, timedelta
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9"}
def req(url, data=None, extra=None):
    h = dict(UA); h.update(extra or {})
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=30) as r:
            b = r.read(); print(f"\n=== {'POST' if data else 'GET'} {url} {data or ''}\n    HTTP {r.status} {r.headers.get('content-type')} {len(b)}B"); return b.decode('utf-8','replace')
    except Exception as e:
        print(f"\n=== {url}\n    ERROR {e}"); return ""
def text(s, n=1200):
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', s, flags=re.S); t = re.sub(r'<[^>]+>', ' ', t); t = re.sub(r'\s+', ' ', t)
    print("    TEXT:", t[:n])

t = date.today()
# KIND IR 일정: 메인 페이지에서 폼·스크립트 단서
s = req("https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain&gubun=iRMaterials")
print("    forms/methods:", sorted(set(re.findall(r'method=([A-Za-z]+)', s)))[:20])
print("    inputs:", sorted(set(re.findall(r'name="([A-Za-z_]+)"', s)))[:40])
for m in ["searchIRScheduleSub", "searchIRScheduleList"]:
    s2 = req("https://kind.krx.co.kr/corpgeneral/irschedule.do", {"method": m, "currentPageSize": "15", "pageIndex": "1", "orderMode": "1", "orderStat": "D",
             "forward": "irschedule_sub", "fromDate": t.isoformat(), "toDate": (t + timedelta(days=21)).isoformat(), "marketType": ""},
             {"Referer": "https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain"})
    text(s2, 1500)
# KIND 공시 검색: 실적 관련 (결산실적공시예고)
s3 = req("https://kind.krx.co.kr/disclosure/todaydisclosure.do", {"method": "searchTodayDisclosureSub", "currentPageSize": "30", "pageIndex": "1",
         "orderMode": "0", "orderStat": "D", "forward": "todaydisclosure_sub", "chose": "S", "todayFlag": "Y", "selDate": t.isoformat()},
         {"Referer": "https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain"})
text(s3, 1200)
# StockHub 공포탐욕
s4 = req("https://stockhub.kr/fear-greed")
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s4, re.S)
print("    __NEXT_DATA__:", (m.group(1)[:1500] if m else "없음"))
print("    api refs:", sorted(set(re.findall(r'["\'](/api/[^"\']+|https?://[^"\']*(?:api|supabase|firebase)[^"\']*)["\']', s4)))[:20])
print("    chunks:", sorted(set(re.findall(r'/_next/static/chunks/(?:app/)?[^"\']*fear[^"\']*\.js', s4)))[:10])
idx = s4.find('공포'); print("    near 공포:", re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s4[idx-300:idx+800])) if idx >= 0 else "")
for js in sorted(set(re.findall(r'(/_next/static/chunks/[^"\']+\.js)', s4)))[:60]:
    c = req("https://stockhub.kr" + js) if 'fear' in js or 'page' in js else ""
    if c:
        print("    endpoints in", js, sorted(set(re.findall(r'["\'`](/api/[^"\'`]+|https?://[a-z0-9.\-]+/[^"\'`]*)["\'`]', c)))[:15])
