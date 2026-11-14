"""데이터 수집 → docs/data/*.json 생성.

사용법:
  python build.py                  # 전체 (기존 파일이 있으면 최근분만 추가)
  python build.py --only kr10y,spx # 일부 지표만
  python build.py --full           # 처음부터 전부 다시 받기
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from collectors import actuals, brazil, calendar, customs, earnings, ecos, fred, sentiment, treasury, yahoo
from collectors.common import CollectorError, mask, parse_date, today_kst

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
LOGS = ROOT / "logs"
COLLECTORS = {"ecos": ecos, "fred": fred, "yahoo": yahoo, "bcb": brazil, "tesouro": brazil, "customs": customs,
              "treasury": treasury, "cnn": sentiment, "alternative": sentiment,
              "stockhub": sentiment}

log = logging.getLogger("market-info")
KST = timezone(timedelta(hours=9))


# ── 준비 ──────────────────────────────────────────────────
def load_dotenv() -> None:
    """로컬 실행용: .env 파일의 KEY=VALUE를 환경변수로 읽는다 (GitHub Actions에서는 Secrets 사용)."""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def setup_logging() -> None:
    LOGS.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOGS / "build.log", "w", encoding="utf-8")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def now_kst() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")


# ── 파일 읽기/쓰기 ────────────────────────────────────────
def read_json(ind_id: str) -> dict | None:
    p = DATA / f"{ind_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def write_json(name: str, obj: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / f"{name}.json").write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ── 수집 기간 정하기 ──────────────────────────────────────
def fetch_window(ind: dict, old: dict | None, cfg: dict, full: bool) -> date:
    first = parse_date(cfg["history_start"])
    if ind.get("transform") == "yoy":                    # 전년비 계산용으로 1년 더
        first = first.replace(year=first.year - 1)
    if full or not old or not old.get("series"):
        return first
    if ind["source"] == "customs":                       # 매월 정정 반영: 최근 2년 다시
        last = old["series"][-1][0]
        return max(first, date(int(last[:4]) - 2, int(last[5:7]), 1))
    if ind.get("cycle") in ("M", "Q"):                   # 월간·분기 지표는 작아서 매번 전체
        return first
    return max(first, parse_date(old["series"][-1][0]) - timedelta(days=30))


def yoy(series: list[list]) -> list[list]:
    vals = dict(series)
    out = []
    for k, v in series:
        prev = vals.get(f"{int(k[:4]) - 1}{k[4:]}")
        if prev:
            out.append([k, round((v / prev - 1) * 100, 2)])
    return out


def merge(old: list[list], new: list[list]) -> list[list]:
    d = {k: v for k, v in old}
    d.update({k: v for k, v in new})
    return sorted([k, v] for k, v in d.items())


def compress_steps(series: list[list]) -> list[list]:
    """기준금리처럼 계단식인 시리즈는 값이 바뀐 날 + 마지막 날만 남긴다 (파일 크기 절감)."""
    out = []
    for i, (k, v) in enumerate(series):
        if not out or v != out[-1][1] or i == len(series) - 1:
            out.append([k, v])
    return out


def fill_latest(ind: dict, new: list[list], start: date) -> list[list]:
    """원 출처가 하루 늦게 올리는 지표(ECOS 코스피 등)의 빈 최근일을 Yahoo 값으로 잠정 채움.
    다음 실행에서 원 출처 값이 들어오면 그 값으로 덮어쓴다. 실패해도 원 출처 값은 그대로."""
    sym = ind.get("latest_from")
    if not sym:
        return []
    try:
        y = yahoo.fetch({"symbol": sym}, max(start, today_kst() - timedelta(days=10)), today_kst())
    except Exception as e:  # noqa: BLE001
        log.warning("  ✗ %s 최근일 보충 실패: %s", ind["id"], mask(str(e))[:120])
        return []
    last = new[-1][0] if new else ""
    out = [r for r in y if r[0] > last]
    if out:
        log.info("  + 최근일 Yahoo 잠정값: %s", ", ".join(r[0] for r in out))
    return out


# ── 지표 1개 수집 ─────────────────────────────────────────
def collect_one(ind: dict, cfg: dict, full: bool) -> tuple[dict, str | None]:
    old = read_json(ind["id"])
    src = cfg["sources"][ind["source"]]
    base = {
        "id": ind["id"], "name": ind["name"], "unit": ind.get("unit", ""),
        "source": src["name"], "source_url": src.get("url", ""),
    }
    try:
        start = fetch_window(ind, old, cfg, full)
        new = COLLECTORS[ind["source"]].fetch(ind, start, today_kst())
        if ind.get("transform") == "yoy":
            new = yoy(new)
        if not new:
            raise CollectorError("받은 데이터가 0건")
        incremental = old and not full and (ind.get("cycle") not in ("M", "Q") or ind["source"] == "customs")
        keep_old = old["series"] if incremental else []
        series = merge(keep_old, new)
        filled = fill_latest(ind, new, start)
        if filled:
            series = merge(series, filled)
        series = [s for s in series if s[0] >= cfg["history_start"][: len(s[0])]]
        nd = ind.get("decimals", 2) + 2
        series = [[k, round(v, nd)] for k, v in series]
        if ind.get("step"):
            series = compress_steps(series)
        if filled and series[-1][0] == filled[-1][0]:
            base["source"] += " (최근일 Yahoo 잠정)"
        obj = {**base, "as_of": series[-1][0], "updated_at": now_kst(), "status": "ok", "series": series}
        write_json(ind["id"], obj)
        return obj, None
    except Exception as e:  # noqa: BLE001 — 한 지표 실패가 전체를 멈추지 않게
        msg = mask(f"{type(e).__name__}: {e}")   # 키가 섞여 나오지 않게
        if old:
            old.update({"status": "stale", "error": msg[:200], "checked_at": now_kst()})
            write_json(ind["id"], old)
            return old, msg
        return {**base, "as_of": None, "status": "failed", "error": msg[:200], "series": []}, msg


def collect_derived(ind: dict, cfg: dict, objs: dict) -> tuple[dict, str | None]:
    a_id, op, b_id = ind["formula"]
    a, b = objs.get(a_id), objs.get(b_id)
    src = cfg["sources"]["derived"]
    base = {"id": ind["id"], "name": ind["name"], "unit": ind.get("unit", ""),
            "source": ind.get("source_name", src["name"]), "source_url": ""}
    if not a or not b or not a["series"] or not b["series"]:
        old = read_json(ind["id"])
        return (old or {**base, "as_of": None, "status": "failed", "series": []}), f"계산 재료 없음 ({a_id}, {b_id})"
    bs = b["series"]
    out, j, last_b = [], 0, None
    for k, v in a["series"]:                    # b는 같은 날 또는 직전 5일 이내 값 사용
        while j < len(bs) and bs[j][0] <= k:
            last_b = bs[j]
            j += 1
        if last_b and (parse_date(k) - parse_date(last_b[0])).days <= 5 and (last_b[1] or op != "/"):
            val = {"/": lambda x, y: x / y, "*": lambda x, y: x * y, "-": lambda x, y: x - y}[op](v, last_b[1])
            out.append([k, round(val, 4)])
    obj = {**base, "as_of": out[-1][0] if out else None, "updated_at": now_kst(),
           "status": "ok" if a["status"] == b["status"] == "ok" else "stale", "series": out}
    write_json(ind["id"], obj)
    return obj, None


# ── 요약 통계 (카드 상단 숫자) ────────────────────────────
def value_at_or_before(series: list[list], key: str):
    lo, hi, ans = 0, len(series) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= key:
            ans, lo = series[mid], mid + 1
        else:
            hi = mid - 1
    return ans


def change(kind: str, now: float, ref) -> float | None:
    if ref is None or ref[1] in (None, 0):
        return None
    if kind == "rate":
        return round((now - ref[1]) * 100, 1)          # bp
    return round((now / ref[1] - 1) * 100, 2)          # %


def summarize(ind: dict, obj: dict) -> dict:
    s = obj.get("series") or []
    if not s:
        return {}
    k, v = s[-1]
    kind = ind.get("kind", "level")
    out = {"date": k, "value": v}
    if kind in ("rate", "level"):
        d = parse_date(k)
        def key(dd: date) -> str: return dd.isoformat()
        if ind.get("step"):    # 계단식: 전일 값과 비교
            prev = value_at_or_before(s[:-1], key(d - timedelta(days=1)))
        else:
            prev = s[-2] if len(s) > 1 else None
        out["chg"] = {
            "1D": change(kind, v, prev),
            "1M": change(kind, v, value_at_or_before(s, key(d - timedelta(days=30)))),
            "1Y": change(kind, v, value_at_or_before(s, key(d.replace(year=d.year - 1)))),
            "YTD": change(kind, v, value_at_or_before(s, f"{d.year - 1}-12-31")),
        }
        out["prev_date"] = prev[0] if prev else None
    elif kind == "gauge":                                  # 공포·탐욕 (0~100): 과거 시점 값과 비교
        d = parse_date(k)
        def at(dd: date):
            r = value_at_or_before(s, dd.isoformat())
            if not r and s and (parse_date(s[0][0]) - dd).days <= 7:   # 이력이 막 시작된 경우 가장 가까운 값
                r = s[0]
            return r[1] if r else None
        out["cmp"] = {"1D": s[-2][1] if len(s) > 1 else None, "1W": at(d - timedelta(days=7)),
                      "1M": at(d - timedelta(days=30)), "1Y": at(d.replace(year=d.year - 1))}
    elif kind == "macro":
        out["prev"] = s[-2][1] if len(s) > 1 else None
    elif kind == "export":
        ly = dict(s).get(f"{int(k[:4]) - 1}{k[4:]}")
        out["yoy"] = round((v / ly - 1) * 100, 1) if ly else None
    out["spark"] = spark(ind, s)
    return out


def spark(ind: dict, s: list[list], n: int = 32) -> list:
    """즐겨찾기 표의 작은 추이선용: 일별은 최근 1달, 월간은 최근 2년 (최대 n개 값)."""
    if len(s[-1][0]) == 7:                                   # 월간
        vals = [x[1] for x in s[-24:]]
    else:
        cut = (parse_date(s[-1][0]) - timedelta(days=31)).isoformat()
        pts = [x for x in s if x[0] >= cut]
        if ind.get("step"):                                  # 계단식: 시작 시점 값 + 마지막 값
            before = value_at_or_before(s, cut)
            pts = ([before] if before else []) + pts
        vals = [x[1] for x in pts]
    if len(vals) > n:
        step = len(vals) / n
        vals = [vals[min(len(vals) - 1, round(i * step))] for i in range(n - 1)] + [vals[-1]]
    if len(vals) == 1:
        vals = vals * 2
    return [round(x, 4) for x in vals]


# ── 일정: 이전 값(우리 데이터) · 컨센서스(직접 입력) ──
def period_label(key: str, cycle: str | None) -> str:
    if len(key) == 7:                                  # YYYY-MM
        m = int(key[5:7])
        return f"{(m - 1) // 3 + 1}분기" if cycle == "Q" else f"{m}월"
    return ""                                          # 일별(기준금리 등)은 현재 수준


def attach_prev_consensus(events: list[dict], cfg: dict, inds: list[dict], objs: dict) -> None:
    by_id = {i["id"]: i for i in inds}
    cons = cfg.get("calendar_consensus") or []
    for e in events:
        pid = e.pop("prev_id", None)
        ind, obj = by_id.get(pid), objs.get(pid) or {}
        if ind and obj.get("series"):
            k, v = obj["series"][-1]
            dec = ind.get("decimals", 2)
            unit = {"%": "%", "천명": "천명"}.get(ind.get("unit", ""), "")
            e["prev"] = f"{v:,.{dec}f}{unit}"
            e["prev_label"] = " ".join(x for x in (period_label(k, ind.get("cycle")), e.pop("prev_note", "")) if x)
            e["prev_key"] = k                          # 이 값의 기준일 — 발표 후 '실제치' 판단에 사용
        else:
            e.pop("prev_note", None)
        for c in cons:
            if str(c.get("date")) == e["date"] and str(c.get("match", "")) in e["event"]:
                e["consensus"] = str(c["value"])


def event_passed(e: dict, now: datetime) -> bool:
    """한국시간 기준으로 발표 시각이 지났는지. 시각이 없으면 다음 날부터, '오전'은 정오부터."""
    t = e.get("time") or ""
    hhmm = t if len(t) == 5 and t[2] == ":" else ("12:00" if t == "오전" else None)
    if hhmm:
        return datetime.strptime(f"{e['date']} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=KST) <= now
    return e["date"] < now.strftime("%Y-%m-%d")


def freeze_past(events: list[dict], old_events: list[dict], now: datetime, week_start: str) -> list[dict]:
    """지난 일정 처리 ('이번 주' 보기용).
    - 이전 값: 발표 전에 저장해 둔 값으로 고정 (안 그러면 발표 뒤 '이전'에 새 발표치가 보임)
    - 실제치(ForexFactory 없는 일정): 우리 데이터의 최신 기준일이 이전 값보다 새로우면 그 값
    - ForexFactory 항목: 이번 실행에서 못 받았으면 지난번 저장분(실제치 포함)을 그대로 사용
    - 이번 실행에서 빠진 이번 주 지난 일정(ForexFactory 실패 등)은 지난번 저장분을 살림"""
    old = {(o["date"], o["event"]): o for o in old_events}
    seen = set()
    for e in events:
        key = (e["date"], e["event"])
        seen.add(key)
        if not event_passed(e, now):
            continue
        o = old.get(key) or {}
        if o.get("ff"):
            if not e.get("ff"):
                e["ff"] = o["ff"]
            else:
                prev_ff = {f.get("key") or f.get("name"): f for f in o["ff"]}
                for f in e["ff"]:
                    pf = prev_ff.get(f.get("key") or f.get("name")) or {}
                    if pf.get("act") and not f.get("act"):
                        f.update({k: pf[k] for k in ("act", "vs", "act_src") if k in pf})
        if "prev" in e:
            cur_key, cur_val = e.get("prev_key"), e.get("prev")
            if o.get("prev_key"):
                e["prev"], e["prev_label"], e["prev_key"] = o.get("prev", ""), o.get("prev_label", ""), o["prev_key"]
                if cur_key and cur_key > o["prev_key"]:
                    e["actual"] = cur_val
                    if e.get("consensus"):
                        e["vs"] = actuals.compare(cur_val, e["consensus"])
                elif o.get("actual"):
                    e["actual"] = o["actual"]
            else:                                         # 발표 전 저장분이 없으면 '이전'을 알 수 없음 → 비움
                for k in ("prev", "prev_label", "prev_key"):
                    e.pop(k, None)
    ff_now = {(e["date"], f.get("key") or f.get("name")) for e in events for f in (e.get("ff") or [])}
    for o in old_events:
        if week_start <= o["date"] and (o["date"], o["event"]) not in seen and event_passed(o, now):
            if any((o["date"], f.get("key") or f.get("name")) in ff_now for f in (o.get("ff") or [])):
                continue                                  # 같은 발표가 다른 이름 줄로 이미 있음
            events.append(o)
    events.sort(key=lambda e: (e["date"], e.get("time") or "99:99"))
    return events


# ── 메인 ──────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="쉼표로 구분한 지표 id")
    ap.add_argument("--full", action="store_true", help="처음부터 다시 받기")
    args = ap.parse_args()

    load_dotenv()
    setup_logging()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    inds = [i for i in cfg["indicators"] if i.get("public", True)]
    only = set(args.only.split(",")) if args.only else None

    # 비공개로 바뀐 지표의 옛 파일은 삭제 (공개 저장소에서 내리기)
    for i in cfg["indicators"]:
        if not i.get("public", True) and (DATA / f"{i['id']}.json").exists():
            (DATA / f"{i['id']}.json").unlink()
            log.info("비공개 전환 → 삭제: %s", i["id"])

    objs, failed, done = {}, [], 0
    for ind in inds:
        if ind["source"] == "derived":
            continue
        if only and ind["id"] not in only:
            objs[ind["id"]] = read_json(ind["id"]) or {}
            continue
        log.info("수집: %-12s (%s)", ind["id"], ind["source"])
        done += 1
        obj, err = collect_one(ind, cfg, args.full)
        objs[ind["id"]] = obj
        if err:
            failed.append({"id": ind["id"], "name": ind["name"], "error": err[:200]})
            log.warning("  ✗ 실패: %s", err[:200])
        else:
            log.info("  ✓ %d건, 기준일 %s", len(obj["series"]), obj["as_of"])

    for ind in inds:
        if ind["source"] == "derived":
            done += 1
            obj, err = collect_derived(ind, cfg, objs)
            objs[ind["id"]] = obj
            if err:
                failed.append({"id": ind["id"], "name": ind["name"], "error": err})
                log.warning("  ✗ %s 계산 실패: %s", ind["id"], err)
            else:
                log.info("계산: %-12s ✓ %d건, 기준일 %s", ind["id"], len(obj["series"]), obj["as_of"])

    # 1일(1D) 차트용 장중 데이터 (Yahoo 5분, 최근 24시간)
    intra, intra_err = {}, []
    for ind in inds:
        if ind.get("intraday"):
            try:
                intra[ind["id"]] = yahoo.fetch_intraday(ind["intraday"], float(ind.get("intraday_scale", 1)))
            except Exception as e:  # noqa: BLE001
                intra_err.append(ind["id"])
                log.warning("  ✗ 장중 %s: %s", ind["id"], mask(str(e))[:120])
    if intra:
        old_intra = (read_json("intraday") or {}).get("series", {})
        write_json("intraday", {"updated_at": now_kst(), "series": {**old_intra, **intra}})
        log.info("장중 데이터: %d개 지표%s", len(intra), f" (실패 {intra_err})" if intra_err else "")

    # manifest.json: 페이지와 일일 브리핑이 읽는 목록·요약
    today = today_kst()
    log.info("일정 수집")
    week_start = today - timedelta(days=today.weekday())          # 이번 주 월요일 ('이번 주' 보기)
    week_end = week_start + timedelta(days=6)
    events, cal_err = calendar.collect(cfg, today, since=week_start)
    for e in cal_err:
        failed.append({"id": "calendar", "name": "주요 일정", "error": mask(e)[:200]})
        log.warning("  ✗ %s", mask(e)[:200])
    if (cfg.get("calendar_auto") or {}).get("forexfactory"):
        try:                                               # ForexFactory 이번 주 컨센서스(이전·예상) 붙이기
            from local_view import FF_URL, merge as ff_merge
            from collectors.common import get as http_get
            ff = http_get(FF_URL, headers={"User-Agent": "market-info/1.0"}).json()
            events = ff_merge(events, ff, week_start.isoformat())
            log.info("  ✓ ForexFactory 컨센서스 %d건 연결", sum(1 for e in events if e.get("ff")))
        except Exception as e:  # noqa: BLE001
            failed.append({"id": "forexfactory", "name": "일정 컨센서스", "error": mask(str(e))[:200]})
            log.warning("  ✗ ForexFactory: %s", mask(str(e))[:200])
    attach_prev_consensus(events, cfg, inds, objs)
    now = datetime.now(KST)
    rules = cfg.get("calendar_actuals") or {}
    if rules:                                              # 발표된 美 지표의 실제치 (FRED에서 계산)
        try:
            n_act, act_err = actuals.attach(events, rules, now)
            log.info("  ✓ 실제치 %d건 (FRED)", n_act)
            for e in act_err:
                failed.append({"id": "actuals", "name": "일정 실제치", "error": mask(e)[:200]})
                log.warning("  ✗ 실제치 %s", mask(e)[:200])
        except Exception as e:  # noqa: BLE001
            failed.append({"id": "actuals", "name": "일정 실제치", "error": mask(str(e))[:200]})
            log.warning("  ✗ 실제치: %s", mask(str(e))[:200])
    old_cal = read_json("calendar") or {}
    events = freeze_past(events, (old_cal.get("week") or []) + (old_cal.get("events") or []), now, week_start.isoformat())
    week = [e for e in events if week_start.isoformat() <= e["date"] <= week_end.isoformat()]
    events = [e for e in events if e["date"] >= today.isoformat()]
    write_json("calendar", {"updated_at": now_kst(), "events": events,
                            "week_start": week_start.isoformat(), "week": week})
    cal = [e for e in events if e["date"] <= (today + timedelta(days=21)).isoformat()]

    # 실적발표 일정 (국내 KIND + 네이버 컨센서스, 미국 Nasdaq)
    earn_info = None
    if (cfg.get("earnings") or {}).get("enabled"):
        log.info("실적발표 일정 수집")
        earn, earn_err = earnings.collect(cfg, today)
        for e in earn_err:
            failed.append({"id": "earnings", "name": "실적발표", "error": mask(e)[:200]})
            log.warning("  ✗ %s", mask(e)[:200])
        old_earn = read_json("earnings") or {}
        for k in ("kr", "us"):                              # 실패한 쪽은 지난 데이터 유지
            if not earn[k] and old_earn.get(k):
                earn[k] = [r for r in old_earn[k] if r["date"] >= today.isoformat()]
        write_json("earnings", {"updated_at": now_kst(), **earn})
        earn_info = {"kr": len(earn["kr"]), "us": len(earn["us"]), "updated_at": now_kst()}
        log.info("  ✓ 국내 %d건(컨센서스 %d건), 미국 %d건", len(earn["kr"]),
                 sum(1 for r in earn["kr"] if r.get("op_cons") is not None), len(earn["us"]))
    log.info("  ✓ 일정 %d건 (3주 이내 %d건)", len(events), len(cal))
    manifest = {
        "site": cfg["site"],
        "periods": cfg["periods"],
        "ticker": [t for t in cfg["ticker"] if t in objs],
        "updated_at": now_kst(),
        "failed": failed,
        "calendar": cal,
        "calendar_week": {"start": week_start.isoformat(), "end": week_end.isoformat(), "events": week},
        "earnings": earn_info,
        "sources": cfg["sources"],
        "indicators": {
            i["id"]: {
                "name": i["name"], "short": i.get("short", i["name"]), "unit": i.get("unit", ""),
                "kind": i.get("kind", "level"), "decimals": i.get("decimals", 2),
                "source": objs.get(i["id"], {}).get("source", ""),
                "status": objs.get(i["id"], {}).get("status", "failed"),
                "hidden": i.get("hidden", False), "step": i.get("step", False),
                "summary": summarize(i, objs.get(i["id"], {})),
            } for i in inds
        },
        "sections": [
            {**sec, "cards": [
                {**c, "lines": [l for l in c.get("lines", [c["main"]]) if l in objs]}
                for c in sec.get("cards", []) if c["main"] in objs
            ]} for sec in cfg["sections"]
        ],
    }
    write_json("manifest", manifest)

    ok = done - len(failed)
    log.info("완료: 성공 %d / 실패 %d", ok, len(failed))
    for f in failed:
        log.info("  - %s(%s): %s", f["name"], f["id"], f["error"])
    return 1 if ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
