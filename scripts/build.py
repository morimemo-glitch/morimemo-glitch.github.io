"""data/ と content/ からサイトを _site/ に書き出す。

  python scripts/build.py            # 公開用（status: published の記事だけ）
  python scripts/build.py --drafts   # 確認用（下書きも含める）
"""
import html
import json
import os
import re
import shutil
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
JST = timezone(timedelta(hours=9))
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SITE = CFG["site"]
CATS = {c["slug"]: c for c in CFG["categories"]}
SECTIONS = {s["slug"]: s for s in CFG["sections"]}
esc = html.escape
CSS_VER = "4"
WEEK = "月火水木金土日"


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
            flush(); out.append(f'<p class="aside">{inline(s[2:])}</p>'); continue
        if lst or table: flush()
        para.append(s.strip())
    flush()
    return "\n".join(out)


# ---------- データ・リンク ----------
def load_data(slug):
    p = ROOT / "data" / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def aff(url: str) -> str:
    a = os.environ.get("RAKUTEN_AFFILIATE_ID", "").strip()
    if not a:
        return url
    q = urllib.parse.quote(url, safe="")
    return f"https://hb.afl.rakuten.co.jp/hgc/{urllib.parse.quote(a)}/?pc={q}&m={q}"


def search_url(keyword: str, extra: str = "") -> str:
    return aff("https://search.rakuten.co.jp/search/mall/" + urllib.parse.quote(keyword) + "/" + extra)


def out_link(url, text, cls="out"):
    return f'<a class="{cls}" href="{esc(url)}" rel="sponsored noopener" target="_blank">{esc(text)}</a>'


def yen(v):
    return f"{v:,.2f}円" if v < 10 else f"{v:,.0f}円"


def best_of(slug):
    d = load_data(slug)
    return d["rows"][0] if d and d.get("rows") else None


def ranking_table(slug, n=10):
    cat, data = CATS.get(slug), load_data(slug)
    if not cat:
        return ""
    if not data:
        return ('<div class="pending"><p>このランキングは、楽天の価格データを取得できるようになりしだい自動で表示されます。'
                'それまでは楽天市場の検索結果から探せます。</p>'
                + out_link(search_url(cat["keyword"]), f"楽天市場で「{cat['name']}」の価格を見る", "btn") + "</div>")
    price_label = cat.get("price_label", "価格")
    rows = []
    for i, r in enumerate(data["rows"][:n], 1):
        ship = "送料無料" if r["free_shipping"] else "送料別"
        rev = f'★{r["review_avg"]}（{r["review_count"]:,}件）' if r.get("review_count") else ""
        badge = '<span class="best">最安</span>' if i == 1 else ""
        rows.append(
            f'<tr{" class=\"top\"" if i == 1 else ""}><td class="n">{i}</td>'
            f'<td class="item">{badge}{out_link(r["url"], r["name"], "")}<div class="sub">{esc(r["shop"])}・{ship} {rev}</div></td>'
            f'<td class="num em" data-label="{esc(cat["unit_label"])}">{yen(r["unit_price"])}</td>'
            f'<td class="num" data-label="{esc(price_label)}">{r["price"]:,}円</td></tr>')
    sample = '<p class="warn">※動作確認用のサンプルデータです。</p>' if data.get("sample") else ""
    return (f'{sample}<div class="tbl"><table class="rank"><thead><tr><th>#</th><th>商品</th>'
            f'<th class="num">{esc(cat["unit_label"])}</th><th class="num">{esc(price_label)}</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>"
            f'<p class="meta">{esc(data["fetched_at"])} 時点の楽天市場の価格。内容量は商品名から自動計算しています'
            '（<a href="/method/">計算方法</a>）。購入前にショップのページで必ず確認してください。</p>')


def shortcode(s):
    parts = s.split(":")
    if parts[0] == "ranking":
        return ranking_table(parts[1], int(parts[2]) if len(parts) > 2 else 10)
    if parts[0] == "search":  # {{search:キーワード:表示名}}
        label = parts[2] if len(parts) > 2 else parts[1]
        return f'<p>{out_link(search_url(parts[1]), "楽天市場で「" + label + "」の価格を見る", "btn")}</p>'
    if parts[0] == "event":
        return event_box(full=True)
    if parts[0] == "verdict":
        return verdict(parts[1])
    return ""


def verdict(slug):
    """記事冒頭の「先に結論」。データがあれば最安の1品、なければ検索リンク"""
    cat, data = CATS.get(slug), load_data(slug)
    if not cat:
        return ""
    if data and data.get("rows"):
        r = data["rows"][0]
        return ('<div class="verdict"><div class="v-label">先に結論</div>'
                f'<p>いま楽天市場で<strong>{esc(cat["unit_label"])}がいちばん安い{esc(cat["name"])}</strong>は、'
                f'{esc(r["name"][:40])}（{yen(r["unit_price"])}）です。</p>'
                + out_link(r["url"], "楽天で価格と在庫を見る", "btn")
                + f'<p class="meta">{esc(data["fetched_at"])} 時点の価格です。</p></div>')
    return ('<div class="verdict"><div class="v-label">先に結論</div>'
            f'<p>{esc(cat["name"])}は、パッケージの大きさではなく<strong>{esc(cat["unit_label"])}の値段</strong>で比べるのが確実です。'
            '下の表で比べるか、楽天市場で直接探せます。</p>'
            + out_link(search_url(cat["keyword"]), f"楽天市場で「{cat['name']}」の価格を見る", "btn") + "</div>")


def fmt_dt(s):
    d = datetime.strptime(s, "%Y-%m-%d %H:%M")
    return f"{d.month}月{d.day}日（{WEEK[d.weekday()]}）{d.hour}:{d.minute:02d}"


def event_box(full=False):
    ev = CFG.get("next_event")
    if not ev:
        return ""
    status = "" if ev.get("confirmed") else '<span class="tag">予想</span>'
    note = "" if ev.get("confirmed") else "例年の開催パターンからの予想です。公式発表が出たら更新します。"
    link = "" if full else f' <a href="{ev["article"]}">買い回りの準備 →</a>'
    return (f'<div class="event"><div class="event-label">次の大型セール {status}</div>'
            f'<div class="event-name">{esc(ev["name"])}</div>'
            f'<div class="event-date">{fmt_dt(ev["start"])} 〜 {fmt_dt(ev["end"])}</div>'
            f'<p class="meta">{note}{link}</p></div>')


# ---------- テンプレート ----------
def page(title, body, path="/", desc=""):
    full = f"{title}｜{SITE['title']}" if title != SITE["title"] else f"{SITE['title']}｜{SITE['tagline']}"
    canon = SITE["url"].rstrip("/") + path
    nav = "".join(f'<a href="/{s}/">{esc(SECTIONS[s]["name"])}</a>' for s in ("sale", "tanka", "bichiku"))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(full)}</title><meta name="description" content="{esc(desc or SITE['tagline'])}">
<meta name="google-site-verification" content="M9nelkQPmXNrqe5-9lRZwhxtoKR0AWkJAvOJi-WPGn0">
<link rel="canonical" href="{canon}"><link rel="stylesheet" href="/assets/style.css?v={CSS_VER}">
</head><body>
<header class="site"><div class="wrap">
<a class="logo" href="/">もりメモ</a><nav>{nav}</nav>
</div><p class="pr wrap">このサイトは楽天アフィリエイトを利用しています（PR）</p></header>
<main class="wrap">{body}</main>
<footer class="wrap"><p><a href="/method/">価格と計算方法</a> ／ <a href="/about/">運営について</a> ／ <a href="/privacy/">プライバシーポリシー</a></p>
<p class="credit"><a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">Supported by Rakuten Developers</a></p></footer>
</body></html>"""


def write(path, content):
    p = OUT / path.strip("/") if path.endswith((".xml", ".txt")) else OUT / path.strip("/") / "index.html"
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


def article_list(arts):
    if not arts:
        return '<p class="meta">記事は準備中です。</p>'
    return '<ul class="list">' + "".join(
        f'<li><span class="date">{esc(a["date"])}</span><a href="{a["path"]}">{esc(a["title"])}</a></li>' for a in arts) + "</ul>"


def tanka_table(slugs):
    rows = []
    for s in slugs:
        c, b = CATS[s], best_of(s)
        val = f'<span class="em">{yen(b["unit_price"])}</span>' if b else '<span class="meta">取得待ち</span>'
        rows.append(f'<tr><td><a href="/ranking/{s}/">{esc(c["name"])}</a></td>'
                    f'<td class="meta">{esc(c["unit_label"])}</td><td class="num">{val}</td></tr>')
    return ('<div class="tbl"><table class="index"><thead><tr><th>品目</th><th>単位</th>'
            '<th class="num">いま最安</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


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
        path = f"/articles/{p.stem}/"
        sec = SECTIONS.get(meta.get("section", ""), None)
        badge = '<p class="warn">【下書き】まだ公開されていません</p>' if meta.get("status") != "published" else ""
        crumb = f'<a href="/{sec["slug"]}/">{esc(sec["name"])}</a>' if sec else ""
        upd = f'・更新 {esc(meta["updated"])}' if meta.get("updated") else ""
        html_body = (f'<article>{badge}<p class="crumb">{crumb}</p><h1>{esc(meta.get("title", p.stem))}</h1>'
                     f'<p class="meta">公開 {esc(meta.get("date", ""))}{upd}</p>{md(body)}</article>')
        write(path, page(meta.get("title", p.stem), html_body, path, meta.get("description", "")))
        arts.append({"date": meta.get("date", ""), "title": meta.get("title", p.stem), "path": path,
                     "section": meta.get("section", "")})
        urls.append(path)
    arts.sort(key=lambda a: a["date"], reverse=True)

    # 単価ランキング
    for slug, cat in CATS.items():
        path = f"/ranking/{slug}/"
        body = (f'<p class="crumb"><a href="/tanka/">単価ランキング</a></p>'
                f'<h1>{esc(cat["name"])}　{esc(cat["unit_label"])}の安い順</h1>'
                f'<p>楽天市場の{esc(cat["name"])}を、{esc(cat["unit_label"])}の値段に直して並べています。'
                'パッケージの大きさやロール数ではなく、中身の量で比べるので、内容量が減った「ステルス値上げ」も見抜けます。</p>'
                + ranking_table(slug, 30))
        write(path, page(f'{cat["name"]} {cat["unit_label"]}の安い順', body, path))
        urls.append(path)

    # セクションページ
    for s, sec in SECTIONS.items():
        path = f"/{s}/"
        body = f'<h1>{esc(sec["name"])}</h1><p>{esc(sec["desc"])}</p>'
        if s == "sale":
            body += event_box()
        cats = [c for c in CATS if CATS[c]["section"] == s]
        if cats:
            body += "<h2>単価の一覧</h2>" + tanka_table(cats)
        body += "<h2>記事</h2>" + article_list([a for a in arts if a["section"] == s])
        write(path, page(sec["name"], body, path, sec["desc"]))
        urls.append(path)

    # トップ
    tanka_slugs = [c for c in CATS if CATS[c]["section"] in ("tanka", "bichiku")]
    top = (f'<p class="lead">{esc(SITE["tagline"])}。楽天市場の価格を毎週集めて、'
           '「1mあたり」「100gあたり」など中身の量あたりの値段に直しています。</p>'
           + event_box()
           + '<h2>単価ランキング <a class="more" href="/tanka/">すべて</a></h2>' + tanka_table(tanka_slugs)
           + '<h2>新着記事</h2>' + article_list(arts[:10]))
    write("/", page(SITE["title"], top, "/"))

    # 固定ページ
    for p in (ROOT / "content/pages").glob("*.md"):
        meta, body = read_md(p)
        path = f"/{p.stem}/"
        write(path, page(meta.get("title", p.stem), f'<article><h1>{esc(meta.get("title", ""))}</h1>{md(body)}</article>', path))
        urls.append(path)

    base = SITE["url"].rstrip("/")
    today = datetime.now(JST).strftime("%Y-%m-%d")
    sm = "".join(f"<url><loc>{base}{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")
    print(f"built {len(urls)} pages -> {OUT}")


if __name__ == "__main__":
    main()
