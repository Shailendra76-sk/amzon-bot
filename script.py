"""
LootBazaar Auto-Deal Poster
============================
Sources (sab combine):
  1. DesiDime Amazon deals (/new + /amazon)
  2. Amazon.in/deals page scrape
  3. Amazon RSS feeds (Lightning Deals, Today's Deals)
  4. DesiDime "hot" deals filtered by Amazon

Output:
  - WhatsApp Group (Green API)
  - Facebook Page (Graph API)
  - Saare links pe affiliate tag: ?tag=sk200709-21
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ============================================================
# CONFIG
# ============================================================
AMAZON_AFFILIATE_TAG = "sk200709-21"
MIN_HOTNESS          = 20
MAX_DEALS_PER_RUN    = 8
POSTED_FILE          = "posted_deals.json"

# WhatsApp (Green API)
GREEN_API_INSTANCE_ID = os.getenv("GREEN_API_INSTANCE_ID", "7107592101")
GREEN_API_TOKEN       = os.getenv("GREEN_API_TOKEN", "")
WHATSAPP_CHAT_JID     = "120363424914979115@g.us"   # tumhara group JID

# Facebook
FB_PAGE_ID    = "1205433809300407"   # Loot Bazaar India page
FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")


# ============================================================
# UTILITIES
# ============================================================
def load_posted():
    if os.path.exists(POSTED_FILE):
        try:
            return set(json.load(open(POSTED_FILE)))
        except Exception:
            return set()
    return set()


def save_posted(posted):
    json.dump(list(posted), open(POSTED_FILE, "w"))


def add_affiliate_tag(url: str) -> str:
    """Amazon URL pe sk200709-21 tag lagao."""
    if "amazon." not in url:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs["tag"] = [AMAZON_AFFILIATE_TAG]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def extract_asin(url: str) -> str | None:
    m = ASIN_RE.search(url or "")
    return m.group(1) if m else None


def build_amazon_url(asin: str) -> str:
    return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"


# ============================================================
# SOURCE 1 — DesiDime Amazon deals
# ============================================================
def scrape_desidime():
    """DesiDime se sirf Amazon store ki deals nikalo."""
    deals = []
    for path in ["/amazon", "/new"]:
        try:
            url = f"https://www.desidime.com{path}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.find_all("article", attrs={"data-gtm-deal-id": True})
            for c in cards:
                try:
                    deal_id  = c.get("data-gtm-deal-id")
                    title_el = c.find("a", class_=re.compile("title", re.I)) or c.find("h3")
                    title    = title_el.get_text(strip=True) if title_el else ""
                    store_el = c.find(attrs={"data-gtm-store": True})
                    store    = (store_el.get("data-gtm-store") if store_el else "").lower()
                    hot_el   = c.find(class_=re.compile("hotness|temperature|temp", re.I))
                    hot_txt  = hot_el.get_text(strip=True) if hot_el else "0"
                    hotness  = int(re.sub(r"\D", "", hot_txt) or "0")
                    deal_link_el = c.find("a", href=re.compile(r"/deals/"))
                    deal_url     = "https://www.desidime.com" + deal_link_el["href"] if deal_link_el else ""

                    if "amazon" not in store:
                        continue
                    deals.append({
                        "id":       deal_id,
                        "title":    title,
                        "store":    store,
                        "hotness":  hotness,
                        "deal_url": deal_url,
                        "source":   "desidime",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[WARN] DesiDime {path} failed: {e}")
    print(f"[INFO] DesiDime: {len(deals)} Amazon deals found")
    return deals


def resolve_amazon_asin_from_desidime(deal_url: str) -> str | None:
    """DesiDime deal page se Amazon ASIN nikalo."""
    try:
        r = requests.get(deal_url, headers=HEADERS, timeout=15)
        # Method 1: HTML mein direct Amazon link
        asin = extract_asin(r.text)
        if asin:
            return asin

        # Method 2: visit.desidime.com redirect follow karo
        soup  = BeautifulSoup(r.text, "html.parser")
        visit = soup.find("a", href=re.compile(r"visit\.desidime\.com"))
        if visit:
            try:
                rr = requests.get(
                    visit["href"], headers=HEADERS,
                    timeout=15, allow_redirects=True,
                )
                asin = extract_asin(rr.url) or extract_asin(rr.text)
                if asin:
                    return asin
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] ASIN resolve failed: {e}")
    return None


# ============================================================
# SOURCE 2 — Amazon.in/deals
# ============================================================
def scrape_amazon_deals():
    deals = []
    try:
        r = requests.get("https://www.amazon.in/deals", headers=HEADERS, timeout=15)
        # ASIN extract karo HTML se
        asins = list(set(ASIN_RE.findall(r.text)))[:20]
        for asin in asins:
            deals.append({
                "id":      f"amz_{asin}",
                "title":   f"Amazon Deal — {asin}",
                "asin":    asin,
                "store":   "amazon",
                "hotness": 100,  # Amazon deals page = trusted
                "source":  "amazon_deals",
            })
    except Exception as e:
        print(f"[WARN] Amazon deals page failed: {e}")
    print(f"[INFO] Amazon.in/deals: {len(deals)} deals found")
    return deals


# ============================================================
# SOURCE 3 — Amazon RSS feeds
# ============================================================
def scrape_amazon_rss():
    """Amazon RSS feeds (alag-alag categories ke liye)."""
    feeds = [
        "https://www.amazon.in/gp/rss/bestsellers/electronics",
        "https://www.amazon.in/gp/rss/bestsellers/kitchen",
        "https://www.amazon.in/gp/rss/bestsellers/apparel",
    ]
    deals = []
    for feed in feeds:
        try:
            r = requests.get(feed, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "xml")
            items = soup.find_all("item")[:5]
            for it in items:
                title = it.title.get_text(strip=True) if it.title else ""
                link  = it.link.get_text(strip=True) if it.link else ""
                asin  = extract_asin(link)
                if asin:
                    deals.append({
                        "id":      f"rss_{asin}",
                        "title":   title,
                        "asin":    asin,
                        "store":   "amazon",
                        "hotness": 80,
                        "source":  "amazon_rss",
                    })
        except Exception as e:
            print(f"[WARN] RSS {feed} failed: {e}")
    print(f"[INFO] Amazon RSS: {len(deals)} deals found")
    return deals


# ============================================================
# POSTERS
# ============================================================
def post_to_whatsapp(message: str) -> bool:
    if not GREEN_API_TOKEN:
        print("[WARN] GREEN_API_TOKEN missing")
        return False
    url = (f"https://7107.api.greenapi.com/waInstance"
           f"{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}")
    try:
        r = requests.post(url, json={
            "chatId": WHATSAPP_CHAT_JID,
            "message": message,
        }, timeout=20)
        if r.status_code == 200:
            print(f"[OK] WhatsApp sent: {r.json().get('idMessage')}")
            return True
        print(f"[ERR] WhatsApp {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"[ERR] WhatsApp: {e}")
    return False


def post_to_facebook(message: str, link: str) -> bool:
    if not FB_PAGE_TOKEN:
        print("[WARN] FB_PAGE_TOKEN missing")
        return False
    url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/feed"
    try:
        r = requests.post(url, data={
            "message":      message,
            "link":         link,
            "access_token": FB_PAGE_TOKEN,
        }, timeout=20)
        if r.status_code == 200:
            print(f"[OK] Facebook posted: {r.json().get('id')}")
            return True
        print(f"[ERR] Facebook {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"[ERR] Facebook: {e}")
    return False


def format_message(title: str, url: str, hotness: int = 0) -> str:
    fire = "🔥" * min(max(hotness // 100, 1), 3)
    return (
        f"{fire} *AMAZON LOOT DEAL* {fire}\n\n"
        f"📦 {title}\n\n"
        f"🛒 Buy Now: {url}\n\n"
        f"💬 Join: https://whatsapp.com/channel/0029VbCy92nBadmau8nw0v3j"
    )


# ============================================================
# MAIN
# ============================================================
def main():
    posted = load_posted()
    print(f"[INFO] Already posted: {len(posted)} deals")

    # Saare sources combine karo
    all_deals = []
    all_deals += scrape_desidime()
    all_deals += scrape_amazon_deals()
    all_deals += scrape_amazon_rss()

    # Duplicates hatao (same ASIN ek hi baar)
    seen_asin, unique = set(), []
    for d in all_deals:
        if d["id"] in posted:
            continue
        if d.get("hotness", 0) < MIN_HOTNESS and d["source"] == "desidime":
            continue

        # ASIN resolve karo
        asin = d.get("asin")
        if not asin and d.get("deal_url"):
            asin = resolve_amazon_asin_from_desidime(d["deal_url"])
        if not asin:
            print(f"[SKIP] No ASIN: {d['title'][:50]}")
            continue
        if asin in seen_asin:
            continue
        seen_asin.add(asin)
        d["asin"]        = asin
        d["amazon_url"]  = build_amazon_url(asin)
        unique.append(d)

    print(f"[INFO] {len(unique)} unique Amazon deals to post")

    posted_count = 0
    for d in unique[:MAX_DEALS_PER_RUN]:
        msg = format_message(d["title"], d["amazon_url"], d.get("hotness", 0))
        wa_ok = post_to_whatsapp(msg)
        fb_ok = post_to_facebook(msg, d["amazon_url"])
        if wa_ok or fb_ok:
            posted.add(d["id"])
            posted_count += 1
            time.sleep(3)  # rate limit ke liye

    save_posted(posted)
    print(f"[DONE] {posted_count} new deals posted. Total tracked: {len(posted)}")


if __name__ == "__main__":
    main()
