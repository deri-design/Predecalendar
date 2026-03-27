import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def parse_date(art_soup):
    """Deep search for dates within an article card"""
    # 1. Look for <time> tags (Best)
    time_tag = art_soup.find('time')
    if time_tag and time_tag.has_attr('datetime'):
        return time_tag['datetime'][:10]

    # 2. Get all text segments to check for "ago" or "Month DD, YYYY"
    text_content = art_soup.get_text(separator='|').lower()
    segments = [s.strip() for s in text_content.split('|')]
    
    now = datetime.now()
    for s in segments:
        # Handle "X days ago"
        if 'ago' in s:
            num = re.findall(r'\d+', s)
            n = int(num[0]) if num else 0
            return (now - timedelta(days=n)).strftime("%Y-%m-%d")
        
        # Handle "Mar 18, 2026"
        match = re.search(r'([a-z]{3})\s+(\d{1,2}),?\s+(\d{4})', s)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1).capitalize()} {match.group(2)} {match.group(3)}", "%b %d %Y")
                return dt.strftime("%Y-%m-%d")
            except: pass
            
    # Default to a safe placeholder if not found (helps debugging)
    return "2026-03-01" 

def scrape():
    print("--- Precision Visual Scrape ---")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'}
    events = []
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Target the news cards
        articles = soup.find_all('a', href=re.compile(r'/news/'))
        print(f"Found {len(articles)} potential articles.")

        for art in articles:
            # 1. Title
            title_tag = art.find(['h2', 'h3', 'h4'])
            if not title_tag: continue
            title = title_tag.get_text().strip()
            
            # 2. Link
            link = BASE_URL + art['href'] if art['href'].startswith('/') else art['href']
            if "patch" in title.lower(): link = link.replace("-patch-notes", "-patchnotes")

            # 3. Image
            img_tag = art.find('img')
            img_url = ""
            if img_tag:
                img_url = img_tag.get('src') or img_tag.get('data-src') or ""
                if img_url.startswith('/'): img_url = BASE_URL + img_url

            # 4. Date (Using our new deep search)
            date_str = parse_date(art)

            events.append({
                "date": date_str,
                "title": title,
                "url": link,
                "image": img_url,
                "type": "patch" if "patch" in title.lower() else "news"
            })
            print(f"Captured: {title} on {date_str}")

    except Exception as e:
        print(f"Scrape Error: {e}")

    output = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "events": events
    }
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)

if __name__ == "__main__":
    scrape()
