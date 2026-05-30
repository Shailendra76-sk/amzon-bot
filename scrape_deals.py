import requests
from bs4 import BeautifulSoup

def get_deals():
    url = "https://www.desidime.com/new"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    deals = []
    
    # Based on the viewport elements and HTML structure analysis
    # Deal titles are often in <a> tags within certain classes
    # Let's look for deal containers.
    # From the browser_view, we saw titles like "Women’s Printed & Ethnic Crepe Kurtas at Flat 90% OFF"
    
    deal_cards = soup.select('div.deal-container, div.card, div.topic-box')
    # If standard classes fail, let's try a more general approach based on the text observed
    
    # The browser_view showed elements like index 54, 60, 66 as titles.
    # Let's try to find all links that look like deals
    links = soup.find_all('a', href=True)
    for link in links:
        href = link['href']
        if '/deals/' in href and len(link.get_text(strip=True)) > 20:
            title = link.get_text(strip=True)
            deal_url = "https://www.desidime.com" + href if href.startswith('/') else href
            deals.append({'title': title, 'url': deal_url})
            
    return deals

if __name__ == "__main__":
    deals = get_deals()
    for deal in deals[:5]:
        print(f"Title: {deal['title']}")
        print(f"URL: {deal['url']}")
        print("-" * 20)
