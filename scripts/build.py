"""data/ と content/ からサイトを _site/ に書き出す。

  python scripts/build.py            # 公開用（status: published の記事だけ）
  python scripts/build.py --drafts   # 確認用（下書きも含める）
"""
import html
import os
import urllib.parse
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
JST = timezone(timedelta(hours=9))
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SITE = CFG["site"]
CATS = {c["slug"]: c for c in CFG["categories"]}
esc = html.escape


# ---------- Markdown（必要最低限） ----------
def inline(t: str) -> str:
    t = esc(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
    return t


def md(text: str) -> str:
    out, para, lst, table = [], [], None, []

    def flush():
        nonlocal para, lst, table
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|?[\s:\-|]+\|?", r)]
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            h = "".join(f"<th>{inline(c)}</th>" for c in cells[0])
            b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f'<div class="tbl"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>')
            table = []

    for line in text.splitlines():
        s = line.rstrip()
        if s.startswith("{{") and s.endswith("}}"):
            flush(); out.append(shortcode(s[2:-2])); continue
        if not s.strip():
            flush(); continue
        m = re.match(r"(#{2,4})\s+(.*)", s)
        if m:
            flush(); n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); continue
        if s.startswith("|"):
            if para or lst: flush()
            table.append(s); continue
        m = re.match(r"\s*(?:([-*])|(\d+)\.)\s+(.*)", s)
        if m:
            tag = "ul" if m.group(1) else "ol"
            if para or table or (lst and lst[0] != tag): flush()
            if not lst: lst = (tag, [])
            lst[1].append(m.group(3)); continue
        if s.startswith("> "):
            flush(); out.append(f'<div class="note">{inline(s[2:])}</div>'); continue
        if lst or table: flush()
        para.append(s.strip())
    flush()
    return "\n".join(out)


# ---------- ランキング表 ----------
def load_data(slug):
    p = ROOT / "data" / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def fmt_unit(cat, v):
    return f"{v:,.2f}円" if v < 10 else f"{v:,.0f}円"


def search_link(cat):
    """楽天市場の検索結果へのアフィリエイトリンク（APIのデータがないときの代わり）"""
    url = "https://search.rakuten.co.jp/search/mall/" + urllib.parse.quote(cat["keyword"]) + "/"
    aff = os.environ.get("RAKUTEN_AFFILIATE_ID", "").strip()
    if aff:
        url = (f"https://hb.afl.rakuten.co.jp/hgc/{urllib.parse.quote(aff)}/?pc="
               + urllib.parse.quote(url, safe="") + "&m=" + urllib.parse.quote(url, safe=""))
    return (f'<p class="cta"><a href="{esc(url)}" rel="sponsored noopener" target="_blank">'
            f'楽天市場で「{esc(cat["name"])}」を探す →</a></p>')


def ranking_table(slug, n=10):
    cat, data = CATS.get(slug), load_data(slug)
    if not cat:
        return ""
    if not data:
        return ('<div class="note">単価ランキングは準備中です。準備ができしだい、ここに自動で表示されます。</div>'
                + search_link(cat))
    price_label = cat.get("price_label", "価格")
    rows = []
    for i, r in enumerate(data["rows"][:n], 1):
        ship = '<span class="tag">送料無料</span>' if r["free_shipping"] else '<span class="tag gray">送料別</span>'
        img = f'<img src="{esc(r["image"])}" alt="" loading="lazy" width="64" height="64">' if r["image"] else ""
        rev = f'★{r["review_avg"]}（{r["review_count"]:,}件）' if r.get("review_count") else ""
        rows.append(
            f'<tr><td class="rank">{i}</td><td class="img">{img}</td>'
            f'<td><a href="{esc(r["url"])}" rel="sponsored noopener" target="_blank">{esc(r["name"])}</a>'
            f'<div class="sub">{esc(r["shop"])} {ship} {rev}</div></td>'
            f'<td class="num"><strong>{fmt_unit(cat, r["unit_price"])}</strong></td>'
            f'<td class="num">{r["price"]:,}円</td></tr>')
    sample = '<div class="note warn">※これは動作確認用のサンプルデータです。</div>' if data.get("sample") else ""
    return (f'{sample}<div class="tbl"><table class="rank-table"><thead><tr><th>#</th><th></th><th>商品</th>'
            f'<th>{esc(cat["unit_label"])}</th><th>{esc(price_label)}</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>"
            f'<p class="meta">{esc(data["fetched_at"])} 時点の楽天市場の価格です。内容量は商品名から自動で計算しているため、'
            '購入前に必ずショップのページで価格・内容量・送料をご確認ください。</p>')


def shortcode(s):
    parts = s.split(":")
    if parts[0] == "ranking":
        return ranking_table(parts[1], int(parts[2]) if len(parts) > 2 else 10)
    if parts[0] == "updated":
        d = load_data(parts[1])
        return f'<p class="meta">価格更新：{esc(d["fetched_at"])}</p>' if d else ""
    return ""


# ---------- テンプレート ----------
CSS_VER = "2"


def page(title, body, path="/", desc=""):
    full = f"{title}｜{SITE['title']}" if title != SITE["title"] else f"{SITE['title']}｜{SITE['tagline']}"
    canon = SITE["url"].rstrip("/") + path
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(full)}</title><meta name="description" content="{esc(desc or SITE['tagline'])}">
<link rel="canonical" href="{canon}"><link rel="stylesheet" href="/assets/style.css?v={CSS_VER}">
</head><body>
<div class="pr">当サイトは楽天アフィリエイトを利用しています（PR）</div>
<header><a class="logo" href="/">{esc(SITE['title'])}</a><span class="tag-line">{esc(SITE['tagline'])}</span></header>
<main>{body}</main>
<footer><a href="/about/">このサイトについて</a> ・ <a href="/privacy/">プライバシーポリシー</a>
<div class="credit"><a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">Supported by Rakuten Developers</a></div></footer>
</body></html>"""


def write(path, content):
    p = OUT / path.strip("/") / "index.html" if not path.endswith(".xml") and not path.endswith(".txt") else OUT / path.strip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def read_md(p: Path):
    text = p.read_text(encoding="utf-8")
    meta, body = {}, text
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return meta, body


def main():
    drafts = "--drafts" in sys.argv
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "assets", OUT / "assets")
    urls = ["/"]

    # 記事
    arts = []
    for p in sorted((ROOT / "content/articles").glob("*.md")):
        meta, body = read_md(p)
        if meta.get("status") != "published" and not drafts:
            continue
        slug = p.stem
        path = f"/articles/{slug}/"
        badge = '<div class="note warn">【下書き】まだ公開されていません</div>' if meta.get("status") != "published" else ""
        html_body = (f'<article>{badge}<h1>{esc(meta.get("title", slug))}</h1>'
                     f'<p class="meta">{esc(meta.get("date", ""))}</p>{md(body)}</article>')
        write(path, page(meta.get("title", slug), html_body, path, meta.get("description", "")))
        arts.append((meta.get("date", ""), meta.get("title", slug), path, meta.get("category", "")))
        urls.append(path)
    arts.sort(reverse=True)

    # ランキングページ
    for slug, cat in CATS.items():
        path = f"/ranking/{slug}/"
        body = (f'<h1>{esc(cat["name"])} {esc(cat["unit_label"])}の安さランキング</h1>'
                f'<p>楽天市場の{esc(cat["name"])}を、{esc(cat["unit_label"])}の価格で安い順に並べています。毎週自動で更新しています。</p>'
                + ranking_table(slug, 30))
        write(path, page(f'{cat["name"]} {cat["unit_label"]}ランキング', body, path))
        urls.append(path)

    # トップ
    groups = {}
    for c in CATS.values():
        groups.setdefault(c["group"], []).append(c)
    rank_html = "".join(
        f'<h3>{esc(g)}</h3><ul class="cards">' + "".join(
            f'<li><a href="/ranking/{c["slug"]}/">{esc(c["name"])}<span>{esc(c["unit_label"])}</span></a></li>' for c in cs)
        + "</ul>" for g, cs in groups.items())
    art_html = "".join(f'<li><a href="{p}">{esc(t)}</a> <span class="meta">{esc(d)}</span></li>' for d, t, p, _ in arts) \
        or "<li>記事は準備中です。</li>"
    top = (f'<section class="hero"><h1>{esc(SITE["tagline"])}</h1>'
           '<p>楽天市場の価格を毎週自動で集めて、「1mあたり」「100gあたり」など、本当にお得な単価で比べています。</p></section>'
           f'<h2>単価ランキング</h2>{rank_html}<h2>新着記事</h2><ul class="list">{art_html}</ul>')
    write("/", page(SITE["title"], top, "/"))

    # 固定ページ
    for p in (ROOT / "content/pages").glob("*.md"):
        meta, body = read_md(p)
        path = f"/{p.stem}/"
        write(path, page(meta.get("title", p.stem), f'<article><h1>{esc(meta.get("title", ""))}</h1>{md(body)}</article>', path))
        urls.append(path)

    # sitemap / robots
    base = SITE["url"].rstrip("/")
    today = datetime.now(JST).strftime("%Y-%m-%d")
    sm = "".join(f"<url><loc>{base}{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")
    print(f"built {len(urls)} pages -> {OUT}")


if __name__ == "__main__":
    main()
