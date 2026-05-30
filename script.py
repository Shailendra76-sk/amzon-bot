import requests
from bs4 import BeautifulSoup
import os
import json
import time

# --- CONFIGURATION (Sahi Group Link Ke Sath) ---
AMAZON_LIVE_DEALS_URL = "https://rss.app" 
AMAZON_AFFILIATE_TAG = "sk200709-21"

GREEN_API_INSTANCE_ID = "7107592101"
GREEN_API_TOKEN = "269f8275111a41439ffebad121b742835c6027d6c6cb40678d"

# Aapka bheja hua asli real WhatsApp group link
GROUP_INVITE_LINK = "https://chat.whatsapp.com/BBP6AltCSKk6tTZ8iFuywz"

POSTED_DEALS_FILE = "posted_deals.json"

def load_posted_deals():
    if os.path.exists(POSTED_DEALS_FILE):
        with open(POSTED_DEALS_FILE, "r") as f:
            try: return json.load(f)
            except: return []
    return []

def save_posted_deals(deals):
    with open(POSTED_DEALS_FILE, "w") as f:
        json.dump(deals, f)

def get_live_deals():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    deals_list = []
    
    try:
        res = requests.get(AMAZON_LIVE_DEALS_URL, headers=headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for item in soup.find_all(['item', 'entry']):
                title_tag = item.find(['title'])
                link_tag = item.find(['link'])
                title = title_tag.get_text(strip=True) if title_tag else ""
                link = link_tag.get_text(strip=True) if link_tag else ""
                if link_tag and not link:
                    link = link_tag.get('href', '')
                if title and link:
                    clean_link = link.split('?').split('&')
                    deals_list.append({"title": title, "url": clean_link})
    except:
        pass

    if not deals_list:
        try:
            backup_url = "https://desidime.com"
            res = requests.get(backup_url, headers=headers, timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag.get('href')
                    title = a_tag.get_text(strip=True)
                    if href and '/deals/' in href and len(title) > 15:
                        full_url = "https://desidime.com" + href if not href.startswith('http') else href
                        deals_list.append({"title": title, "url": full_url})
        except:
            pass

    return deals_list

def send_whatsapp_by_link(invite_link, msg):
    # Green-API ka official method direct group link par message bhejne ke liye
    url = f"https://greenapi.com{GREEN_API_INSTANCE_ID}/sendMessageByLink/{GREEN_API_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "inviteLink": invite_link,
        "message": msg
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        print(f"Direct Group Link Server Response: {res.text}")
    except Exception as e:
        print(f"WhatsApp Connection Error: {e}")

def main():
    posted_deals = load_posted_deals()
    live_items = get_live_deals()
    print(f"Total {len(live_items)} working product structures filtered.")
    
    posted_count = 0
    for item in live_items:
        if posted_count >= 2:
            break
            
        target_url = item["url"]
        product_title = item["title"]
        
        if target_url not in posted_deals:
            print(f"Posting Deal: {product_title}")
            
            if 'amazon.in' in target_url or 'desidime' not in target_url:
                final_link = f"{target_url}?tag={AMAZON_AFFILIATE_TAG}" if "?" not in target_url else f"{target_url}&tag={AMAZON_AFFILIATE_TAG}"
            else:
                final_link = target_url
                
            message = (
                f"🔥 *New Live Loot Deal!*\n\n"
                f"📦 {product_title}\n\n"
                f"👉 *Buy Now:* {final_link}"
            )
            
            # Direct link function call kiya hai
            send_whatsapp_by_link(GROUP_INVITE_LINK, message)
            posted_deals.append(target_url)
            save_posted_deals(posted_deals)
            posted_count += 1
            time.sleep(5)

    print("\nSystem run complete.")

if __name__ == "__main__":
    main()
