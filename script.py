import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re

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
MIN_DISCOUNT          = 30
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
# Step-1: Amazon RSS se deals lo
# ─────────────────────────────────────────────
def get_amazon_deals() -> list:
    import xml.etree.ElementTree as ET

    rss_urls = [
        "https://www.amazon.in/rss/bestsellers/electronics/",
        "https://www.amazon.in/rss/bestsellers/apparel/",
        "https://www.amazon.in/rss/bestsellers/kitchen/",
        "https://www.amazon.in/rss/bestsellers/sports/",
        "https://www.amazon.in/rss/movers-and-shakers/electronics/",
        "https://www.amazon.in/rss/movers-and-shakers/apparel/",
    ]

    deals = []
    for rss_url in rss_urls:
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

                # ASIN nikalo
                asin_match = re.search(r"/dp/([A-Z0-9]{10})", link)
                if not asin_match:
                    continue
                asin = asin_match.group(1)

                # Clean URL
                clean_url = f"https://www.amazon.in/dp/{asin}"

                deals.append({
                    "id":    asin,
                    "title": title,
                    "url":   clean_url,
                })

        except Exception as e:
            print(f"[WARN] RSS error {rss_url}: {e}")
            continue

    # Duplicate remove karo
    seen = set()
    unique = []
    for d in deals:
        if d["id"] not in seen:
            seen.add(d["id"])
            unique.append(d)

    print(f"[INFO] Total {len(unique)} unique Amazon deals")
    return unique

# ─────────────────────────────────────────────
# Step-2: Affiliate URL banao
# ─────────────────────────────────────────────
def make_affiliate_url(url: str) -> str:
    asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if asin_match:
        clean = f"https://www.amazon.in/dp/{asin_match.group(1)}"
    else:
        clean = re.sub(r"[?&]tag=[^&]*", "", url)
    return f"{clean}?tag={AMAZON_AFFILIATE_TAG}"

# ─────────────────────────────────────────────
# Step-3: WhatsApp pe bhejo
# ─────────────────────────────────────────────
def send_whatsapp(text: str) -> bool:
    if not GREEN_API_TOKEN:
        print("[WARN] GREEN_API_TOKEN missing")
        return False

    url     = f"{GREEN_API_BASE_URL}/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    payload = {"chatId": WHATSAPP_CHANNEL_JID, "message": text}

    try:
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=15
        )
        r.raise_for_status()
        print(f"[OK] WhatsApp sent! ✅")
        return True
    except requests.RequestException as e:
        print(f"[ERROR] WhatsApp failed: {e}")
        return False

# ─────────────────────────────────────────────
# Step-4: Facebook Page pe bhejo
# ─────────────────────────────────────────────
def send_facebook(text: str, link: str) -> bool:
    if not FB_PAGE_TOKEN:
        print("[WARN] FB_PAGE_TOKEN missing")
        return False

    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        "message": text,
        "link":    link,
        "access_token": FB_PAGE_TOKEN
    }

    try:
        r = requests.post(url, data=payload, timeout=15)
        print(f"[DEBUG] FB HTTP {r.status_code} | {r.text[:150]}")
        r.raise_for_status()
        print(f"[OK] Facebook posted! ✅")
        return True
    except requests.RequestException as e:
        print(f"[ERROR] Facebook failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"       {e.response.text}")
        return False

# ─────────────────────────────────────────────
# Step-5: Messages banao
# ─────────────────────────────────────────────
def build_whatsapp_message(deal: dict, affiliate_url: str) -> str:
    return (
        f"🔥 *Amazon Hot Deal!*\n\n"
        f"📦 *{deal['title']}*\n\n"
        f"👉 *Buy Now:* {affiliate_url}\n\n"
        f"🛒 _Best deals daily — Share karo!_ 🔥"
    )

def build_facebook_message(deal: dict) -> str:
    return (
        f"🔥 Amazon Hot Deal!\n\n"
        f"📦 {deal['title']}\n\n"
        f"👉 Buy Now (link below)\n\n"
        f"🛒 Best deals daily — Like & Share!\n"
        f"👍 Page follow karo aur notifications on karo!\n\n"
        f"#AmazonDeals #LootBazaar #OnlineShopping #AmazonIndia"
    )

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    posted_deals = load_posted_deals()
    deals        = get_amazon_deals()

    new_count = 0
    for deal in deals:
        if new_count >= MAX_DEALS_PER_RUN:
            break

        deal_id = deal["id"]

        if deal_id in posted_deals:
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")

        affiliate_url = make_affiliate_url(deal["url"])
        print(f"[AFFILIATE] {affiliate_url}")

        # WhatsApp pe bhejo
        wa_msg = build_whatsapp_message(deal, affiliate_url)
        send_whatsapp(wa_msg)

        time.sleep(2)

        # Facebook pe bhejo
        fb_msg = build_facebook_message(deal)
        send_facebook(fb_msg, affiliate_url)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)

        new_count += 1
        time.sleep(5)

    print(f"\n[DONE] {new_count} deals post ki. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
