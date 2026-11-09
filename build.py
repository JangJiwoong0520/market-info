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

from collectors import brazil, customs, ecos, fred, yahoo
from collectors.common import CollectorError, parse_date, today_kst

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
LOGS = ROOT / "logs"
COLLECTORS = {"ecos": ecos, "fred": fred, "yahoo": yahoo, "bcb": brazil, "tesouro": brazil, "customs": customs}

log = logging.getLogger("market-info")


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
    if ind.get("cycle") == "M":                          # 월간 지표는 작아서 매번 전체
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
        incremental = old and not full and (ind.get("cycle") != "M" or ind["source"] == "customs")
        keep_old = old["series"] if incremental else []
        series = merge(keep_old, new)
        series = [s for s in series if s[0] >= cfg["history_start"][: len(s[0])]]
        nd = ind.get("decimals", 2) + 2
        series = [[k, round(v, nd)] for k, v in series]
        if ind.get("step"):
            series = compress_steps(series)
        obj = {**base, "as_of": series[-1][0], "updated_at": now_kst(), "status": "ok", "series": series}
        write_json(ind["id"], obj)
        return obj, None
    except Exception as e:  # noqa: BLE001 — 한 지표 실패가 전체를 멈추지 않게
        msg = f"{type(e).__name__}: {e}"
        if old:
            old.update({"status": "stale", "error": msg[:200], "checked_at": now_kst()})
            write_json(ind["id"], old)
            return old, msg
        return {**base, "as_of": None, "status": "failed", "error": msg[:200], "series": []}, msg


def collect_derived(ind: dict, cfg: dict, objs: dict) -> tuple[dict, str | None]:
    a_id, op, b_id = ind["formula"]
    a, b = objs.get(a_id), objs.get(b_id)
    src = cfg["sources"]["derived"]
    base = {"id": ind["id"], "name": ind["name"], "unit": ind.get("unit", ""), "source": src["name"], "source_url": ""}
    if not a or not b or not a["series"] or not b["series"]:
        old = read_json(ind["id"])
        return (old or {**base, "as_of": None, "status": "failed", "series": []}), f"계산 재료 없음 ({a_id}, {b_id})"
    bs = b["series"]
    out, j, last_b = [], 0, None
    for k, v in a["series"]:                    # b는 같은 날 또는 직전 5일 이내 값 사용
        while j < len(bs) and bs[j][0] <= k:
            last_b = bs[j]
            j += 1
        if last_b and (parse_date(k) - parse_date(last_b[0])).days <= 5 and last_b[1]:
            val = v / last_b[1] if op == "/" else v * last_b[1]
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
    elif kind == "macro":
        out["prev"] = s[-2][1] if len(s) > 1 else None
    elif kind == "export":
        ly = dict(s).get(f"{int(k[:4]) - 1}{k[4:]}")
        out["yoy"] = round((v / ly - 1) * 100, 1) if ly else None
    return out


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

    # manifest.json: 페이지와 일일 브리핑이 읽는 목록·요약
    today = today_kst()
    cal = [c for c in cfg.get("calendar") or []
           if today.isoformat() <= str(c["date"]) <= (today + timedelta(days=21)).isoformat()]
    manifest = {
        "site": cfg["site"],
        "periods": cfg["periods"],
        "ticker": [t for t in cfg["ticker"] if t in objs],
        "updated_at": now_kst(),
        "failed": failed,
        "calendar": sorted(cal, key=lambda c: (str(c["date"]), str(c.get("time", "")))),
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
