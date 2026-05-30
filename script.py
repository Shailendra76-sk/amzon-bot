import requests
from bs4 import BeautifulSoup
import os
import json
import time

# Configuration
DESIDIME_NEW_DEALS_URL = "https://www.desidime.com/new"
AMAZON_AFFILIATE_TAG = "sk200709-21"
GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN")
WHATSAPP_CHANNEL_JID = "120363294334346747@newsletter"

# File to store already posted deal URLs
POSTED_DEALS_FILE = "posted_deals.json"

def load_posted_deals():
    if os.path.exists(POSTED_DEALS_FILE):
        with open(POSTED_DEALS_FILE, "r") as f:
            return json.load(f)
    return []

def save_posted_deals(deals):
    with open(POSTED_DEALS_FILE, "w") as f:
        json.dump(deals, f)

def get_deal_page_urls():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36)'
    }
    try:
        response = requests.get(DESIDIME_NEW_DEALS_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching DesiDime new deals page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    deal_page_urls = []

    # Find all 'div' elements with class 'custom-card-title' which contain the deal link and title
    for title_div in soup.find_all('div', class_='custom-card-title'):
        link = title_div.find('a', href=True)
        if link:
            href = link.get('href')
            title = link.get_text(strip=True)

            if href and '/deals/' in href and title and len(title) > 5:
                # Construct full URL if it's a relative path
                if not href.startswith('http'):
                    full_deal_url = "https://www.desidime.com" + href
                else:
                    full_deal_url = href
                
                # Avoid duplicate URLs
                if full_deal_url not in [d['url'] for d in deal_page_urls]:
                    deal_page_urls.append({"title": title, "url": full_deal_url})
                
    return deal_page_urls

def get_product_url(deal_page_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36)'
    }
    try:
        response = requests.get(deal_page_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching deal page {deal_page_url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    product_url = None

    # First, try to find the 'Buy Now' button and follow its redirect
    buy_now_link = soup.find('a', string=lambda text: text and 'Buy Now' in text, href=True)
    
    if buy_now_link and buy_now_link.get('href'):
        redirect_url = buy_now_link.get('href')
        print(f"Found 'Buy Now' link: {redirect_url}")
        # Desidime uses an intermediary redirect service (visit.desidime.com)
        # We need to follow this redirect to get the actual product URL.
        if 'visit.desidime.com/visit/' in redirect_url:
            try:
                # Follow the redirect to get the final product URL using requests.get
                final_response = requests.get(redirect_url, headers=headers, allow_redirects=True, timeout=15)
                final_response.raise_for_status()
                print(f"Followed redirect to: {final_response.url}")
                product_url = final_response.url
            except requests.exceptions.RequestException as e:
                print(f"Error following redirect from {redirect_url}: {e}")
        else:
            # If it's not a Desidime redirect, assume it's the direct product URL
            print(f"Direct product URL from 'Buy Now': {redirect_url}")
            product_url = redirect_url
            
    # If product_url is still None or not a suitable product link, try to find direct e-commerce links
    # A suitable product link is one that is not a generic app store link.
    if not product_url or ('play.google.com' in product_url and ('details?id=' not in product_url or 'store/apps' in product_url)):
        print("Falling back to searching for direct e-commerce links...")
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            # More specific check for product links, avoiding generic app links
            if href and any(site in href for site in ['amazon.in', 'flipkart.com', 'myntra.com', 'swiggy.com', 'tatacliq.com', 'ajio.com']) and 'desidime.com' not in href:
                # Further refine for play.google.com to ensure it's a product/deal and not just the app
                if 'play.google.com' in href and ('details?id=' not in href or 'store/apps' in href):
                    continue # Skip generic app links
                print(f"Found direct e-commerce link: {href}")
                product_url = href
                break # Take the first one found
            
    if not product_url:
        print("No suitable product URL found for this deal page.")
    return product_url

def generate_affiliate_link(product_url):
    if "?" in product_url:
        return f"{product_url}&tag={AMAZON_AFFILIATE_TAG}"
    else:
        return f"{product_url}?tag={AMAZON_AFFILIATE_TAG}"

def send_whatsapp_message(chat_id, message_text):
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("Green-API credentials not set. Skipping WhatsApp message.")
        return

    url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "chatId": chat_id,
        "message": message_text
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        print(f"WhatsApp message sent successfully: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")

def main():
    posted_deals = load_posted_deals()
    deal_page_urls = get_deal_page_urls()
    
    print(f"Found {len(deal_page_urls)} potential deal pages.")

    for deal_info in deal_page_urls:
        deal_page_url = deal_info["url"]
        deal_title = deal_info["title"]

        if deal_page_url not in posted_deals:
            product_url = get_product_url(deal_page_url)
            if product_url:
                affiliate_link = generate_affiliate_link(product_url)
                
                # Clean up title for WhatsApp formatting (remove hotness score, etc.)
                clean_title = deal_title
                if clean_title and clean_title[0].isdigit() and '°' in clean_title:
                    clean_title = clean_title.split('°', 1)[1].strip()
                if '₹' in clean_title:
                    clean_title = clean_title.split('₹')[0].strip()

                message = (
                    f"🔥 *New Loot Deal!*\n\n"
                    f"📦 {clean_title}\n\n"
                    f"👉 *Buy Now:* {affiliate_link}"
                )
                
                print(f"Posting new deal: {clean_title}")
                send_whatsapp_message(WHATSAPP_CHANNEL_JID, message)
                posted_deals.append(deal_page_url) # Store the deal page URL to avoid reposting
                save_posted_deals(posted_deals)
                time.sleep(5) # Be nice to the API and avoid rate limiting
            else:
                print(f"Could not extract product URL for deal: {deal_title}")

    print("Bot run complete.")

if __name__ == "__main__":
    main()
