# ORBIS デプロイ手順（GitHub Actions + Pages）

これで **公開URLを開くだけで常に最新** になる。自分のPCは起動しっぱなしにしなくてよい。

## 0. 用意するファイル（3つ）
ダウンロードした以下をリポジトリに置く（フォルダ構成が重要）:

```
（リポジトリのルート）
├── orbis.html
├── ingest.py
└── .github/
    └── workflows/
        └── update.yml      ← ダウンロードした update.yml をこの場所・この名前で置く
```

## 1. GitHubリポジトリを作る
- GitHub で新規リポジトリを作成（例: `orbis`）。
- **Public 推奨**（無料でPagesが使える）。Private にすると Pages は有料プランが必要。
- 上記3ファイルをアップロード（Web画面の「Add file → Upload files」でOK。`.github/workflows/` は
  ファイル名を `.github/workflows/update.yml` と入力すればフォルダごと作られる）。

## 2. Pages を「GitHub Actions」配信に設定
- リポジトリの **Settings → Pages** を開く。
- **Build and deployment → Source** を **「GitHub Actions」** に変更。
  （※ "Deploy from a branch" ではない）

## 3. 初回デプロイを走らせる
- **Actions** タブ → 「Update ORBIS feed」を選択 → **Run workflow**（手動実行）。
- 緑のチェックが付けば成功。失敗時はログを確認（多くはPages設定漏れ）。

## 4. 公開URLを開く
- デプロイ成功後のURL: `https://<ユーザー名>.github.io/<リポジトリ名>/`
- 以後はこのURLを開くだけ。15分ごとに自動更新され、画面の「最終更新」に
  取得時刻と GDELT データ時刻が出る。

---

## 仕組み（要点）
- `update.yml` が 15分ごとに `ingest.py` を実行 → `events.json` を生成 → orbis.html と一緒にPagesへデプロイ。
- `orbis.html` は表示中も2分ごとに `events.json` を取り直すので、開きっぱなしでも最新に追従する。
- `ingest.py` が失敗した回は、orbis.html 内蔵の静的スナップショットにフォールバックする（真っ白にはならない）。

## 注意・既知の限界
- **cronはbest-effort**: GitHubの都合で15分ちょうどにならず、20〜30分遅れたりスキップされることがある。
- **60日ルール**: リポジトリに60日間活動がないと、スケジュール実行が自動停止する。たまにpushするか手動実行で再開。
- **公開範囲**: Publicリポジトリだと orbis.html も events.json も誰でも見える。非公開にしたいなら Private + 有料Pages か、VPS構成へ。
- **CDNキャッシュ**: events.json がエッジで数分キャッシュされ、反映が少し遅れることがある（元データが約15分粒度なので実用上は問題になりにくい）。
- **GDELT到達性**: Actionsランナーから data.gdeltproject.org へ通信できる必要がある（通常は問題なし）。

## 商用・大規模に伸ばす場合（次段階）
- 独自ドメイン、アクセス制御（課金・ログイン）、高頻度更新、events.json非公開 が必要になったら
  小規模VPS + cron + nginx 構成へ移行（Pagesからの移植は orbis.html をそのまま使える）。
