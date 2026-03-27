import requests
import re
import json
from datetime import datetime

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def scrape():
    print("--- Starting Power Scrape ---")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=20)
        print(f"Status Code: {response.status_code}")
        html = response.text
        
        # Look for news links
        links = re.findall(r'href="(/en-US/news/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        # Look for multiple date formats: "March 17, 2026" or "17 March 2026"
        dates = re.findall(r'([A-Z][a-z]+ \d{1,2}, \d{4})|(\d{1,2} [A-Z][a-z]+ \d{4})', html)
        
        print(f"Found {len(links)} links and {len(dates)} dates.")

        final_events = []
        for i in range(min(len(links), len(dates))):
            raw_url = links[i][0]
            inner_html = links[i][1]
            
            # Clean title
            title = re.sub('<[^<]+?>', '', inner_html).strip()
            if len(title) < 3: continue
            
            # Handle the two date regex groups
            date_tuple = dates[i]
            raw_date = date_tuple[0] if date_tuple[0] else date_tuple[1]
            
            try:
                # Try Month DD, YYYY
                if "," in raw_date:
                    clean_date = datetime.strptime(raw_date, "%B %d, %Y").strftime("%Y-%m-%d")
                # Try DD Month YYYY
                else:
                    clean_date = datetime.strptime(raw_date, "%d %B %Y").strftime("%Y-%m-%d")
            except Exception as e:
                print(f"Date Parse Error on '{raw_date}': {e}")
                continue

            full_url = BASE_URL + raw_url
            # Fix URL hyphen inconsistency
            if "patch" in full_url.lower() and "-patch-notes" in full_url:
                full_url = full_url.replace("-patch-notes", "-patchnotes")

            final_events.append({
                "date": clean_date,
                "title": title,
                "url": full_url,
                "type": "patch" if "patch" in title.lower() else "news"
            })

        if not final_events:
            print("ALERT: No events found. The scraper might be blocked or site layout changed.")
            return

        with open('events.json', 'w') as f:
            json.dump(final_events, f, indent=4)
        print(f"Successfully wrote {len(final_events)} events to events.json")

    except Exception as e:
        print(f"CRITICAL SCRAPER ERROR: {e}")

if __name__ == "__main__":
    scrape()
