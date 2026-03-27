import requests
import json
import re
from datetime import datetime, timedelta

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def parse_relative_date(text):
    """Converts '2 days ago' or 'Mar 18, 2026' into YYYY-MM-DD"""
    text = text.lower().strip()
    now = datetime.now()
    
    # Handle "X days/hours ago"
    if 'ago' in text:
        num = re.findall(r'\d+', text)
        if num:
            n = int(num[0])
            if 'day' in text:
                return (now - timedelta(days=n)).strftime("%Y-%m-%d")
            if 'hour' in text:
                return now.strftime("%Y-%m-%d")
    
    # Handle "Mar 18, 2026"
    match = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})', text)
    if match:
        mon, day, year = match.groups()
        try:
            dt = datetime.strptime(f"{mon[:3].capitalize()} {day} {year}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except: pass
    return None

def scrape():
    print("Starting Ultimate Scrape...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    
    # Updated safety net with EVERYTHING visible in your screenshot
    events = [
        {"date": "2026-03-25", "title": "Refer-a-Friend Competition", "type": "news", "url": f"{BASE_URL}/en-US/news/events/refer-a-friend-competition"},
        {"date": "2026-03-18", "title": "V1.12.6 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-12-6-patchnotes"},
        {"date": "2026-03-06", "title": "V1.12.4 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-12-4-patchnotes"},
        {"date": "2026-03-05", "title": "Daybreak Updates (New Map)", "type": "news", "url": f"{BASE_URL}/en-US/news/dev-diary/daybreak-introduction"},
        {"date": "2026-02-26", "title": "Double Trouble Weekend!", "type": "news", "url": f"{BASE_URL}/en-US/news/events/double-trouble"},
        {"date": "2026-02-25", "title": "Friend Reward Competition", "type": "news", "url": f"{BASE_URL}/en-US/news/events/friend-reward-competition"},
        {"date": "2026-02-19", "title": "V1.12 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-12-patch-notes"},
        {"date": "2026-02-10", "title": "Enemies For Life", "type": "news", "url": f"{BASE_URL}/en-US/news/announcements/enemies-for-life"},
        {"date": "2026-02-05", "title": "2026 Competitive Events Update", "type": "news", "url": f"{BASE_URL}/en-US/news/events/pcc-competitive-events-update"},
        {"date": "2026-01-29", "title": "V1.11.2 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-11-2-patch-notes"},
        {"date": "2026-01-14", "title": "V1.11 Patch Notes", "type": "patch", "url": f"{BASE_URL}/en-US/news/patch-notes/v1-11-patch-notes"}
    ]

    try:
        response = requests.get(URL, headers=headers, timeout=15)
        # We search the HTML directly for anything that looks like a news link and its date
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        cards = soup.find_all('a', href=re.compile(r'/news/'))
        for card in cards:
            title_tag = card.find(['h2', 'h3', 'h4', 'p', 'span'], string=True)
            if not title_tag: continue
            
            title = title_tag.get_text().strip()
            if len(title) < 5: continue
            
            # Find date by looking for "ago" or month names in the card
            card_text = card.get_text()
            found_date = parse_relative_date(card_text)
            
            if found_date:
                link = BASE_URL + card['href'] if card['href'].startswith('/') else card['href']
                # Fix patch URL hyphenation
                if "patch" in title.lower():
                    link = link.replace("-patch-notes", "-patchnotes")
                
                # If not already in our manual list, add it
                if not any(e['url'] == link for e in events):
                    events.append({
                        "date": found_date, 
                        "title": title, 
                        "url": link, 
                        "type": "patch" if "patch" in title.lower() else "news"
                    })

    except Exception as e:
        print(f"Scrape error: {e}")

    # Write the combined list to JSON
    with open('events.json', 'w') as f:
        json.dump(events, f, indent=4)
    print(f"Success! {len(events)} events saved.")

if __name__ == "__main__":
    scrape()
