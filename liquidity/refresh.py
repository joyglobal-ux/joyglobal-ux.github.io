"""유동성 트래커 — FRED 수집/지표화 엔진 (키 불필요).

반도체 사이클 트래커와 같은 철학: 지표를 각각 그대로 추적하고,
그 위에 규칙 기반 통합 해석(순풍/혼조/역풍) 한 층. 점수 합산 없음.

지표 4개 (전부 FRED fredgraph.csv, 무료·무키):
  net_liquidity : Fed 순유동성 = WALCL − TGA(WTREGEN) − RRP(RRPONTSYD), $T 주간
  m2_yoy        : M2 통화량 YoY (M2SL, 월간)
  hy_oas        : 하이일드 스프레드 (BAMLH0A0HYM2, bp) — 크레딧 스트레스
  nfci          : 시카고연은 금융여건지수 (NFCI) — 0보다 낮을수록 완화

사용: python3 refresh.py  (의존성: requests 뿐)
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import requests

HERE = Path(__file__).parent
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
WEEKS = 156  # 스파크라인 3년


def _log(m: str) -> None:
    print(m, file=sys.stderr)


def fetch_series(sid: str) -> list[tuple[str, float]]:
    """FRED CSV → [(YYYY-MM-DD, value)] 오름차순. 결측('.')은 스킵."""
    r = requests.get(FRED_CSV.format(sid=sid), timeout=30)
    r.raise_for_status()
    rows = list(csv.reader(StringIO(r.text)))
    out = []
    for row in rows[1:]:
        if len(row) >= 2 and row[1] not in ("", "."):
            out.append((row[0], float(row[1])))
    if not out:
        raise RuntimeError(f"{sid}: empty series")
    return out


def asof_value(series: list[tuple[str, float]], date: str) -> float | None:
    """date 이하의 가장 최근 값 (일간→주간 정렬용)."""
    v = None
    for t, x in series:
        if t <= date:
            v = x
        else:
            break
    return v


def weekly_last(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """일간 시계열 → ISO 주 마지막 관측치만."""
    out, cur_key = [], None
    for t, v in series:
        y, w, _ = datetime.strptime(t, "%Y-%m-%d").isocalendar()
        key = (y, w)
        if key == cur_key:
            out[-1] = (t, v)
        else:
            out.append((t, v))
            cur_key = key
    return out


def momentum(hist: list[dict], good_dir: int, eps: float, lookback: int = 13) -> dict | None:
    """방향 판정: d1(직전), dN(lookback 구간). good_dir=+1 이면 상승=우호."""
    if len(hist) < lookback + 1:
        return None
    vs = [p["v"] for p in hist]
    d1 = vs[-1] - vs[-2]
    dN = vs[-1] - vs[-1 - lookback]
    e1, eN = d1 * good_dir, dN * good_dir
    if eN > eps and e1 >= -eps:
        phase, tone = "우호 지속", "pos"
    elif eN > eps:
        phase, tone = "우호 둔화", "warn"  # 추세는 우호인데 직전 꺾임
    elif eN < -eps and e1 <= eps:
        phase, tone = "역풍", "neg"
    elif eN < -eps:
        phase, tone = "역풍 완화", "warn-pos"
    else:
        phase, tone = "중립", "neutral"
    return {"phase": phase, "tone": tone, "d1": round(d1, 3), "dN": round(dN, 3), "lookback": lookback}


DRAIN_ALERT_T = -0.15  # $T — 순유동성 주간 급배수 경보 임계치 (2026-04-22 -0.25$T 사례 기준)


def drain_alert(mom: dict | None) -> dict | None:
    """직전주 순유동성이 임계치 이상 빠지면 13주 추세와 무관하게 경보.

    2026-04 세금시즌 드레인(-253B/주)처럼 추세 판정(13주)이 평활해서 놓치는
    단발 급배수를 잡는다. 원인 후보: 세금납부 시즌 TGA 급증(4/15·6/15·9/15·1/15),
    부채한도 후 TGA 리빌드, QT 가속.
    """
    if not mom or mom["d1"] > DRAIN_ALERT_T:
        return None
    return {
        "tone": "neg",
        "text": f"주간 급배수 {mom['d1']:+.2f}$T — 추세와 무관한 단발 경보. "
                f"원인 확인: 세금시즌 TGA 급증 / TGA 리빌드 / QT 가속",
    }


def build() -> dict:
    _log("=== 유동성 데이터 수집 (FRED) ===")
    walcl = fetch_series("WALCL")        # $M, 주간(수)
    tga = fetch_series("WTREGEN")        # $M, 주간(수) — FRED 단위 주의: millions
    rrp = fetch_series("RRPONTSYD")      # $B, 일간
    m2 = fetch_series("M2SL")            # $B, 월간
    hy = fetch_series("BAMLH0A0HYM2")    # %, 일간
    nfci = fetch_series("NFCI")          # 지수, 주간

    # 1) 순유동성 ($T) — WALCL 주간 날짜 기준으로 TGA/RRP 정렬
    nl_hist = []
    for t, w in walcl[-(WEEKS + 5):]:
        tg, rp = asof_value(tga, t), asof_value(rrp, t)
        if tg is None or rp is None:
            continue
        nl_hist.append({"t": t, "v": round(w / 1e6 - tg / 1e6 - rp / 1e3, 3)})
    nl_hist = nl_hist[-WEEKS:]
    nl_mom = momentum(nl_hist, good_dir=+1, eps=0.05, lookback=13)  # 13주≈3개월, $50B
    _log(f"  순유동성: {nl_hist[-1]['v']}$T ({nl_hist[-1]['t']}) {nl_mom and nl_mom['phase']}")

    # 2) M2 YoY (%)
    m2_hist = []
    for k in range(12, len(m2)):
        t, v = m2[k]
        m2_hist.append({"t": t[:7], "v": round((v / m2[k - 12][1] - 1) * 100, 2)})
    m2_hist = m2_hist[-36:]
    m2_mom = momentum(m2_hist, good_dir=+1, eps=0.2, lookback=3)  # 월간 → 3개월
    _log(f"  M2 YoY: {m2_hist[-1]['v']}% ({m2_hist[-1]['t']}) {m2_mom and m2_mom['phase']}")

    # 3) HY OAS (bp) — 주간 다운샘플
    hy_w = weekly_last(hy)
    hy_hist = [{"t": t, "v": round(v * 100)} for t, v in hy_w][-WEEKS:]
    hy_mom = momentum(hy_hist, good_dir=-1, eps=15, lookback=13)  # 스프레드 축소=우호
    _log(f"  HY OAS: {hy_hist[-1]['v']}bp ({hy_hist[-1]['t']}) {hy_mom and hy_mom['phase']}")

    # 4) NFCI — 낮을수록 완화 (0 = 역사 평균)
    nfci_hist = [{"t": t, "v": round(v, 3)} for t, v in nfci][-WEEKS:]
    nfci_mom = momentum(nfci_hist, good_dir=-1, eps=0.03, lookback=13)
    _log(f"  NFCI: {nfci_hist[-1]['v']} ({nfci_hist[-1]['t']}) {nfci_mom and nfci_mom['phase']}")

    indicators = [
        {
            "id": "net_liquidity", "label": "Fed 순유동성", "unit": "$T",
            "role": "WALCL − TGA − RRP · 위험자산의 물때", "decimals": 2,
            "source": "FRED · WALCL/WTREGEN/RRPONTSYD",
            "sourceUrl": "https://fred.stlouisfed.org/series/WALCL",
            "links": [
                {"label": "WALCL", "url": "https://fred.stlouisfed.org/series/WALCL"},
                {"label": "TGA", "url": "https://fred.stlouisfed.org/series/WTREGEN"},
                {"label": "RRP", "url": "https://fred.stlouisfed.org/series/RRPONTSYD"},
            ],
            "value": nl_hist[-1]["v"], "asOf": nl_hist[-1]["t"],
            "history": nl_hist, "mom": nl_mom,
            "alert": drain_alert(nl_mom),
            "deltaNote": "13주 Δ {dN:+.2f}$T · 직전주 {d1:+.2f}",
        },
        {
            "id": "m2_yoy", "label": "M2 통화량", "unit": "% YoY",
            "role": "광의 유동성 증가율 · 느리지만 구조적", "decimals": 1,
            "source": "FRED · M2SL",
            "sourceUrl": "https://fred.stlouisfed.org/series/M2SL",
            "value": m2_hist[-1]["v"], "asOf": m2_hist[-1]["t"],
            "history": m2_hist, "mom": m2_mom,
            "deltaNote": "3개월 Δ {dN:+.1f}%p · 직전월 {d1:+.1f}",
        },
        {
            "id": "hy_oas", "label": "하이일드 스프레드", "unit": "bp",
            "role": "크레딧 스트레스 · 급등 = 리스크오프 (역방향: 낮을수록 우호)", "decimals": 0,
            "source": "FRED · BAMLH0A0HYM2",
            "sourceUrl": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
            "value": hy_hist[-1]["v"], "asOf": hy_hist[-1]["t"],
            "history": hy_hist, "mom": hy_mom,
            "deltaNote": "13주 Δ {dN:+.0f}bp · 직전주 {d1:+.0f}",
        },
        {
            "id": "nfci", "label": "금융여건지수 NFCI", "unit": "",
            "role": "시카고연은 종합 여건 · 0 아래 = 평균보다 완화 (역방향)", "decimals": 2,
            "source": "FRED · NFCI",
            "sourceUrl": "https://fred.stlouisfed.org/series/NFCI",
            "value": nfci_hist[-1]["v"], "asOf": nfci_hist[-1]["t"],
            "history": nfci_hist, "mom": nfci_mom,
            "deltaNote": "13주 Δ {dN:+.2f} · 직전주 {d1:+.2f}",
        },
    ]
    for ind in indicators:
        m = ind["mom"]
        ind["momLine"] = ind.pop("deltaNote").format(dN=m["dN"], d1=m["d1"]) if m else ""

    # 통합 해석 — 우호(pos/warn-pos 아님: eN>0) 카운트
    def supportive(ind):
        return ind["mom"] and ind["mom"]["phase"] in ("우호 지속", "우호 둔화")

    sup = sum(1 for i in indicators if supportive(i))
    cooling = [i["label"] for i in indicators if i["mom"] and i["mom"]["phase"] == "우호 둔화"]
    against = [i["label"] for i in indicators if i["mom"] and i["mom"]["phase"] in ("역풍",)]
    alerts = [{"label": i["label"], "text": i["alert"]["text"]} for i in indicators if i.get("alert")]
    if sup >= 3 and not against:
        regime, regimeEn, tone = "유동성 순풍", "Tailwind", "pos"
    elif sup >= 2:
        regime, regimeEn, tone = "혼조", "Mixed", "warn"
    else:
        regime, regimeEn, tone = "유동성 역풍", "Headwind", "neg"
    headline = f"지표 4개 중 우호 {sup}개 → {regime}."
    if cooling:
        headline += f"  ⚠ 둔화 감시: {', '.join(cooling)}."
    if against:
        headline += f"  ✖ 역풍: {', '.join(against)}."
    if alerts:
        headline += f"  🚨 급배수 경보: {', '.join(a['label'] for a in alerts)}."

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "indicators": indicators,
        "interpretation": {
            "regime": regime, "regimeEn": regimeEn, "tone": tone,
            "headline": headline, "supportive": sup, "alerts": alerts,
            "bullets": [
                {"label": i["label"], "value": i["value"], "unit": i["unit"],
                 "phase": i["mom"]["phase"] if i["mom"] else "", "tone": i["mom"]["tone"] if i["mom"] else "neutral"}
                for i in indicators
            ],
        },
        "note": "판정은 레벨이 아니라 13주(월간은 3개월) 방향. HY·NFCI는 역방향(하락=우호). 순유동성 단위 $T.",
    }


def main() -> None:
    payload = build()
    (HERE / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "data.js").write_text("window.LIQ_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    _log(f"완료 → {payload['interpretation']['regime']} · {payload['interpretation']['headline']}")


if __name__ == "__main__":
    main()
