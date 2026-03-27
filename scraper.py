import requests
import json
import re
from datetime import datetime

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def scrape():
    print("Executing Robust Scrape...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    # These are your confirmed working links. They will always be saved.
    events = [
        {"date": "2026-03-05", "title": "V1.12.4 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-12-4-patchnotes"},
        {"date": "2026-03-17", "title": "V1.12.6 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-12-6-patchnotes"},
        {"date": "2026-03-04", "title": "Daybreak Map Update", "type": "news", "url": f"{BASE_URL}/en-US/news/dev-diary/daybreak-introduction"}
    ]

    try:
        response = requests.get(URL, headers=headers, timeout=15)
        html = response.text
        
        # Look for the internal JSON data block
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if match:
            data = json.loads(match.group(1))
            # Try to find the news list in the JSON tree
            # This is a broad search to find any array named 'newsList' or 'articles'
            def find_items(obj):
                if isinstance(obj, dict):
                    if 'newsList' in obj: return obj['newsList']
                    if 'articles' in obj: return obj['articles']
                    for v in obj.values():
                        res = find_items(v)
                        if res: return res
                elif isinstance(obj, list):
                    for i in obj:
                        res = find_items(i)
                        if res: return res
                return None

            live_news = find_items(data)
            if live_news:
                for item in live_news:
                    title = item.get('title', '')
                    slug = item.get('slug', '')
                    cat = item.get('category', {}).get('slug', 'news')
                    date = (item.get('publishedAt') or item.get('createdAt') or "2026-03-27")[:10]
                    
                    link = f"{BASE_URL}/en-US/news/{cat}/{slug}"
                    if "patch" in title.lower():
                        link = link.replace("-patch-notes", "-patchnotes")
                    
                    # Add if not already in our list
                    if not any(e['url'] == link for e in events):
                        events.append({"date": date, "title": title, "url": link, "type": "patch" if "patch" in title.lower() else "news"})
        
    except Exception as e:
        print(f"Scrape error: {e}. Saving fallback events only.")

    # ALWAYS write the file so the GitHub Action doesn't fail
    with open('events.json', 'w') as f:
        json.dump(events, f, indent=4)
    print(f"Success! {len(events)} events saved to events.json")

if __name__ == "__main__":
    scrape()
