#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORBIS ingest v4 — GDELT 2.0 Events を直近2時間(15分×8枚)ぶんローリング集約。
v4の変更:
- 行単位のしきい値を撤去 (NumSources>=N → 全行集計に)
- 集約後 (国A,国B,type) ごとの合計ソース数で MIN_PAIR_SOURCES によりフィルタ
- 診断カウンタを出力 ("行数: 全X / 両国コードあり Y / 両方リスト内 Z / A≠B W / 集約ペア P")
"""
import io, csv, json, time, zipfile, argparse, sys, math, re, os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import requests

# 変化(デルタ)ビュー用: run冒頭で公開中の events.json を「前回スナップショット」として取得する。
PREV_EVENTS_URL = os.environ.get("ORBIS_PREV_EVENTS_URL",
                                 "https://zhihongsishan-debug.github.io/orbis/events.json")

GDELT_BASE = "http://data.gdeltproject.org/gdeltv2"
LASTUPDATE = f"{GDELT_BASE}/lastupdate.txt"
QUAD = {1: "coop", 2: "aid", 3: "tension", 4: "conflict"}
ROOT = {"01":"声明","02":"要請","03":"協力の意向","04":"協議","05":"外交的協力","06":"物的協力",
 "07":"支援の提供","08":"譲歩","09":"調査","10":"要求","11":"非難","12":"拒否","13":"威嚇",
 "14":"抗議","15":"軍事的示威","16":"関係縮小","17":"威圧","18":"襲撃","19":"戦闘","20":"大規模暴力"}

# GDELT 2.0 Events 列インデックス
A1CC, A2CC = 7, 17           # Actor1/2 CountryCode (CAMEO 3-letter)
ROOTCODE, QUADCLASS = 28, 29
NUMSOURCES = 32
SRCURL = 60

MIN_PAIR_SOURCES = 3   # 集約後の (国A,国B,type) 合計ソース数のしきい値
TOP_N = 60
WINDOW = 8             # 直近 WINDOW × 15分 = 2時間

# CAMEO 国コード -> [和名, 首都lat, 首都lng]
CC = {
"USA":["米国",38.9,-77.0],"RUS":["ロシア",55.75,37.6],"CHN":["中国",39.9,116.4],
"UKR":["ウクライナ",50.45,30.52],"GBR":["英国",51.51,-0.13],"FRA":["フランス",48.85,2.35],
"DEU":["ドイツ",52.52,13.41],"JPN":["日本",35.68,139.69],"IND":["インド",28.61,77.21],
"PAK":["パキスタン",33.69,73.06],"ISR":["イスラエル",31.78,35.22],"IRN":["イラン",35.69,51.39],
"PRK":["北朝鮮",39.03,125.75],"KOR":["韓国",37.57,126.98],"TUR":["トルコ",39.93,32.86],
"SYR":["シリア",33.51,36.29],"SAU":["サウジアラビア",24.71,46.68],"YEM":["イエメン",15.37,44.19],
"SDN":["スーダン",15.5,32.56],"VEN":["ベネズエラ",10.48,-66.9],"LBN":["レバノン",33.89,35.5],
"AFG":["アフガニスタン",34.53,69.17],"IRQ":["イラク",33.31,44.36],"EGY":["エジプト",30.04,31.24],
"ITA":["イタリア",41.9,12.5],"ESP":["スペイン",40.42,-3.7],"POL":["ポーランド",52.23,21.01],
"CAN":["カナダ",45.42,-75.7],"AUS":["豪州",-35.28,149.13],"BRA":["ブラジル",-15.79,-47.88],
"MEX":["メキシコ",19.43,-99.13],"ARG":["アルゼンチン",-34.6,-58.38],"COL":["コロンビア",4.71,-74.07],
"NGA":["ナイジェリア",9.08,7.4],"ETH":["エチオピア",9.03,38.74],"KEN":["ケニア",-1.29,36.82],
"ZAF":["南アフリカ",-25.75,28.19],"COD":["コンゴ民主共和国",-4.32,15.31],"SOM":["ソマリア",2.04,45.34],
"MLI":["マリ",12.65,-8.0],"LBY":["リビア",32.89,13.19],"DZA":["アルジェリア",36.75,3.06],
"MAR":["モロッコ",34.02,-6.84],"TUN":["チュニジア",36.81,10.18],"JOR":["ヨルダン",31.95,35.93],
"QAT":["カタール",25.29,51.53],"ARE":["UAE",24.45,54.38],"KWT":["クウェート",29.37,47.98],
"GRC":["ギリシャ",37.98,23.73],"NLD":["オランダ",52.37,4.9],"BEL":["ベルギー",50.85,4.35],
"SWE":["スウェーデン",59.33,18.07],"NOR":["ノルウェー",59.91,10.75],"FIN":["フィンランド",60.17,24.94],
"CHE":["スイス",46.95,7.45],"AUT":["オーストリア",48.21,16.37],"CZE":["チェコ",50.08,14.44],
"HUN":["ハンガリー",47.5,19.04],"ROU":["ルーマニア",44.43,26.1],"BGR":["ブルガリア",42.7,23.32],
"BLR":["ベラルーシ",53.9,27.57],"GEO":["ジョージア",41.72,44.78],"ARM":["アルメニア",40.18,44.51],
"AZE":["アゼルバイジャン",40.41,49.87],"KAZ":["カザフスタン",51.17,71.43],"UZB":["ウズベキスタン",41.31,69.24],
"THA":["タイ",13.75,100.5],"VNM":["ベトナム",21.03,105.85],"PHL":["フィリピン",14.6,120.98],
"IDN":["インドネシア",-6.21,106.85],"MYS":["マレーシア",3.14,101.69],"SGP":["シンガポール",1.35,103.82],
"MMR":["ミャンマー",16.84,96.17],"BGD":["バングラデシュ",23.81,90.41],"LKA":["スリランカ",6.93,79.85],
"TWN":["台湾",25.03,121.56],"NZL":["ニュージーランド",-41.29,174.78],"CHL":["チリ",-33.45,-70.67],
"PER":["ペルー",-12.05,-77.04],"CUB":["キューバ",23.11,-82.37],"UGA":["ウガンダ",0.35,32.58],
"RWA":["ルワンダ",-1.95,30.06],"TCD":["チャド",12.13,15.06],"NER":["ニジェール",13.51,2.11],
"BFA":["ブルキナファソ",12.37,-1.52],"CMR":["カメルーン",3.85,11.5],"GHA":["ガーナ",5.6,-0.19],
"PRT":["ポルトガル",38.72,-9.14],"IRL":["アイルランド",53.35,-6.26],"DNK":["デンマーク",55.68,12.57],
}

def latest_export_url():
    txt = requests.get(LASTUPDATE, timeout=30).text
    for line in txt.splitlines():
        p = line.split()
        if p and p[-1].endswith("export.CSV.zip"):
            return p[-1]
    raise RuntimeError("export URL not found")

def parse_url_ts(url):
    m = re.search(r"/(\d{14})\.export", url)
    if not m:
        return None
    s = m.group(1)
    return datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]),
                    int(s[8:10]), int(s[10:12]), tzinfo=timezone.utc)

def export_url(dt):
    return f"{GDELT_BASE}/{dt.strftime('%Y%m%d%H%M%S')}.export.CSV.zip"

def gdelt_label(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def ingest_one(url, agg, stats):
    """1枚をダウンロードして agg/stats に追加集計。成功時 True。"""
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            print(f"  skip {url.rsplit('/',1)[-1]}: HTTP {resp.status_code}", file=sys.stderr)
            return False
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        data = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    except Exception as e:
        print(f"  skip {url.rsplit('/',1)[-1]}: {e}", file=sys.stderr)
        return False
    rows = csv.reader(io.StringIO(data), delimiter="\t")
    for r in rows:
        if len(r) < 61: continue
        stats["total"] += 1
        a, b = r[A1CC].strip(), r[A2CC].strip()
        if not a or not b: continue
        stats["both_cc"] += 1
        if a not in CC or b not in CC: continue
        stats["both_in_list"] += 1
        if a == b: continue
        stats["neq"] += 1
        try: ns = int(r[NUMSOURCES] or 0)
        except ValueError: continue
        try: qc = int(r[QUADCLASS] or 0)
        except ValueError: continue
        typ = QUAD.get(qc)
        if not typ: continue
        k = (a, b, typ)
        agg[k]["sources"] += ns
        agg[k]["roots"][r[ROOTCODE]] += ns
        if not agg[k]["url"]:
            agg[k]["url"] = r[SRCURL]
    return True

def fetch_events():
    latest_url = latest_export_url()
    latest_ts = parse_url_ts(latest_url)
    if latest_ts is None:
        raise RuntimeError("could not parse timestamp from latest URL")
    agg = defaultdict(lambda: {"sources":0,"roots":defaultdict(int),"url":""})
    stats = {"total":0, "both_cc":0, "both_in_list":0, "neq":0}
    ok = 0
    for i in range(WINDOW):
        dt = latest_ts - timedelta(minutes=15 * i)
        if ingest_one(export_url(dt), agg, stats):
            ok += 1
    print(f"集約対象ファイル: {ok}/{WINDOW} 枚")
    print(f"行数: 全{stats['total']} / 両国コードあり {stats['both_cc']} / "
          f"両方リスト内 {stats['both_in_list']} / A≠B {stats['neq']} / 集約ペア {len(agg)}")

    out = []
    for (a, b, typ), v in agg.items():
        ns = v["sources"]
        if ns < MIN_PAIR_SOURCES:
            continue
        an, bn = CC[a][0], CC[b][0]
        top_root = max(v["roots"], key=v["roots"].get)
        rd = ROOT.get(top_root, "事象")
        intensity = max(1, min(10, round(math.log10(ns + 1) * 4) + (2 if typ == "conflict" else 0)))
        out.append({
            "fromName": an, "toName": bn, "type": typ, "intensity": intensity,
            "summary": f"{an} → {bn}：{rd}（報道{ns}件）",
            "detail": f"{an} が {bn} に対して主に『{rd}』に分類される行動。直近2時間の報道ソース合計 {ns} 件。例: {v['url']}",
            "sLat": CC[a][1], "sLng": CC[a][2], "eLat": CC[b][1], "eLng": CC[b][2],
            "sources": ns,
            "url": v["url"],
        })
    out.sort(key=lambda x: x["sources"], reverse=True)
    return out[:TOP_N], gdelt_label(latest_ts)

def load_prev_events():
    """公開中の events.json を取得し (prev_map, generated_iso) を返す。失敗→(None,None)。
    prev_map: {(fromName,toName,type): sources}"""
    try:
        r = requests.get(PREV_EVENTS_URL, timeout=20)
        if r.status_code != 200:
            return None, None
        d = r.json()
    except Exception as e:
        print(f"  前回 events.json 取得失敗: {type(e).__name__}", file=sys.stderr)
        return None, None
    evs = d.get("events") if isinstance(d, dict) else d
    if not isinstance(evs, list):
        return None, None
    pm = {}
    for e in evs:
        pm[(e.get("fromName"), e.get("toName"), e.get("type"))] = e.get("sources", 0)
    return pm, (d.get("generated_iso") if isinstance(d, dict) else None)

def compute_changes(ev, prev_map):
    """各イベントに prev_sources/delta_sources/is_new を付与し、変化サマリを返す。
    prev が無ければ available:False (初回扱い)。"""
    if prev_map is None:
        return {"available": False, "newly_active": [], "attention_up": [], "cooling": []}
    cur_keys = set()
    for e in ev:
        k = (e["fromName"], e["toName"], e["type"])
        cur_keys.add(k)
        ps = prev_map.get(k)
        if ps is None:
            e["prev_sources"] = None; e["delta_sources"] = None; e["is_new"] = True
        else:
            e["prev_sources"] = ps; e["delta_sources"] = e["sources"] - ps; e["is_new"] = False
    def row(e, extra=None):
        d = {"fromName": e["fromName"], "toName": e["toName"], "type": e["type"], "sources": e["sources"]}
        if extra: d.update(extra)
        return d
    newly = sorted([row(e) for e in ev if e.get("is_new")], key=lambda x: -x["sources"])
    up = sorted([row(e, {"delta": e["delta_sources"]}) for e in ev
                 if e.get("delta_sources") and e["delta_sources"] > 0], key=lambda x: -x["delta"])
    cooling = sorted([{"fromName": k[0], "toName": k[1], "type": k[2], "sources": ps}
                      for k, ps in prev_map.items() if k not in cur_keys], key=lambda x: -x["sources"])
    return {"available": True, "newly_active": newly[:8], "attention_up": up[:6], "cooling": cooling[:8]}

def run_once():
    prev_map, prev_iso = load_prev_events()
    ev, gdelt_ts = fetch_events()
    changes = compute_changes(ev, prev_map)
    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generated_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gdelt": gdelt_ts,
        "compare_to": prev_iso,
        "changes": changes,
        "events": ev,
    }
    json.dump(payload, open("events.json", "w", encoding="utf-8"), ensure_ascii=False)
    c = changes
    print(f"[{time.strftime('%H:%M:%S')}] events.json 更新: {len(ev)} 本 / GDELT {gdelt_ts}")
    if c["available"]:
        print(f"  変化 (前回 {prev_iso} 比): 新規 {len(c['newly_active'])} / 増加 {len(c['attention_up'])} / 沈静 {len(c['cooling'])}")
    else:
        print("  変化: 前回データ無し (初回・基準として保存)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()
    if a.loop:
        while True:
            try: run_once()
            except Exception as e: print("取得失敗:", e, file=sys.stderr)
            time.sleep(15*60)
    else:
        run_once()

if __name__ == "__main__":
    main()
