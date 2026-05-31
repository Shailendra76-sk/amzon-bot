import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
DESIDIME_NEW_DEALS_URL  = "https://www.desidime.com/new"
AMAZON_AFFILIATE_TAG    = "sk200709-21"
AFFILIATERS_API_KEY     = os.environ.get("AFFILIATERS_API_KEY", "")
AFFILIATERS_API_URL     = "https://ekaro-api.affiliaters.in/api/converter/public"

GREEN_API_INSTANCE_ID   = os.environ.get("GREEN_API_INSTANCE_ID", "7107592101")
GREEN_API_TOKEN         = os.environ.get("GREEN_API_TOKEN", "")
GREEN_API_BASE_URL      = "https://7107.api.greenapi.com"

WHATSAPP_CHANNEL_JID    = "120363424914979115@g.us"

POSTED_DEALS_FILE       = "posted_deals.json"
MIN_HOTNESS             = 50

# Sirf in stores ki deals post karo (affiliate milta hai)
AFFILIATE_STORES = [
    "amazon", "flipkart", "myntra", "ajio",
    "meesho", "nykaa", "tatacliq", "snapdeal"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
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
# Step-1: DesiDime /new se deals scrape karo
# ─────────────────────────────────────────────
def get_deals_from_new_page() -> list:
    try:
        resp = requests.get(DESIDIME_NEW_DEALS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Could not fetch /new page: {e}")
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    deals = []

    for article in soup.find_all("article", attrs={"data-gtm-deal-id": True}):
        deal_id = article["data-gtm-deal-id"].strip()
        store   = article.get("data-gtm-store", "").strip()

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

        # Hotness score
        hotness = 0
        hotness_span = article.find("span", class_=re.compile(r"hotness_value_" + deal_id))
        if hotness_span:
            raw = hotness_span.get_text(strip=True).replace("°", "")
            if raw.isdigit():
                hotness = int(raw)

        if title and desidime_url:
            deals.append({
                "id":           deal_id,
                "title":        title,
                "desidime_url": desidime_url,
                "hotness":      hotness,
                "store":        store,
            })

    print(f"[INFO] Scraped {len(deals)} deal cards from /new")
    return deals

# ─────────────────────────────────────────────
# Step-2: Affiliaters API se affiliate link banao
# DesiDime link seedha do — API khud product
# dhundh ke affiliate link bana deta hai
# ─────────────────────────────────────────────
def make_affiliate_link(deal: dict) -> str:
    title        = deal["title"]
    desidime_url = deal["desidime_url"]
    store        = deal["store"].lower()

    # Amazon ke liye Affiliaters API + Amazon tag
    # Baaki ke liye sirf Affiliaters API
    if not AFFILIATERS_API_KEY:
        print("[WARN] AFFILIATERS_API_KEY missing")
        return desidime_url

    try:
        payload = {
            "deal": f"{title}\n{desidime_url}",
            "convert_option": "convert_only"
        }
        r = requests.post(
            AFFILIATERS_API_URL,
            headers={
                "Authorization": f"Bearer {AFFILIATERS_API_KEY}",
                "Content-Type":  "application/json"
            },
            json=payload,
            timeout=20
        )
        data = r.json()

        if data.get("success") == 1:
            converted_text = data.get("data", "")
            # Converted text mein se affiliate link nikalo
            urls = re.findall(r'https?://\S+', converted_text)
            affiliate_urls = []
            for u in urls:
                # Desidime links ignore karo
                if "desidime" not in u:
                    affiliate_urls.append(u)

            if affiliate_urls:
                # Amazon link pe apna tag bhi lagao
                for u in affiliate_urls:
                    if "amazon." in u:
                        clean = re.sub(r"[?&]tag=[^&]*", "", u)
                        sep   = "&" if "?" in clean else "?"
                        final = f"{clean}{sep}tag={AMAZON_AFFILIATE_TAG}"
                        print(f"[AFFILIATE] Amazon ✅ -> {final[:70]}")
                        return final
                # Baaki (flipkart, myntra etc)
                print(f"[AFFILIATE] Earnkaro ✅ -> {affiliate_urls[0][:70]}")
                return affiliate_urls[0]
            else:
                print(f"[WARN] Koi affiliate link nahi mila — DesiDime link use hoga")
                return desidime_url
        else:
            msg = data.get("message", "unknown error")
            print(f"[WARN] Affiliaters API: {msg}")
            return desidime_url

    except Exception as e:
        print(f"[WARN] Affiliaters API failed: {e}")
        return desidime_url

# ─────────────────────────────────────────────
# Step-3: WhatsApp message banao
# ─────────────────────────────────────────────
def build_message(deal: dict, affiliate_link: str) -> str:
    title    = deal["title"]
    store    = deal["store"] or "Online"
    hotness  = deal["hotness"]
    dime_url = deal["desidime_url"]
    hotness_str = f"{hotness}°" if hotness > 0 else "New"

    return (
        f"🔥 *{hotness_str} Hot Deal!*\n\n"
        f"📦 *{title}*\n"
        f"🏪 Store: {store}\n\n"
        f"👉 *Buy Now:* {affiliate_link}\n\n"
        f"🔗 _Details: {dime_url}_"
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
    deals        = get_deals_from_new_page()

    new_count = 0
    for deal in deals:
        deal_id = deal["id"]

        # Already posted skip
        if deal_id in posted_deals:
            continue

        # Low hotness skip
        if deal["hotness"] < MIN_HOTNESS and deal["hotness"] != 0:
            print(f"[SKIP] Low hotness ({deal['hotness']}): {deal['title'][:55]}")
            continue

        # Non-affiliate store skip
        store_lower = deal["store"].lower()
        if not any(s in store_lower for s in AFFILIATE_STORES):
            print(f"[SKIP] No affiliate: {deal['store']} | {deal['title'][:45]}")
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Hotness={deal['hotness']}  Store={deal['store']}")

        affiliate_link = make_affiliate_link(deal)
        message        = build_message(deal, affiliate_link)
        send_whatsapp_message(WHATSAPP_CHANNEL_JID, message)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)

        new_count += 1
        time.sleep(5)

    print(f"\n[DONE] {new_count} nayi deals post ki. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
