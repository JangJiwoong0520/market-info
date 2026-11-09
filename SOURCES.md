# 데이터 출처 확인 기록

> 실제 API 호출과 공식 페이지로 확인한 내용만 적는다. (확인일: 2026-11-09)
> 공개 게시: ✅ 가능 / ⚠️ 확인 필요·애매 / ❌ 불가

## 한국은행 ECOS — `https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/{시작}/{끝}/{통계표}/{주기}/{시작일}/{종료일}/{항목}`
연습용 키 `sample`(최대 10건)로 실제 호출해 확인함.

| 지표 | 통계표 | 항목코드 | 주기 | 단위 | 비고 |
|---|---|---|---|---|---|
| 한국은행 기준금리 | 722Y001 | 0101000 | D | 연% | 1999-05-06~ |
| 국고채 3년 | 817Y002 | 010200000 | D | 연% | |
| 국고채 10년 | 817Y002 | 010210000 | D | 연% | 2000-12-18~ |
| 국고채 30년 | 817Y002 | 010230000 | D | 연% | |
| 원/달러(매매기준율) | 731Y001 | 0000001 | D | 원 | 1964~ |
| 원/100엔 | 731Y001 | 0000002 | D | 원 | |
| 코스피 | 802Y001 | 0001000 | D | 지수 | 1995~ |
| 코스닥 | 802Y001 | 0089000 | D | 지수 | 2003~ |
| 소비자물가지수(총지수) | 901Y009 | 0 | M | 지수 | 전년비는 직접 계산 |

- 공개 게시: ⚠️ ECOS 이용약관 원문 확인 필요(인증키 신청 화면에서 확인, 이용형태는 "비영리" 선택).

## 브라질 중앙은행 SGS — `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{코드}/dados?formato=json&dataInicial=dd/mm/yyyy`
키 불필요. 실제 호출로 확인함. 날짜 형식은 `dd/mm/yyyy`, 값은 문자열.

| 지표 | SGS 코드 | 확인값 | 비고 |
|---|---|---|---|
| Selic 목표금리 | 432 | 13.75 | **미래 날짜(다음 회의 전까지)까지 채워져 있음 → 오늘 이후는 잘라낼 것** |
| 달러/헤알 (PTAX 매도) | 1 | 5.5013 (2026-11-06) | 원/헤알 = 원/달러 ÷ 이 값 |
| IPCA 12개월 누적 | 13522 | 4.58 (2026-09) | 월간 |

- 공개 게시: ⚠️ 중앙은행 공개 데이터. 이용조건 원문 추가 확인 예정.

## 브라질 국고청 Tesouro Direto — 금리 CSV
- 카탈로그: `https://www.tesourotransparente.gov.br/ckan/api/3/action/package_search?q=taxas tesouro direto`
- 데이터셋 "Taxas dos Títulos Ofertados pelo Tesouro Direto" → CSV(약 15MB, 전체 이력), 구분자 `;`, 소수점 `,`
- 컬럼: `Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;...`
- 10년 근사: `Tesouro Prefixado com Juros Semestrais`(NTN-F) 중 잔존만기 10년에 가장 가까운 종목 (예: 2026-11-06 기준 2037-01-01 만기, Taxa Venda 15.21)
- 공개 게시: ✅ 라이선스 ODbL(Open Data Commons) — 출처 표시 조건

## 관세청 품목별 수출입실적 (공공데이터포털)
- 페이지: https://www.data.go.kr/data/15101609/openapi.do — "관세청_품목별 수출입실적 (GW)"
- 서비스 주소: `https://apis.data.go.kr/1220000/Itemtrade` (세부 오퍼레이션은 키 발급 후 확인)
- HS 2·4·6·10단위, 무료, 개발계정 자동승인, 하루 10,000건
- 공개 게시: ✅ 이용허락범위 "제한 없음"
- 필요: 공공데이터포털 회원가입 → 위 페이지에서 "활용신청"

## FRED (미국 연준 세인트루이스) — 키 필요
각 시리즈 페이지의 저작권 표시를 확인함.

| 시리즈 | 원 출처 | 공개 게시 |
|---|---|---|
| DGS10 등 국채금리, DFEDTARU | 연준(Board of Governors) | ✅ 저작권 표시 없음 |
| CPIAUCSL, PAYEMS 등 고용·물가 | 美 노동통계국(BLS) | ✅ 저작권 표시 없음 |
| DCOILWTICO (WTI) | 美 에너지정보청(EIA) | ✅ 저작권 표시 없음 |
| SP500 (S&P500) | S&P Dow Jones Indices | ❌ "사전 서면 허락 없이 어떤 형태로도 복제 금지" |
| NASDAQCOM (나스닥) | Nasdaq, Inc. | ⚠️ 저작권 표시 있음, 명시적 금지 문구는 없음 |
| CBBTCUSD (비트코인) | Coinbase | ❌ "사전 서면 허락 없이 어떤 형태로도 복제 금지" |

## Yahoo Finance (yfinance) — S&P500(^GSPC), 나스닥(^IXIC), 금(GC=F), 비트코인(BTC-USD)
- ⚠️ 개인적·비상업적 이용 조건. 공개 페이지 게시는 재배포로 볼 여지가 있음.
- **사용자 결정(2026-11-09): 개인·비상업 목적이므로 야후 데이터 사용.**
- 대응: `config.yaml`에서 지표별 `public: false`로 바꾸면 다음 실행 때 공개 JSON에서 삭제됨.

## 추가 지표 (2026-11-09)
- 美 장단기 금리차(10년−2년): FRED DGS10 − DGS2 직접 계산 (FRED의 T10Y2Y와 같은 정의, 원자료는 연준 H.15)
- 달러인덱스(DXY): Yahoo `DX-Y.NYB` (ICE 지수, Yahoo 조건 — `public` 스위치로 끌 수 있음)

## 컨센서스(예상치) 조사 (2026-11-09)
- ForexFactory: 공식 안내(forexfactory.com/notices)에 "일정표(calendar schedules)를 포함한 콘텐츠의 복사·재게시·재배포는 사전 허락 없이 금지" 명시.
  사이트·robots.txt 모두 자동 접속을 보안 인증으로 차단(403). 주간 내보내기 피드(nfs.faireconomy.media)도 같은 회사 콘텐츠라 같은 조건으로 판단 → **공개 페이지에 사용하지 않음**.
- Investing.com: 자동 접속 차단(403).
- 현재: `config.yaml`의 `calendar_consensus`에 직접 입력 (공개 가능한 출처 값만).

## 주요 일정 (2026-11-09 확인)
| 일정 | 출처 | 방식 |
|---|---|---|
| 美 CPI·고용·PPI·소매판매·PCE·GDP 발표일 | FRED `fred/release/dates` (release_id 10·50·46·9·54·53, `include_release_dates_with_no_data=true`) | 자동 (FRED 달력 페이지 날짜와 대조 일치) |
| 브라질 Copom | 브라질 중앙은행 달력 API `api/servico/sitebcb/calendar?lista=Reuniões do Copom` ('Day 2'가 결정일) | 자동 |
| FOMC | federalreserve.gov/monetarypolicy/fomccalendars.htm (2026·2027) | 수동 (`config.yaml`) |
| 한은 금통위 | bok.or.kr 통화정책방향 결정회의 일정 (2026년분, 2027년 미공개) | 수동 (`config.yaml`) |

- 美 발표 시각은 동부시간 08:30(FOMC 14:00) → 한국시간 자동 변환(서머타임 반영)
- 할 일: 한은 2027년 일정 공개되면 `config.yaml`에 추가
