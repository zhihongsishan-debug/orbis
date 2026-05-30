# ORBIS — Claude Code 引き継ぎ指示書 / プロジェクト仕様

> この文書を Claude Code に渡す（リポジトリ直下に `CLAUDE.md` として置くか、最初のプロンプトに貼る）。
> 既存の4ファイル（`orbis.html` / `ingest.py` / `update.yml` / `SETUP.md`）が手元にあるなら **それを使う**。
> 無い／作り直す場合は「6. 再生成仕様」に従って生成する。

---

## 1. プロダクトのゴール（SSOT — ここからズレないこと）

リアルタイムの世界情勢を **3D地球儀** 上で可視化する。「どの国が・どこへ・何をしているか（武力衝突／緊張／外交／支援）」を、地球上を流れる **ネオンのライン（国→国の方向つき）** で表現する。ユーザーは地球を回し、ラインにホバーで要約・クリックで詳細を見る。

### 確定済みの設計判断（変更禁止。変えるならユーザーに確認）
- **「インターネット全部をリアルタイム検索」は技術的に不可能。** 既存のイベントデータフィードを集約する方式で確定。
- **データの起点は GDELT 2.0 Events（15分粒度の公開フィード）。**
- これは「事実そのもの」ではなく **「報道の集約」**。プロパガンダ完全排除は不可能なので、ソース数などを併記し利用者が偏りを判断できる設計にする（「真実」と銘打たない）。
- **地図表現**: 暗い宇宙背景＋本物の国境（Natural Earth, public domain）＋大気グロー。国→国アークはネオン（太いhalo＋細いcore＋A→Bへ走る彗星状スプライト）。
- **依存は three.js (cdnjs, r128) のみ。** 地図データはHTMLに内蔵し、**実行時に外部CDNの画像へ依存しない**（社内プロキシ／サンドボックスでも動くため）。

---

## 2. 現状の成果物（提供ファイル）

| ファイル | 役割 |
|---|---|
| `orbis.html` | 自己完結の3D地球ビューア。three.js + 内蔵国境。`events.json` があれば読み、無ければ内蔵スナップショット。表示中2分ごとに再取得。HUDに現在時刻／最終更新を表示。 |
| `ingest.py` | GDELT 2.0 Events 最新フィード取得 → 国コードで正規化 → `events.json` 生成。`--loop` で15分ごと。 |
| `.github/workflows/update.yml` | 15分ごとに `ingest.py` 実行 → `orbis.html` と `events.json` を GitHub Pages へデプロイ。 |
| `SETUP.md` | デプロイ手順。 |

→ これらは動作確認済み。**まずそのまま使う。**

---

## 3. リポジトリ構成（この通りに作る）

```
.
├── orbis.html
├── ingest.py
├── CLAUDE.md                     # この指示書
├── SETUP.md
└── .github/
    └── workflows/
        └── update.yml
```

---

## 4. Claude Code への作業指示（順に実行）

1. **Scaffold**: 上記構成でファイルを配置。提供ファイルがあればコピー、無ければ「6. 再生成仕様」で生成。
2. **ローカル検証**:
   - `pip install requests && python ingest.py` を実行。GDELT に到達できれば `events.json`（`{generated, gdelt, events:[...]}` 形式）が生成されることを確認。到達不可環境なら、その旨をユーザーに報告し、HTMLが内蔵スナップショットにフォールバック表示されることを確認。
   - `python -m http.server 8000` で配信し、`http://localhost:8000/orbis.html` を開いて、地球の回転・ネオンアーク・ホバー要約・クリック詳細・国名ラベル・現在時刻クロック・最終更新表示が動くことを確認。
   - **注意**: `file://` 直開きは CORS で `events.json` を読めない。必ず http server 経由で確認。
3. **デプロイ設定**（`SETUP.md` 準拠）:
   - `gh` CLI が使えるなら、リポジトリ作成・push・Pages有効化まで自動化してよい。ただし **Pages の Source を「GitHub Actions」にする操作**と、GitHubアカウント認証はユーザー本人の確認・操作が要る点を明示すること。勝手にアカウント作成・公開はしない。
   - 公開URL: `https://<user>.github.io/<repo>/`
4. **品質改善（ロードマップ／着手順）**:
   1. `ingest.py` の国コード辞書 `CC` を主要主権国家ほぼ全件へ拡張（CAMEO 3文字コード → 和名・首都lat/lng）。
   2. **内戦・国内事象の対応**: 現状は「国A≠国B かつ両国コードあり」しか拾えず内戦が落ちる。`ActionGeo_Lat/Long` を使い、国内事象を**点（hotspotレイヤー）**として別表示する分岐を追加。
   3. CAMEO `EventRootCode` のより細かい和訳・色分け。
   4. パフォーマンス: アーク数が増えた時の上限・クラスタリング・ズーム連動の間引き。
   5. （任意）`borders.json` を分離ファイル化して保守性を上げる（現状はHTML内蔵）。
5. 各改善は **小さくコミット**し、2の検証を都度通す。

---

## 5. 受け入れ基準（Done の定義）
- [ ] http server 経由で `orbis.html` が表示され、地球回転・ズーム・ネオンアーク・ホバー／クリック・国名ラベル・現在時刻／最終更新が機能する。
- [ ] `python ingest.py` が `events.json`（`{generated,gdelt,events}`）を生成し、HTMLが「LIVE」表示に切り替わる（GDELT到達環境）。
- [ ] GDELT不可・events.json無しでも白画面にならずスナップショット表示になる。
- [ ] GitHub Actions が手動実行で成功し、Pages の公開URLで同じ画面が見える。
- [ ] ロードマップ 4-1（国辞書拡張）まで反映。

---

## 6. 再生成仕様（ファイルが無い場合に作り直すための詳細）

### orbis.html
- 依存: `https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js` のみ。フォントは Google Fonts（Saira Condensed / IBM Plex Mono）。
- 構成: 球(暗色)＋**内蔵国境ライン**（Natural Earth ne_110m を簡略化した座標配列を埋め込み）＋経緯線(トグル)＋大気フレネルシェーダ＋星。
- アーク: `QuadraticBezierCurve3`。種別ごとに color（conflict=#ff2d55 / tension=#ffae33 / coop=#27e0ff / aid=#34ffb0）。`TubeGeometry` の halo(太・低透明・加算)＋core(細・高輝度・加算)＋Spriteの彗星ヘッド(curveを周回)。
- 地理変換 `v3(lat,lng,r)`: `phi=(90-lat)π/180, th=(lng+180)π/180; x=-(r sinφ cosθ), y=r cosφ, z=r sinφ sinθ`。
- 操作: ドラッグ回転(globe group rotation)、ホイールでカメラdolly、自動回転トグル、グリッドトグル。
- 当たり判定: アークの core/halo メッシュを raycast。ホバーでツールチップ、クリックで右下readout。
- 国名ラベル: HTML div を毎フレーム `project()` で配置。裏面は法線×視線のdotでフェード。
- データ取り込み: 起動時と2分ごとに `fetch('./events.json',{cache:'no-store'})`。`{generated,gdelt,events}` でも素の配列でも可。失敗時は内蔵 `SNAP` 配列。
- 各イベントの形: `{fromName,toName,type,intensity(1-10),summary,detail,sLat,sLng,eLat,eLng,sources}`。
- HUD: 現在時刻(毎秒)、最終更新(generated / GDELT data time)、種別フィルタ、凡例、出典バッジ。

### ingest.py
- 取得: `http://data.gdeltproject.org/gdelt2/lastupdate.txt` から `*.export.CSV.zip` のURL → DL → unzip → タブ区切りCSV。
- GDELT 2.0 列index: Actor1CountryCode=7, Actor2CountryCode=17, EventRootCode=28, QuadClass=29, NumSources=32, Actor1Geo_Lat/Long=40/41, Actor2Geo_Lat/Long=48/49, ActionGeo_Lat/Long=56/57, SOURCEURL=60。
- 正規化: `CC`(CAMEO国コード→[和名,lat,lng]) に両国があり国A≠国B、`NumSources>=5` のみ採用。`QuadClass`→type(1 coop/2 aid/3 tension/4 conflict)。
- 集約: `(国A,国B,type)` ごとにソース数合算、最頻 `EventRootCode` を要約に。強度 `= clamp(round(log10(sources+1)*4) + (conflictなら+2), 1, 10)`。
- 出力: `events.json = {"generated": ローカル時刻, "gdelt": データ時刻(URLの14桁→UTC), "events": 上位60本}`。
- `--loop` で15分sleepループ。

### borders.json（国境の作り方・再現用）
Natural Earth `ne_110m_admin_0_countries.geojson` を取得し、各Polygon/MultiPolygonの環を座標精度1桁に丸め、連続重複を除去して `[[lng,lat,lng,lat,...], ...]`（環ごとのフラット配列）にして埋め込む。出典: Natural Earth（public domain）。

### update.yml
- `on: schedule(*/15 * * * *), workflow_dispatch, push:main`。
- `permissions: contents:read, pages:write, id-token:write`、`concurrency: pages`。
- steps: checkout → setup-python → `pip install requests` → `python ingest.py || true` → site/ に `orbis.html`→`index.html` と `events.json` をコピー → `actions/upload-pages-artifact@v3` → `actions/deploy-pages@v4`。

---

## 7. 制約・つまずきポイント（必ず守る）
- `file://` 直開きは events.json を CORS で読めない → http server / Pages 経由必須。
- 一部プレビュー環境は外部CDNを **cdnjs のみ** 許可（unpkg等は不可）。three.js は cdnjs から読むこと。
- GitHub Pages の Source は **「GitHub Actions」**（"Deploy from a branch" ではない）。
- cron は best-effort（遅延・スキップあり）。リポジトリ60日無活動でスケジュール自動停止。
- GDELT 生データは粗い（誤ジオコード・コード欠落・重複）。**正規化前提**で扱う。
- ライセンス: 国境=Natural Earth(public domain)。GDELT は比較的自由だが、**商用時は GDELT/各データの利用規約を確認**。

## 8. 将来（商用化・別タスク）
VPS + cron + nginx へ移行、独自ドメイン、events.json 非公開、ログイン／課金、更新頻度向上。orbis.html はそのまま流用可能。
