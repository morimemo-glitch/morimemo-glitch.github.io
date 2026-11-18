# もりメモ

楽天市場の価格を毎週自動で集めて、日用品などを「1個あたり」の単価で比べるサイト。

## しくみ
- `scripts/fetch_rakuten.py`：楽天APIで商品を取得して、内容量を商品名から読み取り、単価を計算して `data/` に保存する
- `scripts/build.py`：`data/` と `content/` からサイトを `_site/` に生成する
- `.github/workflows/update.yml`：毎週月曜の朝4時17分（日本時間）に、取得・生成・公開を自動で行う。記事を追加したときにも公開する

## 記事の公開
`content/articles/*.md` の先頭にある `status: draft` を `status: published` に変えると公開される。
本文中に `{{ranking:カテゴリ名:件数}}` と書くと、最新のランキング表が入る。

## カテゴリの追加
`config.json` の `categories` に追加する。

## 必要なSecrets（Settings → Secrets and variables → Actions）
- `RAKUTEN_APP_ID`
- `RAKUTEN_ACCESS_KEY`
- `RAKUTEN_AFFILIATE_ID`

## 手元での確認
```
python scripts/fetch_rakuten.py --sample
python scripts/build.py --drafts
```
