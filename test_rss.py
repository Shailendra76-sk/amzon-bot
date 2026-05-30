import requests
import xml.etree.ElementTree as ET

urls = [
    "https://www.desidime.com/feed/deals.xml",
    "https://www.desidime.com/deals.xml",
    "https://www.desidime.com/posts.atom",
    "https://www.desidime.com/new_deals.xml"
]

for url in urls:
    try:
        print(f"Checking {url}...")
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Content length: {len(response.content)}")
            print(f"Snippet: {response.text[:200]}")
            # Try to parse
            root = ET.fromstring(response.content)
            print("Successfully parsed XML")
            break
    except Exception as e:
        print(f"Error: {e}")
