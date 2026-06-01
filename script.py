import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
AMAZON_AFFILIATE_TAG  = "sk200709-21"

# Green API (WhatsApp)
GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "7107592101")
GREEN_API_TOKEN       = os.environ.get("GREEN_API_TOKEN", "")
GREEN_API_BASE_URL    = "https://7107.api.greenapi.com"
WHATSAPP_CHANNEL_JID  = "120363424914979115@g.us"

# Facebook Page
FB_PAGE_ID            = "61590532501423"
FB_PAGE_TOKEN         = os.environ.get("FB_PAGE_TOKEN", "")

POSTED_DEALS_FILE     = "posted_deals.json"
MIN_HOTNESS           = 20
MAX_DEALS_PER_RUN     = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# ─────────────────────────────────────────────
# Posted deals tracker
# ─────────────────────────────────────────────
def load_posted_deals() -> list:
    if os.path.exists(POSTED_DEALS_FILE):
        with open(POSTED_DEALS_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_posted_deals(deals: list):
    with open(POSTED_DEALS_FILE, "w") as f:
        json.dump(deals, f, indent=2)

# ─────────────────────────────────────────────
# SOURCE 1: DesiDime /new se Amazon deals
# ─────────────────────────────────────────────
def get_desidime_deals() -> list:
    deals = []
    try:
        resp = requests.get("https://www.desidime.com/new", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for article in soup.find_all("article", attrs={"data-gtm-deal-id": True}):
            deal_id = article["data-gtm-deal-id"].strip()
            store   = article.get("data-gtm-store", "").strip().lower()

            if "amazon" not in store and "other" not in store:
                continue

            title_div = article.find("div", class_="custom-card-title")
            if not title_div:
                continue
            link_tag = title_div.find("a", href=True)
            if not link_tag:
                continue

            title        = link_tag.get_text(strip=True)
            deal_rel_url = link_tag["href"]
            desidime_url = (
                "https://www.desidime.com" + deal_rel_url
                if deal_rel_url.startswith("/") else deal_rel_url
            )

            if "amazon" not in store and "amazon" not in title.lower():
                continue

            hotness = 0
            hotness_span = article.find("span", class_=re.compile(r"hotness_value_" + deal_id))
            if hotness_span:
                raw = hotness_span.get_text(strip=True).replace("°", "")
                if raw.isdigit():
                    hotness = int(raw)

            visit_url = None
            buy_now = article.find("a", class_=re.compile(r"gtm_buy_now_homepage"), href=True)
            if buy_now:
                href = buy_now["href"]
                if href.startswith("http"):
                    visit_url = href

            deals.append({
                "id":           f"dd_{deal_id}",
                "title":        title,
                "desidime_url": desidime_url,
                "visit_url":    visit_url,
                "hotness":      hotness,
                "source":       "DesiDime",
                "asin":         None,
            })

    except Exception as e:
        print(f"[WARN] DesiDime error: {e}")

    print(f"[SOURCE] DesiDime: {len(deals)} Amazon deals")
    return deals

# ─────────────────────────────────────────────
# SOURCE 2: Amazon India RSS Feeds
# ─────────────────────────────────────────────
def get_rss_deals() -> list:
    rss_urls = [
        ("https://www.amazon.in/rss/bestsellers/electronics/", "Electronics"),
        ("https://www.amazon.in/rss/bestsellers/apparel/", "Fashion"),
        ("https://www.amazon.in/rss/bestsellers/kitchen/", "Kitchen"),
        ("https://www.amazon.in/rss/bestsellers/sports/", "Sports"),
        ("https://www.amazon.in/rss/bestsellers/computers/", "Computers"),
        ("https://www.amazon.in/rss/movers-and-shakers/electronics/", "Electronics Trending"),
        ("https://www.amazon.in/rss/new-releases/electronics/", "New Electronics"),
        ("https://www.amazon.in/rss/new-releases/apparel/", "New Fashion"),
    ]

    deals = []
    for rss_url, category in rss_urls:
        try:
            r = requests.get(rss_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue

            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el  = item.find("link")
                title    = title_el.text.strip() if title_el is not None else ""
                link     = link_el.text.strip()  if link_el  is not None else ""

                if not link or not title:
                    continue

                asin_match = re.search(r"/dp/([A-Z0-9]{10})", link)
                if not asin_match:
                    continue
                asin = asin_match.group(1)

                deals.append({
                    "id":           f"rss_{asin}",
                    "title":        title,
                    "desidime_url": None,
                    "visit_url":    None,
                    "hotness":      100,  # RSS deals hot maano
                    "source":       f"RSS-{category}",
                    "asin":         asin,
                })

        except Exception as e:
            continue

    # Duplicates remove
    seen = set()
    unique = []
    for d in deals:
        if d["asin"] not in seen:
            seen.add(d["asin"])
            unique.append(d)

    print(f"[SOURCE] Amazon RSS: {len(unique)} deals")
    return unique

# ─────────────────────────────────────────────
# SOURCE 3: Amazon Today's Deals page scrape
# ─────────────────────────────────────────────
def get_amazon_deals_page() -> list:
    deals = []
    try:
        r = requests.get("https://www.amazon.in/deals", headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return deals

        soup = BeautifulSoup(r.text, "html.parser")

        # ASIN dhundho page mein
        asins = re.findall(r'"asin"\s*:\s*"([A-Z0-9]{10})"', r.text)
        titles_raw = re.findall(r'"title"\s*:\s*"([^"]{10,100})"', r.text)

        seen = set()
        for i, asin in enumerate(asins):
            if asin in seen:
                continue
            seen.add(asin)
            title = titles_raw[i] if i < len(titles_raw) else f"Amazon Deal - {asin}"
            deals.append({
                "id":           f"amz_{asin}",
                "title":        title,
                "desidime_url": None,
                "visit_url":    None,
                "hotness":      150,
                "source":       "Amazon Deals",
                "asin":         asin,
            })

    except Exception as e:
        print(f"[WARN] Amazon deals page error: {e}")

    print(f"[SOURCE] Amazon Deals Page: {len(deals)} deals")
    return deals

# ─────────────────────────────────────────────
# SOURCE 4: Amazon Goldbox (Lightning Deals)
# ─────────────────────────────────────────────
def get_goldbox_deals() -> list:
    deals = []
    try:
        r = requests.get("https://www.amazon.in/gp/goldbox", headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return deals

        asins  = re.findall(r'"asin"\s*:\s*"([A-Z0-9]{10})"', r.text)
        titles = re.findall(r'"title"\s*:\s*"([^"]{10,100})"', r.text)

        seen = set()
        for i, asin in enumerate(asins):
            if asin in seen:
                continue
            seen.add(asin)
            title = titles[i] if i < len(titles) else f"Lightning Deal - {asin}"
            deals.append({
                "id":           f"gb_{asin}",
                "title":        title,
                "desidime_url": None,
                "visit_url":    None,
                "hotness":      200,  # Lightning deals = most hot
                "source":       "Amazon Lightning",
                "asin":         asin,
            })

    except Exception as e:
        print(f"[WARN] Goldbox error: {e}")

    print(f"[SOURCE] Amazon Lightning Deals: {len(deals)} deals")
    return deals

# ─────────────────────────────────────────────
# ASIN resolve karo DesiDime deals ke liye
# ─────────────────────────────────────────────
def resolve_asin(deal: dict) -> str | None:
    # Already ASIN hai
    if deal.get("asin"):
        return deal["asin"]

    # Method 1: visit_url redirect
    visit_url = deal.get("visit_url")
    if visit_url:
        try:
            r = requests.get(visit_url, headers=HEADERS,
                           allow_redirects=True, timeout=15)
            final = r.url
            if "amazon." in final:
                m = re.search(r"/dp/([A-Z0-9]{10})", final)
                if m:
                    print(f"[INFO] ASIN via redirect: {m.group(1)}")
                    return m.group(1)
        except Exception as e:
            print(f"[WARN] Redirect: {e}")

    # Method 2: DesiDime deal page
    desidime_url = deal.get("desidime_url")
    if desidime_url:
        try:
            r = requests.get(desidime_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            for pattern in [
                r'"asin"\s*:\s*"([A-Z0-9]{10})"',
                r'asin=([A-Z0-9]{10})',
                r'/dp/([A-Z0-9]{10})',
            ]:
                m = re.search(pattern, r.text)
                if m:
                    print(f"[INFO] ASIN via page: {m.group(1)}")
                    return m.group(1)
        except Exception as e:
            print(f"[WARN] Deal page: {e}")

    return None

# ─────────────────────────────────────────────
# Affiliate URL banao
# ─────────────────────────────────────────────
def make_affiliate_url(asin: str) -> str:
    return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"

# ─────────────────────────────────────────────
# WhatsApp pe bhejo
# ─────────────────────────────────────────────
def send_whatsapp(text: str) -> bool:
    if not GREEN_API_TOKEN:
        print("[WARN] GREEN_API_TOKEN missing")
        return False
    url     = f"{GREEN_API_BASE_URL}/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    try:
        r = requests.post(url,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"chatId": WHATSAPP_CHANNEL_JID, "message": text}),
            timeout=15)
        r.raise_for_status()
        print(f"[OK] WhatsApp ✅")
        return True
    except Exception as e:
        print(f"[ERROR] WhatsApp: {e}")
        return False

# ─────────────────────────────────────────────
# Facebook pe bhejo
# ─────────────────────────────────────────────
def send_facebook(text: str, link: str) -> bool:
    if not FB_PAGE_TOKEN:
        print("[WARN] FB_PAGE_TOKEN missing")
        return False
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    try:
        r = requests.post(url, data={
            "message": text, "link": link,
            "access_token": FB_PAGE_TOKEN
        }, timeout=15)
        print(f"[DEBUG] FB {r.status_code} | {r.text[:100]}")
        r.raise_for_status()
        print(f"[OK] Facebook ✅")
        return True
    except Exception as e:
        print(f"[ERROR] Facebook: {e}")
        return False

# ─────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────
def build_whatsapp_msg(deal: dict, url: str) -> str:
    hotness = f"{deal['hotness']}°" if deal['hotness'] > 0 else "🆕 New"
    source  = deal.get("source", "Amazon")
    return (
        f"🔥 *{hotness} Amazon Deal!*\n\n"
        f"📦 *{deal['title']}*\n\n"
        f"👉 *Buy Now:* {url}\n\n"
        f"🛒 _Daily deals — Share karo!_ 🔥"
    )

def build_facebook_msg(deal: dict) -> str:
    hotness = f"{deal['hotness']}°" if deal['hotness'] > 0 else "New"
    return (
        f"🔥 {hotness} Amazon Deal!\n\n"
        f"📦 {deal['title']}\n\n"
        f"👉 Buy Now link neeche hai!\n\n"
        f"👍 Page follow karo — daily deals milenge!\n\n"
        f"#AmazonDeals #LootBazaar #OnlineShopping #AmazonIndia #Loot"
    )

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    posted_deals = load_posted_deals()

    # Sab sources se deals lo
    all_deals = []
    all_deals += get_desidime_deals()   # Source 1: DesiDime
    all_deals += get_rss_deals()        # Source 2: Amazon RSS
    all_deals += get_amazon_deals_page() # Source 3: Amazon Deals page
    all_deals += get_goldbox_deals()    # Source 4: Lightning Deals

    # Hotness ke hisaab se sort karo
    all_deals.sort(key=lambda x: x["hotness"], reverse=True)

    print(f"\n[INFO] Total deals across all sources: {len(all_deals)}")

    new_count = 0
    for deal in all_deals:
        if new_count >= MAX_DEALS_PER_RUN:
            break

        deal_id = deal["id"]
        if deal_id in posted_deals:
            continue

        if deal["hotness"] < MIN_HOTNESS and deal["hotness"] != 0:
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Source={deal['source']}  Hotness={deal['hotness']}")

        # ASIN nikalo
        asin = resolve_asin(deal)
        if not asin:
            print(f"[SKIP] ASIN nahi mila")
            posted_deals.append(deal_id)
            save_posted_deals(posted_deals)
            continue

        affiliate_url = make_affiliate_url(asin)
        print(f"[AFFILIATE] {affiliate_url}")

        # Post karo
        send_whatsapp(build_whatsapp_msg(deal, affiliate_url))
        time.sleep(2)
        send_facebook(build_facebook_msg(deal), affiliate_url)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)
        new_count += 1
        time.sleep(5)

    print(f"\n[DONE] {new_count} deals post ki. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
