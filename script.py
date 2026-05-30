import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
DESIDIME_NEW_DEALS_URL = "https://www.desidime.com/new"
AMAZON_AFFILIATE_TAG   = "sk200709-21"

GREEN_API_INSTANCE_ID  = os.environ.get("GREEN_API_INSTANCE_ID")
GREEN_API_TOKEN        = os.environ.get("GREEN_API_TOKEN")
WHATSAPP_CHANNEL_JID   = "0029VbCy92nBadmau8nw0v3j@newsletter"

POSTED_DEALS_FILE      = "posted_deals.json"

# Only post deals with hotness >= this value  (set 0 to post all)
MIN_HOTNESS            = 50

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ─────────────────────────────────────────────
# Helpers: posted-deals tracker
# ─────────────────────────────────────────────
def load_posted_deals() -> list:
    if os.path.exists(POSTED_DEALS_FILE):
        with open(POSTED_DEALS_FILE, "r") as f:
            return json.load(f)
    return []

def save_posted_deals(deals: list):
    with open(POSTED_DEALS_FILE, "w") as f:
        json.dump(deals, f, indent=2)

# ─────────────────────────────────────────────
# Step-1: Scrape /new page → list of deal dicts
# ─────────────────────────────────────────────
def get_deals_from_new_page() -> list:
    """
    Returns list of dicts:
      { title, desidime_url, visit_url, hotness, store, image_url }

    HTML structure observed:
      <article data-gtm-deal-id="XXXXXXX" ...>
        <div class="deal_views_hotness_btn_XXXXXXX">
          <span class="hotness_value_XXXXXXX">957°</span>
        </div>
        <div class="custom-card-title">
          <a href="/deals/SLUG">Title here</a>
        </div>
        ...
        <a class="...gtm_buy_now_homepage..." href="https://visit.desidime.com/visit/.../XXXXXXX">
          Buy Now
        </a>
      </article>
    """
    try:
        resp = requests.get(DESIDIME_NEW_DEALS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Could not fetch /new page: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    deals = []

    for article in soup.find_all("article", attrs={"data-gtm-deal-id": True}):
        deal_id = article["data-gtm-deal-id"].strip()
        store   = article.get("data-gtm-store", "").strip()

        # --- Title & DesiDime URL ---
        title_div = article.find("div", class_="custom-card-title")
        if not title_div:
            continue
        link_tag = title_div.find("a", href=True)
        if not link_tag:
            continue
        title        = link_tag.get_text(strip=True)
        deal_rel_url = link_tag["href"]
        if deal_rel_url.startswith("/"):
            desidime_url = "https://www.desidime.com" + deal_rel_url
        else:
            desidime_url = deal_rel_url

        # --- Hotness score ---
        hotness = 0
        hotness_span = article.find("span", class_=re.compile(r"hotness_value_" + deal_id))
        if hotness_span:
            raw = hotness_span.get_text(strip=True).replace("°", "")
            if raw.isdigit():
                hotness = int(raw)

        # --- Buy Now / visit.desidime.com redirect URL ---
        visit_url = None
        buy_now = article.find(
            "a",
            class_=re.compile(r"gtm_buy_now_homepage"),
            href=True
        )
        if buy_now:
            href = buy_now["href"]
            if "visit.desidime.com" in href or href.startswith("http"):
                visit_url = href

        # --- Thumbnail image ---
        img_tag = article.find("img", loading="lazy")
        image_url = img_tag["src"] if img_tag and img_tag.get("src") else None

        if title and desidime_url:
            deals.append({
                "id":            deal_id,
                "title":         title,
                "desidime_url":  desidime_url,
                "visit_url":     visit_url,
                "hotness":       hotness,
                "store":         store,
                "image_url":     image_url,
            })

    print(f"[INFO] Scraped {len(deals)} deal cards from /new")
    return deals

# ─────────────────────────────────────────────
# Step-2: Resolve visit.desidime.com → product URL
# ─────────────────────────────────────────────
def resolve_product_url(deal: dict) -> str | None:
    """
    Try to get the real product URL by:
    1. Following visit.desidime.com redirect (fastest)
    2. Falling back to scraping the deal page for direct e-com links
    """
    visit_url = deal.get("visit_url")

    # --- Method 1: follow redirect ---
    if visit_url and "visit.desidime.com" in visit_url:
        try:
            r = requests.get(
                visit_url, headers=HEADERS,
                allow_redirects=True, timeout=15
            )
            final_url = r.url
            if final_url and "desidime.com" not in final_url and final_url != visit_url:
                print(f"[INFO] Redirect resolved → {final_url[:80]}")
                return final_url
        except requests.RequestException as e:
            print(f"[WARN] Redirect follow failed: {e}")

    # --- Method 2: scrape deal page ---
    desidime_url = deal.get("desidime_url")
    if not desidime_url:
        return None

    try:
        r = requests.get(desidime_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[WARN] Could not fetch deal page {desidime_url}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    ECOM_DOMAINS = [
        "amazon.in", "amazon.com",
        "flipkart.com", "myntra.com", "ajio.com",
        "tatacliq.com", "snapdeal.com", "nykaa.com",
        "meesho.com", "swiggy.com", "zomato.com",
        "bigbasket.com", "blinkit.com", "zepto.com",
        "jiomart.com", "shopclues.com",
    ]

    # First try: Buy Now button on deal page
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if "Buy Now" in text and "visit.desidime.com" in href:
            try:
                r2 = requests.get(href, headers=HEADERS, allow_redirects=True, timeout=15)
                if "desidime.com" not in r2.url:
                    return r2.url
            except Exception:
                pass

    # Second try: any e-com link on the page
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(d in href for d in ECOM_DOMAINS):
            return href

    return None

# ─────────────────────────────────────────────
# Step-3: Affiliate link
# ─────────────────────────────────────────────
def add_affiliate_tag(url: str) -> str:
    """Append Amazon affiliate tag if URL is Amazon; otherwise return as-is."""
    if "amazon." in url:
        sep = "&" if "?" in url else "?"
        # Remove existing tag= param if present
        url = re.sub(r"[?&]tag=[^&]*", "", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}tag={AMAZON_AFFILIATE_TAG}"
    return url  # non-Amazon: no tag needed

# ─────────────────────────────────────────────
# Step-4: Build WhatsApp message
# ─────────────────────────────────────────────
def build_message(deal: dict, product_url: str) -> str:
    title   = deal["title"]
    store   = deal["store"] or "Online"
    hotness = deal["hotness"]
    dime_url = deal["desidime_url"]

    hotness_str = f"{hotness}°" if hotness > 0 else "New"

    # Use DesiDime page as fallback if product URL not resolved
    buy_link = add_affiliate_tag(product_url) if product_url else dime_url

    msg = (
        f"🔥 *{hotness_str} Hot Deal!*\n\n"
        f"📦 *{title}*\n"
        f"🏪 Store: {store}\n\n"
        f"👉 *Buy Now:* {buy_link}\n\n"
        f"🔗 _Details: {dime_url}_"
    )
    return msg

# ─────────────────────────────────────────────
# Step-5: Send WhatsApp via Green-API
# ─────────────────────────────────────────────
def send_whatsapp_message(chat_id: str, text: str) -> bool:
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("[WARN] Green-API credentials missing — printing message only:\n")
        print(text)
        print("-" * 60)
        return False

    url = (
        f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}"
        f"/sendMessage/{GREEN_API_TOKEN}"
    )
    payload = {"chatId": chat_id, "message": text}
    try:
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=15
        )
        r.raise_for_status()
        print(f"[OK] WhatsApp sent → {r.json()}")
        return True
    except requests.RequestException as e:
        print(f"[ERROR] WhatsApp send failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"       Response: {e.response.text}")
        return False

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    posted_deals = load_posted_deals()
    deals        = get_deals_from_new_page()

    new_count = 0
    for deal in deals:
        deal_id = deal["id"]

        # Skip if already posted
        if deal_id in posted_deals:
            continue

        # Skip low-hotness deals
        if deal["hotness"] < MIN_HOTNESS and deal["hotness"] != 0:
            # 0 means "New" — always include fresh deals
            print(f"[SKIP] Low hotness ({deal['hotness']}°): {deal['title'][:60]}")
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Hotness={deal['hotness']}°  Store={deal['store']}")

        product_url = resolve_product_url(deal)
        if not product_url:
            print(f"[WARN] No product URL found — using DesiDime link")

        message = build_message(deal, product_url)
        send_whatsapp_message(WHATSAPP_CHANNEL_JID, message)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)

        new_count += 1
        time.sleep(5)  # Rate limit: 5s between messages

    print(f"\n[DONE] Posted {new_count} new deals. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
