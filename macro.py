#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORBIS macro feed — FXファンダメンタルズ (政策金利・10年国債利回り・CPI前年比)
を FRED から取得し、為替スポットを frankfurter.app (キー不要) から取得して
macro.json に書き出す。

- FRED_API_KEY は環境変数から読む。値はログに出さない。
- 各通貨について、用意した系列IDを順に試して最初に取れたものを採用 (フォールバック)。
- 政策金利が取れない通貨は heat 用メトリクスを 10年債利回りで代替。
- 取得状況 (sources_used / sources_missing) も同梱して UI 側からフォールバック判定可能に。
"""
import os, sys, json
from datetime import datetime, timezone
import urllib.request, urllib.error

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
if not FRED_KEY:
    print("ERROR: FRED_API_KEY not set", file=sys.stderr)
    sys.exit(2)

# 通貨と和名
CCY = [
    ("USD", "米ドル"),
    ("EUR", "ユーロ"),
    ("JPY", "円"),
    ("GBP", "英ポンド"),
    ("AUD", "豪ドル"),
    ("CAD", "加ドル"),
    ("CHF", "スイスフラン"),
    ("NZD", "NZドル"),
]

# 各通貨のFRED系列ID (実在/有効か順に試す)。先頭が優先。
POLICY = {
    "USD": ["FEDFUNDS", "DFF"],
    "EUR": ["ECBDFR", "IRSTCI01EZM156N"],
    "JPY": ["INTDSRJPM193N", "IRSTCI01JPM156N"],
    "GBP": ["IUDSOIA", "IR3TIB01GBM156N", "INTDSRGBM193N"],
    "AUD": ["INTDSRAUM193N", "IR3TIB01AUM156N"],
    "CAD": ["INTDSRCAM193N", "IR3TIB01CAM156N"],
    "CHF": ["IRSTCI01CHM156N", "IR3TIB01CHM156N"],
    "NZD": ["INTDSRNZM193N", "IR3TIB01NZM156N"],
}
Y10 = {
    "USD": ["IRLTLT01USM156N", "DGS10"],
    "EUR": ["IRLTLT01EZM156N", "IRLTLT01DEM156N"],
    "JPY": ["IRLTLT01JPM156N"],
    "GBP": ["IRLTLT01GBM156N"],
    "AUD": ["IRLTLT01AUM156N"],
    "CAD": ["IRLTLT01CAM156N"],
    "CHF": ["IRLTLT01CHM156N"],
    "NZD": ["IRLTLT01NZM156N"],
}
# CPI(前年比) は維持されているインデックス系列から自前で YoY 計算する。
# 旧OECD成長率系列 (CPALTT01*M657N/659N) は FRED で 2021〜2024 に打ち切られ、
# AUD/NZD は HTTP400、JPY は最新が "." になっていたため指数系列へ移行。
# (series_id, kind)  kind: index_m=月次指数→12ヶ月前比 / index_q=四半期指数→4期前比 /
#                          yoy=既に前年比%の系列(最新有効値をそのまま採用)
CPI = {
    "USD": ("CPIAUCSL", "index_m"),
    "EUR": ("CP0000EZ19M086NEST", "index_m"),   # ユーロ圏HICP指数
    "JPY": ("FPCPITOTLZGJPN", "yoy"),           # OECD月次が2021打切り→World Bank年次YoYで代替
    "GBP": ("GBRCPIALLMINMEI", "index_m"),
    "AUD": ("AUSCPIALLQINMEI", "index_q"),       # 四半期
    "CAD": ("CANCPIALLMINMEI", "index_m"),
    "CHF": ("CHECPIALLMINMEI", "index_m"),
    "NZD": ("NZLCPIALLQINMEI", "index_q"),       # 四半期
}

def fred_latest(series_id):
    """FRED の最新値を取得。(value:float, date:str) または (None, reason:str)。"""
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
        "&sort_order=desc&limit=1"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, type(e).__name__
    obs = d.get("observations", [])
    if not obs:
        return None, "empty"
    v = obs[0].get("value", ".")
    if v == "." or v == "":
        return None, "null-obs"
    try:
        return (float(v), obs[0].get("date")), None
    except ValueError:
        return None, "parse"

def first_ok(series_list):
    """順に試して最初に取れた (series_id, value, date) を返す。全滅なら (None, None, None, last_reason)。"""
    last_reason = "no-series"
    for sid in series_list:
        val, reason = fred_latest(sid)
        if val is not None:
            v, d = val
            return sid, v, d, None
        last_reason = f"{sid}: {reason}"
    return None, None, None, last_reason

def fred_observations(series_id, limit):
    """最新 limit 件の有効観測を (date, value) の昇順リストで返す。失敗時は ([], reason)。"""
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
        f"&sort_order=desc&limit={limit}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except Exception as e:
        return [], type(e).__name__
    out = []
    for o in d.get("observations", []):
        v = o.get("value", ".")
        if v in (".", ""):
            continue
        try:
            out.append((o.get("date"), float(v)))
        except ValueError:
            continue
    out.reverse()  # 昇順 (最後が最新)
    return out, (None if out else "empty")

def cpi_yoy(series_id, kind):
    """前年比CPIを (value, date, note) で返す。取れなければ (None, None, reason)。
    JPY等 yoy系列はそのまま採用。指数系列は同月(同四半期)の前年値と日付一致で割る。"""
    if kind == "yoy":
        obs, reason = fred_observations(series_id, 6)
        if not obs:
            return None, None, reason or "empty"
        d, v = obs[-1]
        return round(v, 3), d, "yoy-direct"
    obs, reason = fred_observations(series_id, 26 if kind == "index_m" else 10)
    if len(obs) < 2:
        return None, None, reason or "short"
    bydate = dict(obs)
    d0, v0 = obs[-1]                      # 最新
    y, m, dd = d0.split("-")
    base = bydate.get(f"{int(y)-1}-{m}-{dd}")   # 同月(同四半期)の前年値
    if not base:                         # 日付が揃わなければ位置で前年分さかのぼる
        step = 12 if kind == "index_m" else 4
        if len(obs) > step:
            base = obs[-1 - step][1]
    if not base:
        return None, None, "no-base"
    return round((v0 / base - 1) * 100, 3), d0, "index-yoy"

def fetch_fx():
    """EUR基準のレート辞書 (X = 1EURあたりのX) と (source, date) を返す。全滅なら (None, None, None)。
    1) frankfurter.app → 2) open.er-api.com (キー不要) の順にフォールバック。"""
    # 1) frankfurter.app
    try:
        with urllib.request.urlopen("https://api.frankfurter.app/latest?from=EUR", timeout=25) as r:
            d = json.loads(r.read().decode())
        rates = dict(d.get("rates", {})); rates["EUR"] = 1.0
        if len(rates) > 5:
            return rates, "frankfurter", d.get("date")
    except Exception as e:
        print(f"  Frankfurter: {type(e).__name__}", file=sys.stderr)
    # 2) open.er-api.com (USDだけでなく任意baseで返る・キー不要)
    try:
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/EUR", timeout=25) as r:
            d = json.loads(r.read().decode())
        rates = dict(d.get("rates", {})); rates["EUR"] = 1.0
        date = (d.get("time_last_update_utc") or "")[:25]
        if len(rates) > 5:
            return rates, "er-api", date
    except Exception as e:
        print(f"  er-api: {type(e).__name__}", file=sys.stderr)
    return None, None, None

def load_prev_macro():
    """前回デプロイ済み macro.json 全体を読む(変化ビュー基準 + FX全滅時の保険)。失敗→None。"""
    url = os.environ.get("ORBIS_PREV_MACRO_URL",
                         "https://zhihongsishan-debug.github.io/orbis/macro.json")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def _delta(cur, prev, nd=3):
    return round(cur - prev, nd) if (cur is not None and prev is not None) else None

def main():
    prev = load_prev_macro()                 # 変化ビューの基準 (前回公開分)
    prev_cur = (prev.get("currencies", {}) if prev else {})
    prev_pairs = {}
    if prev:
        for p in prev.get("pairs", []):
            prev_pairs[(p.get("from"), p.get("to"))] = p
    out = {
        "generated_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "compare_to": (prev.get("generated_iso") if prev else None),
        "compare_available": bool(prev),
        "currencies": {},
        "pairs": [],
        "fx": {},
        "sources_used": {},
        "sources_missing": [],
    }
    ok_cnt = miss_cnt = 0

    for ccy, name in CCY:
        rec = {
            "name_jp": name,
            "policy_rate": None, "policy_date": None,
            "y10": None, "y10_date": None,
            "cpi": None, "cpi_date": None,
            "real_rate": None,
            "heat_rate": None,
        }
        for label, table in (("policy", POLICY), ("y10", Y10)):
            sid, v, d, reason = first_ok(table.get(ccy, []))
            key = f"{ccy}.{label}"
            if v is not None:
                if label == "policy": rec["policy_rate"] = round(v, 3); rec["policy_date"] = d
                else: rec["y10"] = round(v, 3); rec["y10_date"] = d
                out["sources_used"][key] = sid
                ok_cnt += 1
            else:
                out["sources_missing"].append(f"{key} ({reason})")
                miss_cnt += 1
        # CPI(前年比) は指数系列から自前計算
        csid, ckind = CPI.get(ccy, (None, None))
        if csid:
            cval, cdate, cnote = cpi_yoy(csid, ckind)
            if cval is not None:
                rec["cpi"] = cval; rec["cpi_date"] = cdate
                out["sources_used"][f"{ccy}.cpi"] = f"{csid} ({cnote})"
                ok_cnt += 1
            else:
                out["sources_missing"].append(f"{ccy}.cpi ({csid}: {cnote})")
                miss_cnt += 1

        if rec["policy_rate"] is not None and rec["cpi"] is not None:
            rec["real_rate"] = round(rec["policy_rate"] - rec["cpi"], 3)
        elif rec["y10"] is not None and rec["cpi"] is not None:
            rec["real_rate"] = round(rec["y10"] - rec["cpi"], 3)
        rec["heat_rate"] = rec["policy_rate"] if rec["policy_rate"] is not None else rec["y10"]
        # 前回比 (prev / delta) を付与
        pc = prev_cur.get(ccy) or {}
        rec["prev"] = {}; rec["delta"] = {}
        for f in ("policy_rate", "y10", "cpi", "real_rate"):
            pv = pc.get(f)
            rec["prev"][f] = pv
            rec["delta"][f] = _delta(rec[f], pv)
        out["currencies"][ccy] = rec

    PAIR_DEFS = [
        ("USD","JPY"),("EUR","USD"),("GBP","USD"),("USD","CHF"),
        ("AUD","USD"),("NZD","USD"),("USD","CAD"),
        ("EUR","JPY"),("GBP","JPY"),("EUR","GBP"),
        ("AUD","JPY"),("EUR","AUD"),("EUR","CHF"),("CHF","JPY"),
        ("AUD","NZD"),("NZD","JPY"),("GBP","CHF"),("CAD","JPY"),
    ]
    out["fx_stale"] = False
    out["fx_source"] = None
    out["fx_date"] = None
    rates, fx_src, fx_date = fetch_fx()
    if rates:
        out["fx_source"] = fx_src
        out["fx_date"] = fx_date
        for a, b in PAIR_DEFS:
            if a in rates and b in rates and rates[a]:
                out["fx"][f"{a}{b}"] = round(rates[b] / rates[a], 4)
    else:
        # 今回FX全滅 → 前回デプロイ値を流用して空白回避 ((前回値)表示はUI側)
        if prev and prev.get("fx"):
            out["fx"] = dict(prev["fx"])
            out["fx_stale"] = True
            out["fx_source"] = "carried"
            out["fx_date"] = prev.get("fx_date")

    for a, b in PAIR_DEFS:
        ra = out["currencies"].get(a, {}).get("heat_rate")
        rb = out["currencies"].get(b, {}).get("heat_rate")
        if ra is None or rb is None: continue
        diff = round((ra - rb) * 100, 1)
        fxv = out["fx"].get(f"{a}{b}")
        pp = prev_pairs.get((a, b)) or {}
        out["pairs"].append({
            "from": a, "to": b,
            "diff_bp": diff,
            "fx": fxv,
            "diff_bp_prev": pp.get("diff_bp"),
            "diff_bp_delta": _delta(diff, pp.get("diff_bp"), 1),
            "fx_prev": pp.get("fx"),
            "fx_delta": _delta(fxv, pp.get("fx"), 4),
        })
    out["pairs"].sort(key=lambda x: -abs(x["diff_bp"]))

    with open("macro.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    # 取れた系列と欠損を必ず報告 (キー値そのものは絶対に出さない)
    print(f"macro.json: {len(out['currencies'])} ccy, {len(out['pairs'])} pairs, "
          f"FX={len(out['fx'])} pairs (src={out['fx_source']}, stale={out['fx_stale']}, date={out['fx_date']}), "
          f"FRED OK={ok_cnt} MISS={miss_cnt}, "
          f"compare={'前回 '+str(out['compare_to']) if out['compare_available'] else '無し(初回)'}")
    if out["sources_used"]:
        print("Used:")
        for k, sid in out["sources_used"].items():
            print(f"  {k} <- {sid}")
    if out["sources_missing"]:
        print("Missing:")
        for k in out["sources_missing"]:
            print(f"  {k}")

if __name__ == "__main__":
    main()
