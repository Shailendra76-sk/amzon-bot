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

GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "7107592101")
GREEN_API_TOKEN       = os.environ.get("GREEN_API_TOKEN", "")
GREEN_API_BASE_URL    = "https://7107.api.greenapi.com"

WHATSAPP_CHANNEL_JID  = "120363424914979115@g.us"

POSTED_DEALS_FILE     = "posted_deals.json"
MIN_DISCOUNT          = 50   # Minimum discount % (50% se kam skip)
MAX_DEALS_PER_RUN     = 5    # Ek baar mein max 5 deals post karo

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
# Step-1: Amazon.in/deals se deals scrape karo
# ─────────────────────────────────────────────
def get_amazon_deals() -> list:
    urls_to_try = [
        "https://www.amazon.in/deals",
        "https://www.amazon.in/gp/goldbox",
    ]

    deals = []

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[WARN] Could not fetch {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Amazon deals page structure
        # Deal cards mein data-csa-c-item-id ya data-deal-id hota hai
        deal_cards = soup.find_all("div", attrs={"data-csa-c-item-id": True})

        if not deal_cards:
            # Try alternative selectors
            deal_cards = soup.find_all("div", attrs={"data-deal-id": True})

        if not deal_cards:
            # Try deal tiles
            deal_cards = soup.select("div[class*='DealCard']")

        print(f"[INFO] Found {len(deal_cards)} deal cards on {url}")

        for card in deal_cards:
            try:
                # Deal ID
                deal_id = (
                    card.get("data-csa-c-item-id") or
                    card.get("data-deal-id") or
                    ""
                ).strip()

                # Title
                title_tag = (
                    card.find("span", attrs={"data-csa-c-content-id": True}) or
                    card.find("span", class_=re.compile(r"title|Title|name")) or
                    card.find("div", class_=re.compile(r"title|Title"))
                )
                title = title_tag.get_text(strip=True) if title_tag else ""

                # Price
                price_tag = card.find("span", class_=re.compile(r"price|Price"))
                price = price_tag.get_text(strip=True) if price_tag else ""

                # Discount %
                discount_tag = card.find("span", class_=re.compile(r"discount|Discount|percent|badge"))
                discount_text = discount_tag.get_text(strip=True) if discount_tag else ""
                discount_num = 0
                disc_match = re.search(r"(\d+)%", discount_text)
                if disc_match:
                    discount_num = int(disc_match.group(1))

                # Product link
                link_tag = card.find("a", href=True)
                product_url = ""
                if link_tag:
                    href = link_tag["href"]
                    if href.startswith("/"):
                        product_url = "https://www.amazon.in" + href
                    elif href.startswith("http"):
                        product_url = href

                # ASIN nikalo URL se
                asin_match = re.search(r"/dp/([A-Z0-9]{10})", product_url)
                asin = asin_match.group(1) if asin_match else deal_id

                if title and product_url and asin:
                    deals.append({
                        "id":       asin,
                        "title":    title,
                        "price":    price,
                        "discount": discount_num,
                        "url":      product_url,
                    })

            except Exception as e:
                continue

        if deals:
            break  # Pehli working URL se deals mil gayi

    # Fallback — Amazon Today's Deals RSS
    if not deals:
        print("[INFO] Trying Amazon RSS feed...")
        deals = get_amazon_rss_deals()

    print(f"[INFO] Total {len(deals)} Amazon deals scraped")
    return deals

# ─────────────────────────────────────────────
# Fallback: Amazon RSS feed
# ─────────────────────────────────────────────
def get_amazon_rss_deals() -> list:
    import xml.etree.ElementTree as ET

    rss_urls = [
        "https://www.amazon.in/rss/bestsellers/electronics/",
        "https://www.amazon.in/rss/bestsellers/apparel/",
        "https://www.amazon.in/rss/bestsellers/kitchen/",
        "https://www.amazon.in/rss/bestsellers/sports/",
        "https://www.amazon.in/rss/movers-and-shakers/electronics/",
    ]

    deals = []
    for rss_url in rss_urls:
        try:
            r = requests.get(rss_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue

            root = ET.fromstring(r.content)
            ns   = {"media": "http://search.yahoo.com/mrss/"}

            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el  = item.find("link")
                title    = title_el.text.strip() if title_el is not None else ""
                link     = link_el.text.strip()  if link_el  is not None else ""

                if not link:
                    continue

                # Clean URL
                clean_url = link.split("?")[0] if "?" in link else link

                # ASIN
                asin_match = re.search(r"/dp/([A-Z0-9]{10})", clean_url)
                asin = asin_match.group(1) if asin_match else ""

                if title and clean_url and asin:
                    deals.append({
                        "id":       asin,
                        "title":    title,
                        "price":    "",
                        "discount": 0,
                        "url":      clean_url,
                    })

            if deals:
                print(f"[INFO] RSS deals from {rss_url}: {len(deals)}")
                break

        except Exception as e:
            print(f"[WARN] RSS error: {e}")
            continue

    return deals

# ─────────────────────────────────────────────
# Step-2: Affiliate tag lagao
# ─────────────────────────────────────────────
def make_affiliate_url(url: str) -> str:
    clean = re.sub(r"[?&]tag=[^&]*", "", url)
    # Sirf ASIN wala clean URL rakho
    asin_match = re.search(r"(/dp/[A-Z0-9]{10})", clean)
    if asin_match:
        clean = "https://www.amazon.in" + asin_match.group(1)
    sep   = "&" if "?" in clean else "?"
    return f"{clean}{sep}tag={AMAZON_AFFILIATE_TAG}"

# ─────────────────────────────────────────────
# Step-3: WhatsApp message banao
# ─────────────────────────────────────────────
def build_message(deal: dict, affiliate_url: str) -> str:
    title    = deal["title"]
    price    = deal["price"]
    discount = deal["discount"]

    disc_str  = f"🏷️ *{discount}% OFF*\n" if discount >= MIN_DISCOUNT else ""
    price_str = f"💰 Price: *{price}*\n"   if price else ""

    return (
        f"🔥 *Amazon Hot Deal!*\n\n"
        f"📦 *{title}*\n\n"
        f"{disc_str}"
        f"{price_str}\n"
        f"👉 *Buy Now:* {affiliate_url}"
    )

# ─────────────────────────────────────────────
# Step-4: WhatsApp pe bhejo
# ─────────────────────────────────────────────
def send_whatsapp_message(chat_id: str, text: str) -> bool:
    if not GREEN_API_TOKEN:
        print("[WARN] GREEN_API_TOKEN missing — message:\n")
        print(text)
        print("-" * 60)
        return False

    url     = f"{GREEN_API_BASE_URL}/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    payload = {"chatId": chat_id, "message": text}

    try:
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=15
        )
        print(f"[DEBUG] HTTP {r.status_code} | {r.text[:150]}")
        r.raise_for_status()
        print(f"[OK] WhatsApp message sent! ✅")
        return True
    except requests.RequestException as e:
        print(f"[ERROR] Send failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"       {e.response.text}")
        return False

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

        # Already posted skip
        if deal_id in posted_deals:
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Discount={deal['discount']}%  Price={deal['price']}")

        # Affiliate URL banao
        affiliate_url = make_affiliate_url(deal["url"])
        print(f"[AFFILIATE] {affiliate_url[:80]}")

        # Message banao aur bhejo
        message = build_message(deal, affiliate_url)
        send_whatsapp_message(WHATSAPP_CHANNEL_JID, message)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)

        new_count += 1
        time.sleep(5)

    print(f"\n[DONE] {new_count} Amazon deals post ki. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
