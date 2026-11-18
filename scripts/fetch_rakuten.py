"""楽天市場商品検索APIから商品を取り、1個あたりの単価を計算して data/<slug>.json に保存する。

必要な環境変数（GitHubのSecretsに登録する）:
  RAKUTEN_APP_ID        アプリID（applicationId）
  RAKUTEN_ACCESS_KEY    アクセスキー（accessKey）
  RAKUTEN_AFFILIATE_ID  アフィリエイトID
任意:
  RAKUTEN_ENDPOINT      APIのURL（仕様変更時に差し替え用）
  SITE_URL              楽天に登録したサイトURL（Refererとして送る）

使い方:
  python scripts/fetch_rakuten.py            # 本番（APIを呼ぶ）
  python scripts/fetch_rakuten.py --sample   # tests/sample_response.json で動作確認
"""
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from quantity import parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
DEFAULT_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"


def call_api(keyword: str, page: int, cfg_site: dict) -> dict:
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "affiliateId": os.environ.get("RAKUTEN_AFFILIATE_ID", ""),
        "keyword": keyword,
        "hits": 30,
        "page": page,
        "sort": "-reviewCount",
        "availability": 1,
        "imageFlag": 1,
        "formatVersion": 2,
        "format": "json",
    }
    url = os.environ.get("RAKUTEN_ENDPOINT", DEFAULT_ENDPOINT) + "?" + urllib.parse.urlencode(params)
    site = os.environ.get("SITE_URL", cfg_site["url"]).rstrip("/") + "/"
    req = urllib.request.Request(url, headers={"Referer": site, "Origin": site.rstrip("/"),
                                               "User-Agent": "morimemo-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def items_of(resp: dict):
    for it in resp.get("Items", []):
        yield it.get("Item", it)  # formatVersion 1/2 の両方に対応


def build_rows(items, cat):
    rows, seen = [], set()
    scale = cat.get("unit_scale", 1)
    for it in items:
        code = it.get("itemCode")
        if code in seen:
            continue
        seen.add(code)
        name = it.get("itemName", "")
        price = it.get("itemPrice")
        qty = parse(name, cat["parse"], cat["unit"])
        if not price or not qty:
            continue
        if (it.get("reviewCount") or 0) < cat.get("min_reviews", 0):
            continue
        imgs = it.get("mediumImageUrls") or []
        img = imgs[0] if imgs else ""
        if isinstance(img, dict):
            img = img.get("imageUrl", "")
        rows.append({
            "name": name[:90],
            "shop": it.get("shopName", ""),
            "price": int(price),
            "qty": round(qty, 3),
            "unit_price": round(price / qty * scale, 2),
            "free_shipping": it.get("postageFlag") == 0,
            "review_avg": it.get("reviewAverage"),
            "review_count": it.get("reviewCount"),
            "url": it.get("affiliateUrl") or it.get("itemUrl", ""),
            "image": img,
        })
    if len(rows) >= 5:  # 読み取りミスによる極端な値を除外
        med = statistics.median(r["unit_price"] for r in rows)
        rows = [r for r in rows if med / 4 <= r["unit_price"] <= med * 4]
    rows.sort(key=lambda r: r["unit_price"])
    return rows


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    sample = "--sample" in sys.argv
    sample_data = json.loads((ROOT / "tests/sample_response.json").read_text(encoding="utf-8")) if sample else {}
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    for cat in cfg["categories"]:
        items = []
        try:
            if sample:
                items = list(items_of(sample_data.get(cat["slug"], {})))
            else:
                for page in (1, 2, 3):
                    items += list(items_of(call_api(cat["keyword"], page, cfg["site"])))
                    time.sleep(1.2)  # 1秒1回の利用制限を守る
        except Exception as e:  # 1カテゴリの失敗で全体を止めない。前回のデータを残す
            print(f"[warn] {cat['slug']}: {e}", file=sys.stderr)
            continue
        rows = build_rows(items, cat)
        if not rows:
            print(f"[warn] {cat['slug']}: 比較できる商品が0件。前回のデータを残します", file=sys.stderr)
            continue
        (out_dir / f"{cat['slug']}.json").write_text(
            json.dumps({"fetched_at": now, "sample": sample, "rows": rows[:30]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ok] {cat['slug']}: {len(rows)}件")


if __name__ == "__main__":
    main()
