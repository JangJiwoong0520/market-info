"""임시 점검용 (확인 후 삭제)."""
import re, urllib.request, urllib.parse
from datetime import date, timedelta
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "ko-KR,ko;q=0.9"}
def req(url, data=None, extra=None):
    h = dict(UA); h.update(extra or {}); body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=30) as r:
            b = r.read(); print(f"\n=== {'POST' if data else 'GET'} {url} {data or ''}\n    HTTP {r.status} {len(b)}B"); return b.decode('utf-8','replace')
    except Exception as e: print(f"\n=== {url}\n    ERROR {e}"); return ""
def text(s, n=1800):
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', s, flags=re.S); t = re.sub(r'<[^>]+>', ' ', t); t = re.sub(r'\s+', ' ', t); print("    TEXT:", t[:n])
t = date.today(); f, e = t.isoformat(), (t + timedelta(days=21)).isoformat()
for g in ["iRSchedule", "irSchedule", ""]:
    s = req(f"https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain&gubun={g}")
    for m in re.finditer(r'\$\("#searchForm > #method"\)\.val\("(\w+)"\);\s*\$\("#searchForm > #forward"\)\.val\("(\w+)"\)', s):
        print("    search method/forward:", m.groups())
    print("    tabs:", sorted(set(re.findall(r'gubun=(\w+)', s))))
ref = {"Referer": "https://kind.krx.co.kr/corpgeneral/irschedule.do?method=searchIRScheduleMain&gubun=iRSchedule", "X-Requested-With": "XMLHttpRequest"}
for m, fw in [("searchIRScheduleSub", "searchirschedule_sub"), ("searchIRScheduleSub", "irschedule_sub")]:
    text(req("https://kind.krx.co.kr/corpgeneral/irschedule.do", {"method": m, "forward": fw, "currentPageSize": "100", "pageIndex": "1",
         "fromDate": f, "toDate": e, "searchFromDate": f, "searchToDate": e, "marketType": "", "searchCorpName": "", "searchCodeType": "", "repIsuSrtCd": ""}, ref))
