# market-info

매일 자동으로 업데이트되는 투자정보 페이지 (거시지표 대시보드 · 공모주 캘린더).

👉 **https://jangjiwoong0520.github.io/market-info/**

- 데이터 수집: GitHub Actions (평일 하루 2회)
- 화면: GitHub Pages (`docs/` 폴더)
- 데이터 출처: 한국은행 ECOS, FRED, 브라질 중앙은행·국고청, 관세청 등 — 각 지표에 출처와 기준일 표시

> 본 페이지의 정보는 참고용이며, 투자 판단의 책임은 투자자 본인에게 있습니다.

## 내 PC 전용 보기 (컨센서스 포함)

주요 일정에 ForexFactory 이번 주 컨센서스(이전·예상)를 붙여서 **내 PC에서만** 본다.
결과는 `docs/local/`에만 저장되고 GitHub에 올라가지 않으며, 화면은 이 PC(127.0.0.1)에서만 열린다.
받은 컨센서스는 공개 페이지·고객 자료에 옮기지 않는다 (ForexFactory 약관상 재배포 금지).

```powershell
python local_view.py
```
