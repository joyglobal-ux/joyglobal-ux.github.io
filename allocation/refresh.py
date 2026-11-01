"""배분판 — 레짐 다이얼 · US/KR 틸트 · 트리거 수집 엔진.

입력(전부 무료·무키):
  yfinance : SPY, ^KS11(코스피), ^VIX, KRW=X(USDKRW), DX-Y.NYB(DXY)  — 3년 일봉
  FRED     : DGS10(미 10년물), BAMLH0A0HYM2(HY OAS)
  Polaris  : https://joyglobal-ux.github.io/rs-screener/data-{us,kr}.json  — breadth(50/200일선 위 비율, RS90+ 수)

룰 v1 (근거: backtest.json, 지수 레벨 1995~/1997~):
  다이얼  = 지수>200일선(+50) + 지수>50일선(+50) → 시장별 익스포저 상한 0/50/100%
  가드    = breadth(50일선 위) < 30% → −25%p · HY OAS 4주 +50bp↑ → −25%p · VIX 워시아웃(20일 최고≥30, 현재≤최고×0.8) → +25%p 재진입 허용(상한 50)
  틸트    = 12개월 상대 모멘텀(원화 기준, SPY×USDKRW vs 코스피) 강한 쪽 75 / 약한 쪽 25
  지시    = 슬리브 US = min(capUS, tiltUS), KR = min(capKR, tiltKR), 나머지 현금
history.json 에 일별 스냅샷을 append(트리거 since 계산·향후 가드 백테스트용).

사용: python3 refresh.py   (의존성: requests, pandas, yfinance)
"""
from __future__ import annotations

import csv, json, sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

HERE = Path(__file__).parent
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
SCREENER = "https://joyglobal-ux.github.io/rs-screener/data-{m}.json"
SERIES_DAYS = 520   # 차트용 2년

# ── 룰 상수 (여기만 고친다) ─────────────────────────────────────────
BREADTH_GUARD = 30        # 50일선 위 비율 < 30% → 가드
HY_4W_BP = 50             # HY OAS 4주 변화 ≥ +50bp → 가드
VIX_WASHOUT_PEAK = 30     # 20일 최고 VIX ≥ 30 이고
VIX_WASHOUT_DROP = 0.8    # 현재 ≤ 최고 × 0.8 → 워시아웃 재진입 허용
TILT_STRONG, TILT_WEAK = 75, 25
DGS10_ALERT = 4.8         # AIDC 노트의 경보선
HYNIX_LINES = {"structure": 1_600_000, "oct_low": 1_208_000}
CREDIT_DUE = "2026-12-07"


def log(m): print(m, file=sys.stderr)


def fred(sid: str) -> pd.Series:
    r = requests.get(FRED_CSV.format(sid=sid), timeout=30); r.raise_for_status()
    rows = [(d, float(v)) for d, v in list(csv.reader(StringIO(r.text)))[1:] if v not in ("", ".")]
    s = pd.Series({pd.Timestamp(d): v for d, v in rows}).sort_index()
    if s.empty: raise RuntimeError(f"{sid} empty")
    return s


def pct(a, b): return None if (a is None or b is None or b == 0) else round((a / b - 1) * 100, 2)


def breadth(m: str) -> dict | None:
    try:
        d = requests.get(SCREENER.format(m=m), timeout=60).json()
    except Exception as e:  # noqa
        log(f"  breadth {m} fetch failed: {e}"); return None
    st = [s for s in d["stocks"] if s.get("dev")]
    n = len(st)
    a50 = sum(1 for s in st if (s["dev"].get("dev50") or 0) > 0)
    a200 = sum(1 for s in st if (s["dev"].get("dev200") or 0) > 0)
    rs90 = sum(1 for s in d["stocks"] if (s.get("score") or 0) >= 90)
    return {"asOf": d["asOf"], "n": n, "a50": round(100 * a50 / n, 1), "a200": round(100 * a200 / n, 1), "rs90": rs90}


def main() -> None:
    px = yf.download(["SPY", "^KS11", "^VIX", "KRW=X", "DX-Y.NYB"], period="3y", auto_adjust=False, progress=False)["Close"].sort_index().ffill()
    dgs10 = fred("DGS10"); hy = fred("BAMLH0A0HYM2") * 100   # FRED는 %(3.14) → bp(314)
    today = px.index[-1]

    def market(col: str, name: str, m: str) -> dict:
        c = px[col].dropna()
        ma50, ma150, ma200 = c.rolling(50).mean(), c.rolling(150).mean(), c.rolling(200).mean()
        mo = c.resample("ME").last(); m10 = mo.rolling(10).mean()
        last = float(c.iloc[-1])
        above200, above50 = last > ma200.iloc[-1], last > ma50.iloc[-1]
        dial = (50 if above200 else 0) + (50 if above50 else 0)
        b = breadth(m)
        guard_breadth = bool(b and b["a50"] < BREADTH_GUARD)
        tail = c.iloc[-SERIES_DAYS:]
        return {
            "name": name, "ticker": col, "last": round(last, 2), "lastDate": c.index[-1].strftime("%Y-%m-%d"),
            "vs50": pct(last, ma50.iloc[-1]), "vs150": pct(last, ma150.iloc[-1]), "vs200": pct(last, ma200.iloc[-1]),
            "vs10m": pct(float(mo.iloc[-1]), float(m10.iloc[-1])),
            "ma200slope20": pct(ma200.iloc[-1], ma200.iloc[-21]),
            "hi52": pct(last, float(c.iloc[-252:].max())),
            "r1M": pct(last, float(c.iloc[-22])), "r3M": pct(last, float(c.iloc[-64])),
            "above200": bool(above200), "above50": bool(above50), "dial": dial,
            "breadth": b, "guardBreadth": guard_breadth,
            "series": {"dates": [d.strftime("%Y-%m-%d") for d in tail.index], "c": [round(float(v), 2) for v in tail],
                       "ma50": [None if pd.isna(v) else round(float(v), 2) for v in ma50.iloc[-SERIES_DAYS:]],
                       "ma200": [None if pd.isna(v) else round(float(v), 2) for v in ma200.iloc[-SERIES_DAYS:]]},
        }

    us = market("SPY", "S&P 500 (SPY)", "us"); kr = market("^KS11", "코스피", "kr")

    # 매크로
    vix = px["^VIX"].dropna(); vmax20 = float(vix.iloc[-20:].max()); vlast = float(vix.iloc[-1])
    washout = vmax20 >= VIX_WASHOUT_PEAK and vlast <= vmax20 * VIX_WASHOUT_DROP
    hy_last = float(hy.iloc[-1]); hy_4w = float(hy.iloc[-21]) if len(hy) > 21 else None
    hy_chg = round(hy_last - hy_4w, 0) if hy_4w is not None else None
    guard_hy = bool(hy_chg is not None and hy_chg >= HY_4W_BP)
    krw = px["KRW=X"].dropna(); dxy = px["DX-Y.NYB"].dropna()
    macro = {
        "vix": {"last": round(vlast, 1), "max20": round(vmax20, 1), "washout": bool(washout), "lastDate": vix.index[-1].strftime("%Y-%m-%d")},
        "dgs10": {"last": float(dgs10.iloc[-1]), "prev4w": float(dgs10.iloc[-21]), "lastDate": dgs10.index[-1].strftime("%Y-%m-%d"), "alert": float(dgs10.iloc[-1]) >= DGS10_ALERT},
        "hy": {"last": hy_last, "chg4w": hy_chg, "lastDate": hy.index[-1].strftime("%Y-%m-%d"), "guard": guard_hy},
        "usdkrw": {"last": round(float(krw.iloc[-1]), 1), "chg3M": pct(float(krw.iloc[-1]), float(krw.iloc[-64])), "chg1M": pct(float(krw.iloc[-1]), float(krw.iloc[-22]))},
        "dxy": {"last": round(float(dxy.iloc[-1]), 2), "chg3M": pct(float(dxy.iloc[-1]), float(dxy.iloc[-64]))},
        "series": {
            "vix": {"dates": [d.strftime("%Y-%m-%d") for d in vix.index[-260:]], "v": [round(float(x), 2) for x in vix.iloc[-260:]]},
            "dgs10": {"dates": [d.strftime("%Y-%m-%d") for d in dgs10.index[-260:]], "v": [float(x) for x in dgs10.iloc[-260:]]},
            "hy": {"dates": [d.strftime("%Y-%m-%d") for d in hy.index[-260:]], "v": [float(x) for x in hy.iloc[-260:]]},
            "usdkrw": {"dates": [d.strftime("%Y-%m-%d") for d in krw.index[-260:]], "v": [round(float(x), 1) for x in krw.iloc[-260:]]},
        },
    }

    # 상한 = 다이얼 + 가드
    def cap(mk):
        v = mk["dial"]
        adj = []
        if mk["guardBreadth"]: v -= 25; adj.append(f"breadth {mk['breadth']['a50']}% < {BREADTH_GUARD}% −25")
        if guard_hy: v -= 25; adj.append(f"HY 4주 +{hy_chg:.0f}bp −25")
        if washout and v < 50: v = min(v + 25, 50); adj.append("VIX 워시아웃 +25 (상한 50)")
        return max(0, min(100, v)), adj
    us["cap"], us["capAdj"] = cap(us); kr["cap"], kr["capAdj"] = cap(kr)

    # 틸트 (원화 기준)
    spyk = (px["SPY"] * px["KRW=X"]).dropna(); ks = px["^KS11"].reindex(spyk.index).ffill()
    rel = {}
    for L, d in (("3M", 63), ("6M", 126), ("12M", 252)):
        u = pct(float(spyk.iloc[-1]), float(spyk.iloc[-1 - d])); k = pct(float(ks.iloc[-1]), float(ks.iloc[-1 - d]))
        rel[L] = {"us": u, "kr": k, "diff": round(u - k, 2)}
    win = "US" if rel["12M"]["diff"] > 0 else "KR"
    tilt = {"rel": rel, "winner12M": win, "us": TILT_STRONG if win == "US" else TILT_WEAK, "kr": TILT_WEAK if win == "US" else TILT_STRONG}

    # 슬리브: 틸트는 두 시장이 모두 열려 있을 때만 나눈다. 한쪽이 0이면 열린 쪽이 자기 상한을 다 쓴다.
    if kr["cap"] == 0 and us["cap"] > 0: sleeve_us, sleeve_kr = us["cap"], 0
    elif us["cap"] == 0 and kr["cap"] > 0: sleeve_us, sleeve_kr = 0, kr["cap"]
    else: sleeve_us, sleeve_kr = min(us["cap"], tilt["us"]), min(kr["cap"], tilt["kr"])
    orders = {"capUS": us["cap"], "capKR": kr["cap"], "sleeveUS": sleeve_us, "sleeveKR": sleeve_kr, "cash": 100 - sleeve_us - sleeve_kr,
              "regimeUS": {0: "방어", 25: "방어+", 50: "경계", 75: "정상", 100: "공격"}.get(us["cap"], "경계"),
              "regimeKR": {0: "방어", 25: "방어+", 50: "경계", 75: "정상", 100: "공격"}.get(kr["cap"], "경계")}

    # 트리거 (state on/off) — since는 history로 계산
    trig = [
        {"id": "kr_above50", "label": "코스피 50일선 회복", "value": f"{kr['vs50']:+.1f}%", "on": kr["above50"], "effect": "KR 상한 +50"},
        {"id": "kr_above200", "label": "코스피 200일선 회복", "value": f"{kr['vs200']:+.1f}%", "on": kr["above200"], "effect": "KR 상한 +50"},
        {"id": "kr_breadth", "label": f"코스피 breadth ≥ {BREADTH_GUARD}% (50일선 위 종목)", "value": f"{kr['breadth']['a50']}%" if kr["breadth"] else "—", "on": not kr["guardBreadth"], "effect": "KR 가드 해제"},
        {"id": "us_above50", "label": "SPY 50일선 위", "value": f"{us['vs50']:+.1f}%", "on": us["above50"], "effect": "US 상한 +50"},
        {"id": "us_above200", "label": "SPY 200일선 위", "value": f"{us['vs200']:+.1f}%", "on": us["above200"], "effect": "US 상한 +50"},
        {"id": "us_breadth", "label": f"US breadth ≥ {BREADTH_GUARD}%", "value": f"{us['breadth']['a50']}%" if us["breadth"] else "—", "on": not us["guardBreadth"], "effect": "US 가드 해제"},
        {"id": "tilt_us", "label": "12M 상대(원화) US 우위", "value": f"{rel['12M']['diff']:+.1f}%p", "on": win == "US", "effect": "틸트 US 75 / KR 25"},
        {"id": "vix_washout", "label": "VIX 워시아웃 (20일 최고≥30 → −20%)", "value": f"{vlast:.1f} / 최고 {vmax20:.1f}", "on": bool(washout), "effect": "재진입 +25 허용"},
        {"id": "hy_spike", "label": f"HY OAS 4주 +{HY_4W_BP}bp", "value": f"{hy_last:.0f}bp ({hy_chg:+.0f})" if hy_chg is not None else "—", "on": guard_hy, "effect": "상한 −25"},
        {"id": "dgs10", "label": f"미 10년물 ≥ {DGS10_ALERT}%", "value": f"{float(dgs10.iloc[-1]):.2f}%", "on": bool(float(dgs10.iloc[-1]) >= DGS10_ALERT), "effect": "AIDC·전력기기 섹터 금지"},
        {"id": "credit_due", "label": f"신용 만기 {CREDIT_DUE}", "value": f"D-{(pd.Timestamp(CREDIT_DUE) - today).days}", "on": (pd.Timestamp(CREDIT_DUE) - today).days <= 14, "effect": "레버리지 0 데드라인"},
    ]

    # history append (하루 1행, 같은 날이면 덮어씀)
    hp = HERE / "history.json"
    hist = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else []
    row = {"date": today.strftime("%Y-%m-%d"),
           "us": {"a50": us["breadth"]["a50"] if us["breadth"] else None, "a200": us["breadth"]["a200"] if us["breadth"] else None, "rs90": us["breadth"]["rs90"] if us["breadth"] else None, "dial": us["dial"], "cap": us["cap"]},
           "kr": {"a50": kr["breadth"]["a50"] if kr["breadth"] else None, "a200": kr["breadth"]["a200"] if kr["breadth"] else None, "rs90": kr["breadth"]["rs90"] if kr["breadth"] else None, "dial": kr["dial"], "cap": kr["cap"]},
           "tilt": win, "vix": round(vlast, 1), "hy": hy_last, "dgs10": float(dgs10.iloc[-1]), "usdkrw": round(float(krw.iloc[-1]), 1),
           "trig": {t["id"]: t["on"] for t in trig}}
    hist = [h for h in hist if h["date"] != row["date"]] + [row]
    hist.sort(key=lambda h: h["date"])
    hp.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    for t in trig:  # since = 현재 상태가 연속된 첫 날
        since = row["date"]
        for h in reversed(hist):
            if h.get("trig", {}).get(t["id"]) == t["on"]: since = h["date"]
            else: break
        t["since"] = since
        t["changedToday"] = len(hist) >= 2 and hist[-2].get("trig", {}).get(t["id"]) not in (None, t["on"])

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "asOf": today.strftime("%Y-%m-%d"),
        "rules": {"breadthGuard": BREADTH_GUARD, "hy4wBp": HY_4W_BP, "vixPeak": VIX_WASHOUT_PEAK, "vixDrop": VIX_WASHOUT_DROP, "tilt": [TILT_STRONG, TILT_WEAK], "dgs10Alert": DGS10_ALERT, "hynixLines": HYNIX_LINES, "creditDue": CREDIT_DUE},
        "markets": {"us": us, "kr": kr}, "tilt": tilt, "macro": macro, "orders": orders, "triggers": trig,
        "history": hist[-400:],
    }
    (HERE / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (HERE / "data.js").write_text("window.ALLOC_DATA = " + json.dumps(payload, ensure_ascii=False) + ";", encoding="utf-8")
    log(f"asOf {payload['asOf']} | US dial {us['dial']} cap {us['cap']} {us['capAdj']} | KR dial {kr['dial']} cap {kr['cap']} {kr['capAdj']} | tilt {win} | orders {orders}")
    log("triggers ON: " + ", ".join(t["id"] for t in trig if t["on"]))


if __name__ == "__main__":
    main()
