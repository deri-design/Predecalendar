import requests
import json
import re
from datetime import datetime

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com/en-US/news"

def scrape():
    print("Starting Live API Scrape...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        html = response.text
        
        # 1. Locate the JSON data block embedded in the HTML (Next.js __NEXT_DATA__)
        # This is where the actual database records for news are stored.
        json_pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(json_pattern, html)
        
        if not match:
            print("Could not find the data block. Website structure may have changed.")
            return

        data = json.loads(match.group(1))
        
        # 2. Navigate to the news list inside the JSON
        # Path: props -> pageProps -> news (or similar based on current site state)
        # We search deep for the key 'newsList' or 'articles'
        news_list = []
        
        # Search for the news array inside the complex JSON object
        def find_news_list(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == 'newsList' and isinstance(v, list):
                        return v
                    res = find_news_list(v)
                    if res: return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_news_list(item)
                    if res: return res
            return None

        news_data = find_news_list(data)
        
        if not news_data:
            print("Found the data block but no news items inside.")
            return

        final_events = []
        for item in news_data:
            # Extract fields
            title = item.get('title', 'Untitled Update')
            slug = item.get('slug', '')
            # Categories: patch-notes, dev-diary, events, announcements, community
            category = item.get('category', {}).get('slug', 'announcements')
            
            # Use the 'publishedAt' or 'createdAt' date
            raw_date = item.get('publishedAt') or item.get('createdAt') or ""
            # Format: 2026-03-17T14:00:00.000Z -> 2026-03-17
            date_str = raw_date[:10] if len(raw_date) >= 10 else datetime.now().strftime("%Y-%m-%d")

            # 3. Build the EXACT URL
            # The pattern is: BASE_URL / category-slug / article-slug
            full_url = f"{BASE_URL}/{category}/{slug}"

            final_events.append({
                "date": date_str,
                "title": title,
                "url": full_url,
                "type": "patch" if category == "patch-notes" or "patch" in title.lower() else "news",
                "desc": f"Category: {category.replace('-', ' ').title()}"
            })

        # 4. Save to events.json
        with open('events.json', 'w') as f:
            json.dump(final_events, f, indent=4)
        
        print(f"Success! {len(final_events)} live events scraped and URLs generated.")

    except Exception as e:
        print(f"Critical Scrape Error: {e}")

if __name__ == "__main__":
    scrape()
