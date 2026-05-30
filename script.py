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

WHATSAPP_CHANNEL_JID    = "120363424914979115@g.us"  # Tumhara group JID

POSTED_DEALS_FILE       = "posted_deals.json"
MIN_HOTNESS             = 50

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

        # Buy Now URL
        visit_url = None
        buy_now = article.find("a", class_=re.compile(r"gtm_buy_now_homepage"), href=True)
        if buy_now:
            href = buy_now["href"]
            if href.startswith("http"):
                visit_url = href

        if title and desidime_url:
            deals.append({
                "id":           deal_id,
                "title":        title,
                "desidime_url": desidime_url,
                "visit_url":    visit_url,
                "hotness":      hotness,
                "store":        store,
            })

    print(f"[INFO] Scraped {len(deals)} deal cards from /new")
    return deals

# ─────────────────────────────────────────────
# Step-2: Product URL resolve karo
# ─────────────────────────────────────────────
def resolve_product_url(deal: dict) -> str | None:
    visit_url = deal.get("visit_url")

    # Method 1: visit.desidime.com redirect follow karo
    if visit_url and "visit.desidime.com" in visit_url:
        try:
            r = requests.get(visit_url, headers=HEADERS, allow_redirects=True, timeout=15)
            final_url = r.url
            if final_url and "desidime.com" not in final_url and final_url != visit_url:
                print(f"[INFO] Redirect -> {final_url[:80]}")
                return final_url
        except requests.RequestException as e:
            print(f"[WARN] Redirect failed: {e}")

    # Method 2: deal page scrape karo
    desidime_url = deal.get("desidime_url")
    if not desidime_url:
        return None

    try:
        r = requests.get(desidime_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[WARN] Deal page fetch failed: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    ECOM_DOMAINS = [
        "amazon.in", "amazon.com", "flipkart.com", "myntra.com",
        "ajio.com", "tatacliq.com", "nykaa.com", "meesho.com",
        "swiggy.com", "zomato.com", "bigbasket.com", "zepto.com",
        "jiomart.com",
    ]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(d in href for d in ECOM_DOMAINS):
            return href

    return None

# ─────────────────────────────────────────────
# Step-3: Affiliaters API se affiliate link banao
# ─────────────────────────────────────────────
def make_affiliate_link(product_url: str, deal_title: str) -> str:
    """
    Amazon  → seedha Amazon tag lagao (fast)
    Baaki   → Affiliaters API se convert karo (Earnkaro commission)
    """

    # Amazon ke liye seedha tag lagao
    if "amazon." in product_url:
        clean = re.sub(r"[?&]tag=[^&]*", "", product_url)
        sep   = "&" if "?" in clean else "?"
        final = f"{clean}{sep}tag={AMAZON_AFFILIATE_TAG}"
        print(f"[AFFILIATE] Amazon tag laga ✅")
        return final

    # Baaki stores ke liye Affiliaters API
    if not AFFILIATERS_API_KEY:
        print("[WARN] AFFILIATERS_API_KEY missing — original URL use ho raha hai")
        return product_url

    try:
        # Deal title + URL bhejo — better conversion
        payload = {
            "deal": f"{deal_title}\n{product_url}",
            "convert_option": "convert_only"
        }
        r = requests.post(
            AFFILIATERS_API_URL,
            headers={
                "Authorization": f"Bearer {AFFILIATERS_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=15
        )
        data = r.json()

        if data.get("success") == 1:
            converted = data.get("data", "")
            # Converted text mein se link nikalo
            urls = re.findall(r'https?://\S+', converted)
            if urls:
                # Affiliate link wala (fktr.in, myntr.it etc)
                for u in urls:
                    if any(x in u for x in ["fktr.in", "myntr.it", "ekaro", "amzn"]):
                        print(f"[AFFILIATE] Earnkaro link bana ✅ -> {u[:60]}")
                        return u
                # Koi bhi pehla link le lo
                print(f"[AFFILIATE] Link converted ✅ -> {urls[0][:60]}")
                return urls[0]
        else:
            print(f"[WARN] Affiliaters API error: {data.get('message', 'unknown')}")

    except Exception as e:
        print(f"[WARN] Affiliaters API call failed: {e}")

    # Fallback — original URL
    return product_url

# ─────────────────────────────────────────────
# Step-4: WhatsApp message banao
# ─────────────────────────────────────────────
def build_message(deal: dict, product_url: str) -> str:
    title    = deal["title"]
    store    = deal["store"] or "Online"
    hotness  = deal["hotness"]
    dime_url = deal["desidime_url"]

    hotness_str  = f"{hotness}°" if hotness > 0 else "New"
    affiliate_url = make_affiliate_link(product_url, title) if product_url else dime_url

    return (
        f"🔥 *{hotness_str} Hot Deal!*\n\n"
        f"📦 *{title}*\n"
        f"🏪 Store: {store}\n\n"
        f"👉 *Buy Now:* {affiliate_url}\n\n"
        f"🔗 _Details: {dime_url}_"
    )

# ─────────────────────────────────────────────
# Step-5: WhatsApp pe bhejo
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

        if deal_id in posted_deals:
            continue

        if deal["hotness"] < MIN_HOTNESS and deal["hotness"] != 0:
            print(f"[SKIP] Low hotness ({deal['hotness']}): {deal['title'][:60]}")
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Hotness={deal['hotness']}  Store={deal['store']}")

        product_url = resolve_product_url(deal)
        if not product_url:
            print("[WARN] Product URL nahi mila — DesiDime link use hoga")

        message = build_message(deal, product_url)
        send_whatsapp_message(WHATSAPP_CHANNEL_JID, message)

        posted_deals.append(deal_id)
        save_posted_deals(posted_deals)

        new_count += 1
        time.sleep(5)

    print(f"\n[DONE] {new_count} nayi deals post ki. Total tracked: {len(posted_deals)}")

if __name__ == "__main__":
    main()
