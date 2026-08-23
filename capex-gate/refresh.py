"""CAPEX 게이트 워치 — 크레딧 레이어 수집 엔진.

게이트 ①②③(실적·가이던스 판정)은 사람이 팩트 로그로 관리한다(index.html, append-only).
이 스크립트는 그 아래 깔리는 **숫자 레이어**만 자동 수집한다.

핵심 질문: "AI capex를 빚으로 조달하는 게 지속 가능한가" — 채권시장의 답.

지표 4개:
  ig_oas      : IG 회사채 스프레드 (FRED BAMLC0A0CM) — 하이퍼스케일러가 속한 등급대
  hy_oas      : HY 스프레드 (FRED BAMLH0A0HYM2) — 위험선호 전반
  ai_premium  : AI 크레딧 프리미엄 = ORCL 프록시 − MSFT 프록시 (bp)
                capex를 빚으로 조달하는 쪽 vs 현금으로 조달하는 쪽의 격차
  cds_activity: 단일종목 CDS 헤지 활동 (DTCC PPD) — AI capex 이름들에 붙은 주간 거래 건수

크레딧 프록시(중요): 실제 CDS 스프레드는 무료로 얻을 수 없다(Markit/S&P 유료).
그래서 **126일 실현변동성 → CDS 로그-로그 캘리브레이션**으로 프록시를 만든다.
2026-07-31 텔레그램에서 받은 실측 7개를 앵커로 적합 (R²=0.93, 평균오차 21%).
→ 레벨을 믿지 말고 **방향과 격차**를 봐라. 자세한 한계는 index.html "읽는 법" 참조.

사용: python3 refresh.py   (의존성: requests)
"""
from __future__ import annotations

import csv
import io
import json
import math
import statistics
import sys
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests

HERE = Path(__file__).parent
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
STOOQ_CSV = "https://stooq.com/q/d/l/?s={sym}.us&i=d"
YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{t}"
               "?range=5y&interval=1d")
DTCC_ZIP = ("https://pddata.dtcc.com/ppd/api/report/cumulative/sec/"
            "SEC_CUMULATIVE_CREDITS_{d:%Y_%m_%d}.zip")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

WEEKS = 156          # 스파크라인 3년
VOL_WIN = 126        # 실현변동성 창 (6개월) — 반응성과 적합도의 균형점
                     # 252일이 단면 적합은 더 좋지만(R²=.965) 레짐 변화 반영이 너무 느림

# 2026-07-31 실측 5Y CDS (텔레그램, 일회성) — 프록시 캘리브레이션 앵커.
# 지속 수신 불가라 이 값은 고정 상수로 둔다. 새 실측이 생기면 여기만 갱신.
CDS_ANCHOR = {
    "MSFT": 52.55, "GOOGL": 63.45, "AMZN": 64.23, "META": 94.82,
    "NVDA": 77.88, "ORCL": 206.88, "CRWV": 863.53,
}
ANCHOR_DATE = "2026-07-31"

NAMES = [
    {"t": "MSFT",  "label": "Microsoft", "role": "현금조달 · 기준점"},
    {"t": "GOOGL", "label": "Alphabet",  "role": "현금조달"},
    {"t": "AMZN",  "label": "Amazon",    "role": "현금조달"},
    {"t": "META",  "label": "Meta",      "role": "capex 급증 · 채권발행"},
    {"t": "NVDA",  "label": "NVIDIA",    "role": "공급측 · 무차입"},
    {"t": "ORCL",  "label": "Oracle",    "role": "🚨 부채조달 capex"},
    {"t": "CRWV",  "label": "CoreWeave", "role": "🚨 네오클라우드 · 고레버리지"},
]
# DTCC 매칭용 reference entity 이름 (UPI Underlier Name에 부분일치)
DTCC_ENTITIES = ["MICROSOFT", "ORACLE", "NVIDIA", "ALPHABET", "AMAZON",
                 "META PLATFORMS", "COREWEAVE", "BROADCOM", "APPLE INC"]


def _log(m: str) -> None:
    print(m, file=sys.stderr)


# ---------------------------------------------------------------- FRED
def fetch_fred(sid: str) -> list[tuple[str, float]]:
    r = requests.get(FRED_CSV.format(sid=sid), timeout=30, headers=UA)
    r.raise_for_status()
    out = []
    for row in list(csv.reader(StringIO(r.text)))[1:]:
        if len(row) >= 2 and row[1] not in ("", "."):
            out.append((row[0], float(row[1])))
    if not out:
        raise RuntimeError(f"{sid}: empty")
    return out


# ---------------------------------------------------------------- 주가
def fetch_closes(ticker: str) -> list[tuple[str, float]]:
    """일간 종가. Yahoo chart API 우선, 실패 시 Stooq 폴백.

    (Stooq는 봇 차단이 잦아 2순위. 둘 다 분할조정 종가.)
    """
    try:
        r = requests.get(YAHOO_CHART.format(t=ticker), timeout=30, headers=UA)
        r.raise_for_status()
        j = r.json()["chart"]["result"][0]
        ts, cl = j["timestamp"], j["indicators"]["quote"][0]["close"]
        out = [(date.fromtimestamp(t).strftime("%Y-%m-%d"), float(c))
               for t, c in zip(ts, cl) if c is not None]
        if len(out) > 200:
            return out
    except Exception as e:  # noqa: BLE001
        _log(f"    yahoo {ticker} 실패 ({e}) → stooq 폴백")
    r = requests.get(STOOQ_CSV.format(sym=ticker.lower()), timeout=30, headers=UA)
    r.raise_for_status()
    rows = [l.split(",") for l in r.text.strip().splitlines()[1:]]
    return [(x[0], float(x[4])) for x in rows
            if len(x) >= 5 and x[4] not in ("", "N/D")]


def rolling_vol(closes: list[tuple[str, float]], win: int) -> list[tuple[str, float]]:
    """연율화 실현변동성(%) 시계열."""
    rets = []
    for i in range(1, len(closes)):
        p0, p1 = closes[i - 1][1], closes[i][1]
        if p0 > 0 and p1 > 0:
            rets.append((closes[i][0], math.log(p1 / p0)))
    out = []
    for i in range(win, len(rets) + 1):
        seg = [r for _, r in rets[i - win:i]]
        out.append((rets[i - 1][0], statistics.pstdev(seg) * math.sqrt(252) * 100))
    return out


def calibrate(vols_now: dict[str, float]) -> tuple[float, float, dict]:
    """log(CDS) = a + b·log(vol) 을 실측 앵커에 적합."""
    pts = [(vols_now[t], c) for t, c in CDS_ANCHOR.items() if vols_now.get(t)]
    xs = [math.log(v) for v, _ in pts]
    ys = [math.log(c) for _, c in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    ssr = sum((ys[i] - (a + b * xs[i])) ** 2 for i in range(n))
    sst = sum((y - my) ** 2 for y in ys)
    errs = [abs(math.exp(a + b * xs[i]) / pts[i][1] - 1) * 100 for i in range(n)]
    fit = {"r2": round(1 - ssr / sst, 3), "mae": round(sum(errs) / n, 1),
           "a": a, "b": round(b, 3), "n": n, "anchorDate": ANCHOR_DATE}
    return a, b, fit


def proxy_bp(a: float, b: float, vol: float) -> float:
    return math.exp(a + b * math.log(vol))


# ---------------------------------------------------------------- DTCC
def dtcc_week_counts(weeks: int = 8) -> tuple[list[dict], str | None]:
    """AI capex 이름들에 붙은 단일종목 CDS 거래 건수 (주간).

    DTCC 공개 가격배포(PPD)는 가격 필드가 비어 있어 스프레드는 못 뽑지만,
    '누가 헤지되고 있나'라는 활동량은 읽힌다. 실측: Price 채움율 0%,
    빅테크 단일종목은 월 3~11건 수준 → 레벨이 아니라 추세로만 본다.
    """
    counts: dict[tuple[int, int], int] = {}
    d = date.today()
    got = 0
    need = weeks * 5
    last_seen = None
    while got < need and (date.today() - d).days < weeks * 11:
        if d.weekday() < 5:
            try:
                raw = requests.get(DTCC_ZIP.format(d=d), timeout=45, headers=UA)
                if raw.status_code == 200 and raw.content[:2] == b"PK":
                    z = zipfile.ZipFile(io.BytesIO(raw.content))
                    txt = z.read(z.namelist()[0]).decode("utf-8-sig", errors="replace")
                    y, w, _ = d.isocalendar()
                    counts.setdefault((y, w), 0)
                    for row in csv.DictReader(StringIO(txt)):
                        nm = (row.get("UPI Underlier Name") or "").upper()
                        if any(e in nm for e in DTCC_ENTITIES):
                            counts[(y, w)] += 1
                    got += 1
                    last_seen = last_seen or d.isoformat()
            except Exception:  # noqa: BLE001
                pass
        d -= timedelta(days=1)
    hist = [{"t": f"{y}-W{w:02d}", "v": c} for (y, w), c in sorted(counts.items())]
    return hist[-weeks:], last_seen


# ---------------------------------------------------------------- 판정
def momentum(hist: list[dict], good_dir: int, eps: float, lookback: int = 13) -> dict | None:
    """방향 판정. good_dir=-1 이면 하락=우호(스프레드류)."""
    if len(hist) < lookback + 1:
        return None
    vs = [p["v"] for p in hist]
    d1, dN = vs[-1] - vs[-2], vs[-1] - vs[-1 - lookback]
    e1, eN = d1 * good_dir, dN * good_dir
    if eN > eps and e1 >= -eps:
        phase, tone = "우호 지속", "pos"
    elif eN > eps:
        phase, tone = "우호 둔화", "warn"
    elif eN < -eps and e1 <= eps:
        phase, tone = "역풍", "neg"
    elif eN < -eps:
        phase, tone = "역풍 완화", "warn-pos"
    else:
        phase, tone = "중립", "neutral"
    return {"phase": phase, "tone": tone, "d1": round(d1, 2), "dN": round(dN, 2),
            "lookback": lookback}


def weekly_last(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    out, cur = [], None
    for t, v in series:
        y, w, _ = datetime.strptime(t, "%Y-%m-%d").isocalendar()
        if (y, w) == cur:
            out[-1] = (t, v)
        else:
            out.append((t, v))
            cur = (y, w)
    return out


def build() -> dict:
    _log("=== CAPEX 게이트 · 크레딧 레이어 ===")

    # 1) 주가 → 실현변동성 → 프록시
    closes, vols = {}, {}
    for nm in NAMES:
        t = nm["t"]
        try:
            c = fetch_closes(t)
            v = rolling_vol(c, VOL_WIN)
            if v:
                closes[t], vols[t] = c, v
                _log(f"  {t:6} 종가 {len(c)}일 · 126d vol {v[-1][1]:.1f}%")
        except Exception as e:  # noqa: BLE001
            _log(f"  {t:6} 수집 실패: {e}")
    # 주가 소스(Yahoo·Stooq)는 데이터센터 IP에서 자주 차단된다. 예전엔 여기서 raise 해
    # 스크립트 전체를 죽였는데, 그러면 잘 되는 FRED 레이어까지 같이 못 쓴다(2026-08, 23일 연속 실패).
    # → 프록시 레이어만 생략하고 나머지는 정상 갱신한다.
    degraded: list[str] = []
    prices_ok = "ORCL" in vols and "MSFT" in vols
    names_out: list[dict] = []
    prem_hist: list[dict] = []
    prem_mom = None
    fit = None

    if prices_ok:
        vols_now = {t: v[-1][1] for t, v in vols.items()}
        a, b, fit = calibrate(vols_now)
        _log(f"  캘리브레이션: CDS≈{math.exp(a):.4f}×vol^{fit['b']} "
             f"R²={fit['r2']} 평균오차={fit['mae']}%")

        for nm in NAMES:
            t = nm["t"]
            if t not in vols:
                continue
            px = proxy_bp(a, b, vols_now[t])
            wk = weekly_last(vols[t])
            hist = [{"t": d_, "v": round(proxy_bp(a, b, v))} for d_, v in wk][-WEEKS:]
            mom = momentum(hist, good_dir=-1, eps=8, lookback=13)
            names_out.append({
                "ticker": t, "label": nm["label"], "role": nm["role"],
                "vol": round(vols_now[t], 1), "proxy": round(px),
                "actual": CDS_ANCHOR.get(t), "asOf": vols[t][-1][0],
                "history": hist, "mom": mom,
            })

        # 2) AI 크레딧 프리미엄 = ORCL − MSFT (공통 주차만)
        o = {p["t"]: p["v"] for p in next(n for n in names_out if n["ticker"] == "ORCL")["history"]}
        m = {p["t"]: p["v"] for p in next(n for n in names_out if n["ticker"] == "MSFT")["history"]}
        prem_hist = [{"t": k, "v": o[k] - m[k]} for k in sorted(set(o) & set(m))][-WEEKS:]
        prem_mom = momentum(prem_hist, good_dir=-1, eps=15, lookback=13)
        _log(f"  AI 크레딧 프리미엄: {prem_hist[-1]['v']}bp {prem_mom and prem_mom['phase']}")
    else:
        degraded.append("주가 소스 차단 — AI 크레딧 프리미엄·종목별 프록시 생략")
        _log("  ⚠ ORCL/MSFT 시계열 없음 → 프록시 레이어 생략, FRED 레이어만 갱신")

    # 3) FRED 크레딧 집계
    ig = weekly_last(fetch_fred("BAMLC0A0CM"))
    ig_hist = [{"t": t, "v": round(v * 100)} for t, v in ig][-WEEKS:]
    ig_mom = momentum(ig_hist, good_dir=-1, eps=8, lookback=13)
    hy = weekly_last(fetch_fred("BAMLH0A0HYM2"))
    hy_hist = [{"t": t, "v": round(v * 100)} for t, v in hy][-WEEKS:]
    hy_mom = momentum(hy_hist, good_dir=-1, eps=15, lookback=13)
    _log(f"  IG OAS {ig_hist[-1]['v']}bp · HY OAS {hy_hist[-1]['v']}bp")

    # 4) DTCC CDS 헤지 활동
    try:
        act_hist, act_asof = dtcc_week_counts(8)
        act_mom = momentum(act_hist, good_dir=-1, eps=3, lookback=4) if len(act_hist) >= 5 else None
        _log(f"  DTCC CDS 활동: 최근주 {act_hist[-1]['v']}건" if act_hist else "  DTCC: 없음")
    except Exception as e:  # noqa: BLE001
        _log(f"  DTCC 실패: {e}")
        act_hist, act_mom, act_asof = [], None, None

    indicators = []
    if prem_hist:
        indicators.append(
        {"id": "ai_premium", "label": "AI 크레딧 프리미엄", "unit": "bp",
         "role": "ORCL − MSFT 프록시 · 부채조달 capex의 값", "decimals": 0,
         "source": "프록시 (126d 실현변동성 캘리브레이션)", "sourceUrl": "",
         "proxy": True,
         "value": prem_hist[-1]["v"], "asOf": prem_hist[-1]["t"],
         "history": prem_hist, "mom": prem_mom,
         "deltaNote": "13주 Δ {dN:+.0f}bp · 직전주 {d1:+.0f}"})
    indicators += [
        {"id": "ig_oas", "label": "IG 회사채 스프레드", "unit": "bp",
         "role": "하이퍼스케일러가 속한 등급대 · 조달비용", "decimals": 0,
         "source": "FRED · BAMLC0A0CM",
         "sourceUrl": "https://fred.stlouisfed.org/series/BAMLC0A0CM",
         "value": ig_hist[-1]["v"], "asOf": ig_hist[-1]["t"],
         "history": ig_hist, "mom": ig_mom,
         "deltaNote": "13주 Δ {dN:+.0f}bp · 직전주 {d1:+.0f}"},
        {"id": "hy_oas", "label": "하이일드 스프레드", "unit": "bp",
         "role": "위험선호 전반 · 네오클라우드 조달환경", "decimals": 0,
         "source": "FRED · BAMLH0A0HYM2",
         "sourceUrl": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
         "value": hy_hist[-1]["v"], "asOf": hy_hist[-1]["t"],
         "history": hy_hist, "mom": hy_mom,
         "deltaNote": "13주 Δ {dN:+.0f}bp · 직전주 {d1:+.0f}"},
    ]
    if act_hist:
        indicators.append({
            "id": "cds_activity", "label": "CDS 헤지 활동", "unit": "건/주",
            "role": "AI capex 이름들에 붙은 단일종목 CDS 거래 수", "decimals": 0,
            "source": "DTCC 공개 가격배포(PPD)",
            "sourceUrl": "https://pddata.dtcc.com/ppd/",
            # 표본이 주 수십 건뿐이라 노이즈가 크다 → 참고용, 레짐 투표에서 제외
            "vote": False, "noisy": True,
            "value": act_hist[-1]["v"], "asOf": act_asof or "",
            "history": act_hist, "mom": act_mom,
            "deltaNote": "4주 Δ {dN:+.0f}건 · 직전주 {d1:+.0f}"})

    for ind in indicators:
        mm = ind["mom"]
        ind["momLine"] = ind.pop("deltaNote").format(dN=mm["dN"], d1=mm["d1"]) if mm else ""

    # 통합 해석 — 스프레드류는 전부 '하락=우호'. 노이즈 지표(vote=False)는 투표 제외.
    voting = [i for i in indicators if i.get("vote", True) and i["mom"]]
    tot = len(voting)
    sup = sum(1 for i in voting if i["mom"]["phase"] in ("우호 지속", "우호 둔화"))
    against = [i["label"] for i in voting if i["mom"]["phase"] == "역풍"]
    neutral = tot - sup - len(against)
    if "AI 크레딧 프리미엄" in against:
        # 부채조달 capex의 값이 벌어지는 중 = 이 페이지가 잡으려던 바로 그 신호
        regime, regimeEn, tone = "크레딧 경보", "Credit Stress", "neg"
    elif len(against) >= 2:
        regime, regimeEn, tone = "크레딧 균열", "Cracking", "warn"
    elif sup >= 2 and not against:
        regime, regimeEn, tone = "크레딧 안정", "Stable", "pos"
    else:
        regime, regimeEn, tone = "혼조", "Mixed", "warn"
    headline = f"투표 지표 {tot}개 — 우호 {sup} · 중립 {neutral} · 역풍 {len(against)} → {regime}."
    if against:
        headline += f"  ✖ 확대: {', '.join(against)}."
    headline += ("  자금조달이 조여지면 capex 의지(게이트①)가 우호여도 "
                 "실행이 막힌다 — 게이트의 조기경보 레이어.")

    # 직전 판정과 비교해 "언제부터 이 판정인지"를 남긴다.
    # (매일 들여다보지 않아도 랜딩에서 '바뀐 것'만 눈에 띄게 하려는 장치)
    prev: dict = {}
    try:
        prev = json.loads((HERE / "data.json").read_text(encoding="utf-8")).get("interpretation", {})
    except Exception:  # noqa: BLE001
        pass
    today_s = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 부분 갱신이면 판정을 새로 계산하지 않는다.
    # AI 크레딧 프리미엄이 '크레딧 경보'를 결정하는 지표라, 주가 소스가 막혔다는
    # 이유만으로 경보가 조용히 '혼조'로 내려앉으면 최악의 실패다.
    # → 직전 판정을 그대로 유지하고 부분 갱신임을 명시한다.
    if degraded and prev.get("regime"):
        regime, regimeEn = prev["regime"], prev.get("regimeEn", regimeEn)
        tone = prev.get("tone", tone)
        headline = (f"⚠ 부분 갱신 — {degraded[0]}. 판정은 직전 값({regime})을 유지한다. "
                    + headline)

    if prev.get("regime") and prev["regime"] != regime:
        regime_since, regime_prev = today_s, prev["regime"]
        _log(f"  ⚑ 판정 변화: {prev['regime']} → {regime}")
    else:
        regime_since = prev.get("regimeSince") or today_s
        regime_prev = prev.get("regimePrev")

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "indicators": indicators,
        "names": names_out,
        "calibration": ({**fit, "anchors": CDS_ANCHOR, "volWindow": VOL_WIN} if fit else None),
        "degraded": degraded,
        "interpretation": {
            "regime": regime, "regimeEn": regimeEn, "tone": tone,
            "regimeSince": regime_since, "regimePrev": regime_prev,
            "headline": headline, "supportive": sup,
            "bullets": [{"label": i["label"], "value": i["value"], "unit": i["unit"],
                         "phase": i["mom"]["phase"] if i["mom"] else "",
                         "tone": i["mom"]["tone"] if i["mom"] else "neutral"}
                        for i in indicators],
        },
        "note": ("프록시는 실제 CDS가 아니다 — 126일 실현변동성을 "
                 f"{ANCHOR_DATE} 실측 7개에 맞춰 캘리브레이션한 추정치. "
                 "레벨이 아니라 방향과 격차를 봐라."),
    }


def main() -> None:
    payload = build()
    (HERE / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "data.js").write_text(
        "window.CAPEX_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    _log(f"완료 → {payload['interpretation']['regime']}")


if __name__ == "__main__":
    main()
