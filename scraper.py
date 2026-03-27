import requests
import json
import re
from datetime import datetime, timedelta

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def parse_relative_date(text):
    text = text.lower().strip()
    now = datetime.now()
    if 'ago' in text:
        num = re.findall(r'\d+', text)
        if num:
            n = int(num[0])
            if 'day' in text: return (now - timedelta(days=n)).strftime("%Y-%m-%d")
            if 'hour' in text: return now.strftime("%Y-%m-%d")
    match = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})', text)
    if match:
        mon, day, year = match.groups()
        try:
            dt = datetime.strptime(f"{mon[:3].capitalize()} {day} {year}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except: pass
    return None

def scrape():
    print("--- Starting Visual Scrape ---")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        html = response.text
        
        # Grab the raw data block
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match: 
            print("Error: Could not find __NEXT_DATA__")
            return

        data = json.loads(match.group(1))
        
        # Deep search for news list
        def find_news_list(obj):
            if isinstance(obj, dict):
                if 'newsList' in obj: return obj['newsList']
                if 'articles' in obj: return obj['articles']
                for v in obj.values():
                    res = find_news_list(v)
                    if res: return res
            elif isinstance(obj, list):
                for i in obj:
                    res = find_news_list(i)
                    if res: return res
            return None

        news_items = find_news_list(data)
        if not news_items:
            print("Error: No news found in JSON structure.")
            return

        final_events = []
        for item in news_items:
            title = item.get('title', 'Update')
            slug = item.get('slug', '')
            category = item.get('category', {}).get('slug', 'news')
            
            # Date
            raw_date = item.get('publishedAt') or item.get('createdAt') or ""
            date_str = raw_date[:10] if raw_date else datetime.now().strftime("%Y-%m-%d")
            
            # IMAGE LOGIC
            img_url = ""
            img_data = item.get('image') or item.get('thumbnail') or {}
            if isinstance(img_data, dict):
                img_url = img_data.get('url', '')
            
            # Ensure full path for images
            if img_url and img_url.startswith('/'):
                img_url = BASE_URL + img_url

            # URL & Path Fixes
            full_url = f"{BASE_URL}/en-US/news/{category}/{slug}"
            if "patch" in title.lower():
                full_url = full_url.replace("-patch-notes", "-patchnotes")

            final_events.append({
                "date": date_str,
                "title": title,
                "url": full_url,
                "image": img_url,
                "type": "patch" if "patch" in title.lower() or category == "patch-notes" else "news"
            })

        with open('events.json', 'w') as f:
            json.dump(final_events, f, indent=4)
        print(f"Success! Saved {len(final_events)} events WITH images.")

    except Exception as e:
        print(f"Critical Scrape Error: {e}")

if __name__ == "__main__":
    scrape()
