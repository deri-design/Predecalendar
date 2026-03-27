import requests
import json
import re
from datetime import datetime, timedelta

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def scrape():
    print("--- Starting Visual Scrape ---")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        html = response.text
        
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match: 
            print("Error: Could not find data block")
            return

        data = json.loads(match.group(1))
        
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
            print("Error: No news found.")
            return

        events = []
        for item in news_items:
            title = item.get('title', 'Update')
            slug = item.get('slug', '')
            category = item.get('category', {}).get('slug', 'news')
            raw_date = item.get('publishedAt') or item.get('createdAt') or ""
            
            img_url = ""
            image_data = item.get('image') or item.get('thumbnail') or {}
            if isinstance(image_data, dict):
                img_url = image_data.get('url', '')
            if img_url and img_url.startswith('/'):
                img_url = BASE_URL + img_url

            full_url = f"{BASE_URL}/en-US/news/{category}/{slug}"
            if "patch" in title.lower():
                full_url = full_url.replace("-patch-notes", "-patchnotes")

            events.append({
                "date": raw_date[:10],
                "title": title,
                "url": full_url,
                "image": img_url,
                "type": "patch" if "patch" in title.lower() or category == "patch-notes" else "news"
            })

        # --- THE FIX: Add a timestamp to force a file change ---
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events
        }

        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success! Saved {len(events)} events.")

    except Exception as e:
        print(f"Scrape Error: {e}")

if __name__ == "__main__":
    scrape()
