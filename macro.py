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
CPI = {
    "USD": ["CPALTT01USM657N"],
    "EUR": ["CPHPTT01EZM657N", "CPALTT01EZM657N"],
    "JPY": ["CPALTT01JPM657N"],
    "GBP": ["CPALTT01GBM657N"],
    "AUD": ["CPALTT01AUM657N"],
    "CAD": ["CPALTT01CAM657N"],
    "CHF": ["CPALTT01CHM657N"],
    "NZD": ["CPALTT01NZM657N"],
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

def frankfurter_latest():
    url = "https://api.frankfurter.app/latest"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  Frankfurter: {type(e).__name__}", file=sys.stderr)
        return None

def main():
    out = {
        "generated_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
        for label, table in (("policy", POLICY), ("y10", Y10), ("cpi", CPI)):
            sid, v, d, reason = first_ok(table.get(ccy, []))
            key = f"{ccy}.{label}"
            if v is not None:
                if label == "policy": rec["policy_rate"] = round(v, 3); rec["policy_date"] = d
                elif label == "y10": rec["y10"] = round(v, 3); rec["y10_date"] = d
                else: rec["cpi"] = round(v, 3); rec["cpi_date"] = d
                out["sources_used"][key] = sid
                ok_cnt += 1
            else:
                out["sources_missing"].append(f"{key} ({reason})")
                miss_cnt += 1

        if rec["policy_rate"] is not None and rec["cpi"] is not None:
            rec["real_rate"] = round(rec["policy_rate"] - rec["cpi"], 3)
        elif rec["y10"] is not None and rec["cpi"] is not None:
            rec["real_rate"] = round(rec["y10"] - rec["cpi"], 3)
        rec["heat_rate"] = rec["policy_rate"] if rec["policy_rate"] is not None else rec["y10"]
        out["currencies"][ccy] = rec

    fx = frankfurter_latest()
    if fx and "rates" in fx:
        eur_to = dict(fx["rates"])
        eur_to["EUR"] = 1.0
        pair_defs = [
            ("USD","JPY"),("EUR","USD"),("GBP","USD"),("USD","CHF"),
            ("AUD","USD"),("NZD","USD"),("USD","CAD"),
            ("EUR","JPY"),("GBP","JPY"),("EUR","GBP"),
            ("AUD","JPY"),("EUR","AUD"),("EUR","CHF"),("CHF","JPY"),
            ("AUD","NZD"),("NZD","JPY"),("GBP","CHF"),("CAD","JPY"),
        ]
        for a, b in pair_defs:
            if a in eur_to and b in eur_to and eur_to[a]:
                out["fx"][f"{a}{b}"] = round(eur_to[b] / eur_to[a], 4)

    diff_pairs = [
        ("USD","JPY"),("EUR","USD"),("GBP","USD"),("USD","CHF"),
        ("AUD","USD"),("NZD","USD"),("USD","CAD"),
        ("EUR","JPY"),("GBP","JPY"),("EUR","GBP"),
        ("AUD","JPY"),("EUR","AUD"),("EUR","CHF"),("CHF","JPY"),
        ("AUD","NZD"),("NZD","JPY"),("GBP","CHF"),("CAD","JPY"),
    ]
    for a, b in diff_pairs:
        ra = out["currencies"].get(a, {}).get("heat_rate")
        rb = out["currencies"].get(b, {}).get("heat_rate")
        if ra is None or rb is None: continue
        out["pairs"].append({
            "from": a, "to": b,
            "diff_bp": round((ra - rb) * 100, 1),
            "fx": out["fx"].get(f"{a}{b}"),
        })
    out["pairs"].sort(key=lambda x: -abs(x["diff_bp"]))

    with open("macro.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    # 取れた系列と欠損を必ず報告 (キー値そのものは絶対に出さない)
    print(f"macro.json: {len(out['currencies'])} ccy, {len(out['pairs'])} pairs, "
          f"FX={len(out['fx'])} pairs, FRED OK={ok_cnt} MISS={miss_cnt}")
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
