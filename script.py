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

GREEN_API_INSTANCE_ID  = os.environ.get("GREEN_API_INSTANCE_ID", "7107592101")
GREEN_API_TOKEN        = os.environ.get("GREEN_API_TOKEN", "")
GREEN_API_BASE_URL     = "https://7107.api.greenapi.com"

WHATSAPP_CHANNEL_JID   = "120363424914979115@g.us"

POSTED_DEALS_FILE      = "posted_deals.json"
MIN_HOTNESS            = 50

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
# Step-2: Amazon product URL resolve karo
# ─────────────────────────────────────────────
def resolve_amazon_url(deal: dict) -> str | None:
    visit_url = deal.get("visit_url")

    # Method 1: visit.desidime.com redirect follow karo
    if visit_url and "visit.desidime.com" in visit_url:
        try:
            r = requests.get(
                visit_url, headers=HEADERS,
                allow_redirects=True, timeout=15
            )
            final_url = r.url
            if final_url and "amazon." in final_url:
                print(f"[INFO] Amazon URL mila -> {final_url[:80]}")
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
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "amazon." in href:
            print(f"[INFO] Amazon URL scraped -> {href[:80]}")
            return href

    return None

# ─────────────────────────────────────────────
# Step-3: Amazon affiliate tag lagao
# ─────────────────────────────────────────────
def make_amazon_affiliate(url: str) -> str:
    clean = re.sub(r"[?&]tag=[^&]*", "", url)
    sep   = "&" if "?" in clean else "?"
    final = f"{clean}{sep}tag={AMAZON_AFFILIATE_TAG}"
    print(f"[AFFILIATE] Tag laga -> {final[:80]}")
    return final

# ─────────────────────────────────────────────
# Step-4: WhatsApp message banao
# ─────────────────────────────────────────────
def build_message(deal: dict, buy_link: str) -> str:
    title       = deal["title"]
    hotness     = deal["hotness"]
    dime_url    = deal["desidime_url"]
    hotness_str = f"{hotness}°" if hotness > 0 else "🆕 New"

    return (
        f"🔥 *{hotness_str} Amazon Deal!*\n\n"
        f"📦 *{title}*\n\n"
        f"👉 *Buy Now:* {buy_link}\n\n"
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
        deal_id     = deal["id"]
        store_lower = deal["store"].lower()

        # Already posted skip
        if deal_id in posted_deals:
            continue

        # Sirf Amazon deals
        if "amazon" not in store_lower:
            print(f"[SKIP] Non-Amazon ({deal['store']}): {deal['title'][:50]}")
            continue

        # Low hotness skip
        if deal["hotness"] < MIN_HOTNESS and deal["hotness"] != 0:
            print(f"[SKIP] Low hotness ({deal['hotness']}): {deal['title'][:50]}")
            continue

        print(f"\n[DEAL] {deal['title'][:70]}")
        print(f"       Hotness={deal['hotness']}  Store={deal['store']}")

        # Amazon URL nikalo
        amazon_url = resolve_amazon_url(deal)

        if not amazon_url:
            print(f"[SKIP] Amazon URL nahi mila — skip kar rahe hain")
            # Track karo taaki baar baar try na ho
            posted_deals.append(deal_id)
            save_posted_deals(posted_deals)
            continue

        # Affiliate tag lagao
        affiliate_url = make_amazon_affiliate(amazon_url)

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
