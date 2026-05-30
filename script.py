import requests
from bs4 import BeautifulSoup
import os
import json
import time

# Configuration
DESIDIME_NEW_DEALS_URL = "https://desidime.com"
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

def get_deal_page_urls():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(DESIDIME_NEW_DEALS_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching DesiDime: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    deal_page_urls = []

    # Har naye deal card ka link nikalna
    for card in soup.find_all('div', class_='feed-row'):
        link = card.find('a', class_='deal-title-link') or card.find('a', href=True)
        if link:
            href = link.get('href')
            title = link.get_text(strip=True)
            if href and '/deals/' in href:
                full_url = "https://desidime.com" + href if not href.startswith('http') else href
                if full_url not in [d['url'] for d in deal_page_urls]:
                    deal_page_urls.append({"title": title, "url": full_url})
                
    # Fallback to general cards if layout changes
    if not deal_page_urls:
        for title_div in soup.find_all('div', class_='custom-card-title'):
            link = title_div.find('a', href=True)
            if link:
                href = link.get('href')
                title = link.get_text(strip=True)
                if href and '/deals/' in href:
                    full_url = "https://desidime.com" + href if not href.startswith('http') else href
                    deal_page_urls.append({"title": title, "url": full_url})

    return deal_page_urls

def get_product_url(deal_page_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(deal_page_url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching deal page {deal_page_url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. Sabse pehle poore page par direct Amazon/Flipkart/Myntra ke links dhoondhein
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and any(site in href for site in ['amazon.in', 'flipkart.com', 'myntra.com', 'ajio.com', 'tatacliq.com']):
            if '://desidime.com' not in href:
                print(f"Found direct clean link: {href}")
                return href

    # 2. Agar direct link nahi mila, toh 'Buy Now' ka link nikal kar follow karein
    for buy_now in soup.find_all('a', href=True):
        href = buy_now.get('href')
        text = buy_now.get_text().lower()
        if href and ('buy' in text or 'get' in text or 'visit' in href):
            if '://desidime.com' in href or '://desidime.com' in href:
                try:
                    # Redirect track karne ke liye request bhejna
                    print(f"Following Desidime link: {href}")
                    res = requests.get(href, headers=headers, allow_redirects=True, timeout=15)
                    print(f"Final Destination URL: {res.url}")
                    return res.url
                except:
                    continue
            elif not href.startswith('/') and 'desidime' not in href:
                return href

    return None

def generate_affiliate_link(product_url):
    # Sirf Amazon links ke peeche tag lagayein
    if 'amazon.in' in product_url:
        if "?" in product_url:
            return f"{product_url}&tag={AMAZON_AFFILIATE_TAG}"
        else:
            return f"{product_url}?tag={AMAZON_AFFILIATE_TAG}"
    return product_url # Baki websites ke link ko bina badle jaane dein

def send_whatsapp_message(chat_id, message_text):
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("Green-API Credentials error. Secrets check karein.")
        return

    url = f"https://green-api.com{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {"chatId": chat_id, "message": message_text}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        print(f"WhatsApp Response: {response.text}")
    except Exception as e:
        print(f"Error sending WhatsApp: {e}")

def main():
    posted_deals = load_posted_deals()
    deal_page_urls = get_deal_page_urls()
    
    print(f"Found {len(deal_page_urls)} potential deal pages.")

    # Ek baar mein maximum 2 nayi deals bhejega taaki channel block na ho
    posted_count = 0
    for deal_info in deal_page_urls:
        if posted_count >= 2:
            break
            
        deal_page_url = deal_info["url"]
        deal_title = deal_info["title"]

        if deal_page_url not in posted_deals:
            print(f"\nProcessing deal: {deal_title}")
            product_url = get_product_url(deal_page_url)
            
            if product_url:
                affiliate_link = generate_affiliate_link(product_url)
                
                message = (
                    f"🔥 *New Loot Deal!*\n\n"
                    f"📦 {deal_title}\n\n"
                    f"👉 *Buy Now:* {affiliate_link}"
                )
                
                send_whatsapp_message(WHATSAPP_CHANNEL_JID, message)
                posted_deals.append(deal_page_url)
                save_posted_deals(posted_deals)
                posted_count += 1
                time.sleep(5)
            else:
                print("Could not extract any product link for this card.")

    print("Bot run complete.")

if __name__ == "__main__":
    main()
