import requests
from bs4 import BeautifulSoup
import os
import json
import time

# --- CONFIGURATION ---
DESIDIME_NEW_DEALS_URL = "https://desidime.com"
AMAZON_DEALS_RSS = "https://rss.app" 
AMAZON_AFFILIATE_TAG = "sk200709-21"

GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN")
WHATSAPP_CHANNEL_JID = "120363294334346747@newsletter"

POSTED_DEALS_FILE = "posted_deals.json"

def load_posted_deals():
    if os.path.exists(POSTED_DEALS_FILE):
        with open(POSTED_DEALS_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_posted_deals(deals):
    with open(POSTED_DEALS_FILE, "w") as f:
        json.dump(deals, f)

# ----------------- METHOD 1: DESIDIME SCRAPER -----------------
def get_desidime_deals():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(DESIDIME_NEW_DEALS_URL, headers=headers, timeout=15)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, 'html.parser')
        deal_page_urls = []
        for card in soup.find_all('div', class_='feed-row'):
            link = card.find('a', class_='deal-title-link') or card.find('a', href=True)
            if link:
                href = link.get('href')
                title = link.get_text(strip=True)
                if href and '/deals/' in href:
                    full_url = "https://desidime.com" + href if not href.startswith('http') else href
                    if full_url not in [d['url'] for d in deal_page_urls]:
                        deal_page_urls.append({"title": title, "url": full_url, "source": "DesiDime"})
        return deal_page_urls
    except:
        return []

def extract_desidime_product_url(deal_page_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(deal_page_url, headers=headers, timeout=12)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href and any(site in href for site in ['amazon.in', 'flipkart.com', 'myntra.com', 'ajio.com']):
                if '://desidime.com' not in href and 'desidime.com' not in href:
                    return href
        return None
    except:
        return None

# ----------------- METHOD 2: AMAZON RSS FEED -----------------
def get_amazon_rss_deals():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    deals = []
    try:
        response = requests.get(AMAZON_DEALS_RSS, headers=headers, timeout=15)
        if response.status_code == 200:
            # Sahi Parser ('html.parser') use kiya hai taaki extra library ka error na aaye
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.find_all('item')
            for item in items:
                title = item.find('title').text if item.find('title') else 'Amazon Hot Deal'
                link = item.find('link').text if item.find('link') else ''
                if link:
                    # Link ko clean karna
                    clean_link = link.split('?')[0].split('&')[0]
                    deals.append({"title": title, "url": clean_link, "source": "Amazon_RSS"})
    except Exception as e:
        print(f"Amazon RSS Error: {e}")
    return deals

# ----------------- SYSTEM LOGIC -----------------
def generate_link(product_url):
    if 'amazon.in' in product_url:
        return f"{product_url}&tag={AMAZON_AFFILIATE_TAG}" if "?" in product_url else f"{product_url}?tag={AMAZON_AFFILIATE_TAG}"
    return product_url

def send_whatsapp(chat_id, msg):
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("Green-API Settings Error.")
        return
    url = f"https://green-api.com{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps({"chatId": chat_id, "message": msg}), timeout=10)
        print(f"WhatsApp Server Sent: {res.text}")
    except Exception as e:
        print(f"WhatsApp Error: {e}")

def main():
    posted_deals = load_posted_deals()
    posted_count = 0
    
    print("--- FIRST PRIORITY: Fetching from DesiDime ---")
    dd_deals = get_desidime_deals()
    print(f"Found {len(dd_deals)} raw pages on DesiDime.")
    
    for deal in dd_deals:
        if posted_count >= 2:
            break
        if deal["url"] not in posted_deals:
            print(f"Trying DesiDime link extraction for: {deal['title']}")
            prod_url = extract_desidime_product_url(deal["url"])
            if prod_url:
                final_link = generate_link(prod_url)
                message = f"🔥 *New Loot Deal (DesiDime)!*\n\n📦 {deal['title']}\n\n👉 *Buy Now:* {final_link}"
                send_whatsapp(WHATSAPP_CHANNEL_JID, message)
                posted_deals.append(deal["url"])
                save_posted_deals(posted_deals)
                posted_count += 1
                time.sleep(5)

    if posted_count < 2:
        print("\n--- SECOND PRIORITY (FALLBACK): Fetching from Amazon Official RSS ---")
        amz_deals = get_amazon_rss_deals()
        print(f"Found {len(amz_deals)} official Amazon items in backup feed.")
        
        for deal in amz_deals:
            if posted_count >= 2:
                break
            if deal["url"] not in posted_deals:
                print(f"Posting Backup Deal from Amazon RSS: {deal['title']}")
                final_link = generate_link(deal["url"])
                message = f"🔥 *Amazon Official Loot Deal!*\n\n📦 {deal['title']}\n\n👉 *Buy Now:* {final_link}"
                send_whatsapp(WHATSAPP_CHANNEL_JID, message)
                posted_deals.append(deal["url"])
                save_posted_deals(posted_deals)
                posted_count += 1
                time.sleep(5)

    print("\nBot run execution finished successfully.")

if __name__ == "__main__":
    main()
