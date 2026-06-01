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
DESIDIME_URL          = "https://www.desidime.com/new"

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
# Step-1: DesiDime se sirf Amazon deals lo
# ─────────────────────────────────────────────
def get_amazon_deals() -> list:
    try:
        resp = requests.get(DESIDIME_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] DesiDime fetch failed: {e}")
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    deals = []

    for article in soup.find_all("article", attrs={"data-gtm-deal-id": True}):
        deal_id = article["data-gtm-deal-id"].strip()
        store   = article.get("data-gtm-store", "").strip().lower()

        # Sirf Amazon deals
        if "amazon" not in store and "other" not in store:
            continue

        # Title
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

        # Amazon check — title mein bhi
        if "amazon" not in store and "amazon" not in title.lower():
            continue

        # Hotness
        hotness = 0
        hotness_span = article.find("span", class_=re.compile(r"hotness_value_" + deal_id))
        if hotness_span:
            raw = hotness_span.get_text(strip=True).replace("°", "")
            if raw.isdigit():
                hotness = int(raw)

        # Buy Now URL
        visit_url = None
        buy_now = article.find("a", class_=re.compile(r"gtm_buy_now_homepage"), href=True)
        if buy_now:
            href = buy_now["href"]
            if href.startswith("http"):
                visit_url = href

        if title:
            deals.append({
                "id":           deal_id,
                "title":        title,
                "desidime_url": desidime_url,
                "visit_url":    visit_url,
                "hotness":      hotness,
                "store":        store,
            })

    print(f"[INFO] {len(deals)} Amazon deals found on DesiDime")
    return deals

# ─────────────────────────────────────────────
# Step-2: Amazon URL resolve karo
# ─────────────────────────────────────────────
def get_amazon_url(deal: dict) -> str | None:
    # Deal page scrape karke Amazon link dhundho
    desidime_url = deal.get("desidime_url")
    if not desidime_url:
        return None

    try:
        r = requests.get(desidime_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Amazon link dhundho
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "amazon.in" in href or "amazon.com" in href:
                # ASIN nikalo
                asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
                if asin_match:
                    clean = f"https://www.amazon.in/dp/{asin_match.group(1)}"
                    print(f"[INFO] Amazon URL: {clean}")
                    return clean
                return href

    except Exception as e:
        print(f"[WARN] Deal page error: {e}")

    return None

# ─────────────────────────────────────────────
# Step-3: Affiliate URL banao
# ─────────────────────────────────────────────
def make_affiliate_url(url: str) -> str:
    asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if asin_match:
        return f"https://www.amazon.in/dp/{asin_match.group(1)}?tag={AMAZON_AFFILIATE_TAG}"
    clean = re.sub(r"[?&]tag=[^&]*", "", url)
    sep   = "&" if "?" in clean else "?"
    return f"{clean}{sep}tag={AMAZON_AFFILIATE_TAG}"

# ─────────────────────────────────────────────
# Step-4: WhatsApp pe bhejo
# ─────────────────────────────────────────────
def send_whatsapp(text: str) -> bool:
    if not GREEN_API_TOKEN:
        print("[WARN] GREEN_API_TOKEN missing")
        return False

    url     = f"{GREEN_API_BASE_URL}/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    payload = {"chatId": WHATSAPP_CHANNEL_JID, "message": text}

    try:
        r = requests.post(url, headers={"Content-Type": "application/json"},
                         data=json.dumps(payload), timeout=15)
        r.raise_for_status()
        print(f"[OK] WhatsApp sent! ✅")
        return True
    except Exception as e:
        print(f"[ERROR] WhatsApp: {e}")
        return False

# ─────────────────────────────────────────────
# Step-5: Facebook pe bhejo
# ─────────────────────────────────────────────
def send_facebook(text: str, link: str) -> bool:
    if not FB_PAGE_TOKEN:
        print("[WARN] FB_PAGE_TOKEN missing")
        return False

    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    try:
        r = requests.post(url, data={
            "message":      text,
            "link":         link,
            "access_token": FB_PAGE_TOKEN
        }, timeout=15)
        print(f"[DEBUG] FB {r.status_code} | {r.text[:100]}")
        r.raise_for_status()
        print(f"[OK] Facebook posted! ✅")
        return True
    except Exception as e:
        print(f"[ERROR] Facebook: {e}")
        return False

# ─────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────
def build_whatsapp_msg(deal: dict, url: str) -> str:
    hotness = f"{deal['hotness']}°" if deal['hotness'] > 0 else "🆕 New"
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
        f"👍 Page follow karo aur notifications on karo!\n\n"
        f"#AmazonDeals #LootBazaar #OnlineShopping #AmazonIndia #Loot"
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

        if deal["hotness"] < MIN_HOTNESS and deal["hotness"] != 0:
            print(f"[SKIP] Low hotness ({deal['hotness']}): {deal['title'][:50]}")
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Hotness={deal['hotness']}  Store={deal['store']}")

        # Amazon URL nikalo
        amazon_url = get_amazon_url(deal)

        if not amazon_url:
            print(f"[SKIP] Amazon URL nahi mila")
            posted_deals.append(deal_id)
            save_posted_deals(posted_deals)
            continue

        affiliate_url = make_affiliate_url(amazon_url)
        print(f"[AFFILIATE] {affiliate_url}")

        # WhatsApp
        send_whatsapp(build_whatsapp_msg(deal, affiliate_url))
        time.sleep(2)

        # Facebook
        send_facebook(build_facebook_msg(deal), affiliate_url)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)
        new_count += 1
        time.sleep(5)

    print(f"\n[DONE] {new_count} deals post ki. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
