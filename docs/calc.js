/* R·수량 계산 로직 (화면 코드와 분리)
 * - 브라우저: window.Sizing.calc(...)
 * - node 테스트: require("./calc.js").calc(...)
 * - 같은 테스트 케이스(tests/sizing_cases.json)로 나중에 Python core/sizing.py도 검증한다.
 * 이 파일에는 계산 공식만 있다. 계좌금액 등 개인 값은 여기에 넣지 않는다.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Sizing = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // 부동소수점 오차 때문에 499.9999999 → 499 가 되는 것을 막는 내림
  // (예: 10.30 − 10.10 = 0.20000000000000107)
  function floorSafe(x) {
    return Math.floor(x + 1e-9 * Math.max(1, Math.abs(x)));
  }

  function pos(v) { return typeof v === "number" && isFinite(v) && v > 0; }

  /**
   * @param {object} p
   *  account   계좌금액(원)
   *  riskPct   1회 허용손실 % (예: 1)
   *  maxPct    최대 비중 % (예: 20)
   *  market    "kr"(원화 가격) | "us"(달러 가격)
   *  fx        원/달러 환율 (market="us"일 때만 사용)
   *  side      "long" | "short"
   *  entry     진입가 (가격 통화)
   *  stop      손절가 (가격 통화)
   *  targets   목표가 배열 (가격 통화, 빈칸은 null)
   * @returns 결과 객체. ok=false면 errors에 코드 목록.
   *  금액(unit, cost, actualRisk, profit 등)은 모두 원화. 가격 통화 값은 *Px 로 표시.
   */
  function calc(p) {
    var errors = [], warnings = [];
    var market = p.market === "us" ? "us" : "kr";
    var side = p.side === "short" ? "short" : "long";

    if (!pos(p.account)) errors.push("account_invalid");
    if (!pos(p.riskPct) || p.riskPct > 100) errors.push("risk_pct_invalid");
    if (!pos(p.maxPct) || p.maxPct > 100) errors.push("max_pct_invalid");
    if (market === "us" && !pos(p.fx)) errors.push("fx_invalid");
    if (!pos(p.entry)) errors.push("entry_invalid");
    if (!pos(p.stop)) errors.push("stop_invalid");

    var out = { ok: false, market: market, side: side, errors: errors, warnings: warnings };
    if (errors.length) return out;

    var fx = market === "us" ? p.fx : 1;
    var riskPx = side === "long" ? p.entry - p.stop : p.stop - p.entry;   // 1R (가격 통화)
    if (!(riskPx > 0)) { errors.push("stop_wrong_side"); return out; }

    var riskPerShare = riskPx * fx;                         // 1R (원)
    var unit = p.account * p.riskPct / 100;                 // 1unit = 허용손실 금액 (원)
    var maxCost = p.account * p.maxPct / 100;               // 최대 투입금액 (원)
    var entryKrw = p.entry * fx;

    var qtyRisk = floorSafe(unit / riskPerShare);           // 위험 기준 수량
    var qtyMax = floorSafe(maxCost / entryKrw);             // 최대 비중 기준 수량
    var capped = qtyMax < qtyRisk;
    var qty = capped ? qtyMax : qtyRisk;

    out.riskPx = riskPx;
    out.riskPerShare = riskPerShare;
    out.riskPctOfEntry = riskPx / p.entry * 100;            // 손절폭 %
    out.unit = unit;
    out.maxCost = maxCost;
    out.qtyRisk = qtyRisk;
    out.qtyMax = qtyMax;
    out.capped = capped;

    if (qtyRisk === 0) errors.push("qty_zero_risk");        // 1unit < 1R
    else if (qtyMax === 0) errors.push("qty_zero_max");     // 최대 비중으로 1주도 안 됨
    if (capped && qty > 0) warnings.push("capped_by_max");

    out.qty = qty;
    out.costPx = qty * p.entry;
    out.cost = qty * entryKrw;
    out.weight = out.cost / p.account * 100;
    out.actualRisk = qty * riskPerShare;
    out.actualRiskPct = out.actualRisk / p.account * 100;

    out.targets = (p.targets || []).map(function (t) {
      if (!pos(t)) return null;
      var movePx = side === "long" ? t - p.entry : p.entry - t;
      var r = movePx / riskPx;
      if (!(movePx > 0)) warnings.push("target_wrong_side");
      return { price: t, r: r, profitPx: qty * movePx, profit: qty * movePx * fx };
    });

    out.ok = errors.length === 0;
    return out;
  }

  // 화면에 보여줄 한국어 안내
  var MESSAGES = {
    account_invalid: "계좌금액을 0보다 큰 숫자로 입력하세요.",
    risk_pct_invalid: "허용손실 %는 0보다 크고 100 이하여야 합니다.",
    max_pct_invalid: "최대 비중 %는 0보다 크고 100 이하여야 합니다.",
    fx_invalid: "환율을 0보다 큰 숫자로 입력하세요.",
    entry_invalid: "진입가를 0보다 큰 숫자로 입력하세요.",
    stop_invalid: "손절가를 0보다 큰 숫자로 입력하세요.",
    stop_wrong_side: "손절가 위치가 잘못됐어요. 롱은 손절가 < 진입가, 숏은 손절가 > 진입가여야 합니다.",
    qty_zero_risk: "허용손실 금액(1unit)이 1주당 위험(1R)보다 작아서 1주도 살 수 없어요. 손절폭을 줄이거나 허용손실 %를 확인하세요.",
    qty_zero_max: "최대 비중 안에서는 1주도 살 수 없어요(주가가 최대 투입금액보다 큼).",
    capped_by_max: "최대 비중을 넘어서 수량을 줄였어요. 실제 위험금액이 허용손실보다 작습니다.",
    target_wrong_side: "목표가가 진입가의 반대쪽에 있어요(손실 방향). 값을 확인하세요."
  };

  return { calc: calc, floorSafe: floorSafe, MESSAGES: MESSAGES };
});
