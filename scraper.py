import requests
import re
import json
from datetime import datetime

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def scrape():
    print("Starting Universal Brute-Force Scrape...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        html = response.text
        
        # 1. Find all potential news links and the text around them
        # We look for <a> tags containing /news/ and grab a large chunk of surrounding text
        # to find the associated date.
        links = re.findall(r'href="(/en-US/news/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        
        # 2. Find all dates on the page in format "Month DD, YYYY"
        # We'll map these to the links we found.
        all_dates = re.findall(r'([A-Z][a-z]+ \d{1,2}, \d{4})', html)
        
        print(f"Found {len(links)} links and {len(all_dates)} dates.")

        final_events = []
        
        # We loop through the links and try to match them with the dates
        # Typically, the first N links on the page match the first N dates found.
        for i in range(len(links)):
            if i >= len(all_dates): break
            
            raw_url = links[i][0]
            inner_html = links[i][1]
            
            # Clean the title: remove HTML tags and extra whitespace
            title = re.sub('<[^<]+?>', '', inner_html).strip()
            if not title or len(title) < 5: 
                # If title is empty/short, it's likely an image link, skip it
                continue
            
            # Convert date: "March 17, 2026" -> "2026-03-17"
            try:
                raw_date = all_dates[i]
                clean_date = datetime.strptime(raw_date, "%B %d, %Y").strftime("%Y-%m-%d")
            except:
                continue

            full_url = BASE_URL + raw_url
            
            # Fix the hyphen inconsistency for patches automatically
            if "-patch-notes" in full_url and "v1-" in full_url:
                full_url = full_url.replace("-patch-notes", "-patchnotes")

            final_events.append({
                "date": clean_date,
                "title": title,
                "url": full_url,
                "type": "patch" if "patch" in title.lower() else "news",
                "desc": f"Published: {raw_date}"
            })

        # Remove duplicates based on URL
        unique_events = list({v['url']: v for v in final_events}.values())

        if not unique_events:
            print("Warning: No events captured. The site layout might be blocking the scraper.")
        else:
            with open('events.json', 'w') as f:
                json.dump(unique_events, f, indent=4)
            print(f"Success! Saved {len(unique_events)} events.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    scrape()
