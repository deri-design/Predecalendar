import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

# Lookup for known articles to ensure perfect dates if scraping fails
DATE_LOOKUP = {
    "v1-12-6-patchnotes": "2026-03-18",
    "v1-12-4-patchnotes": "2026-03-06",
    "daybreak-introduction": "2026-03-05",
    "double-trouble-weekend": "2026-02-26",
    "friend-reward-competition": "2026-02-25",
    "v1-12-patch-notes": "2026-02-19",
    "enemies-for-life": "2026-02-10",
    "pcc-competitive-events-update": "2026-02-05",
    "v1-11-2-patch-notes": "2026-01-29"
}

def parse_date(art_soup, slug):
    # 1. Check our lookup table first
    for key, date in DATE_LOOKUP.items():
        if key in slug: return date

    # 2. Look for <time> tag
    time_tag = art_soup.find('time')
    if time_tag and time_tag.has_attr('datetime'):
        return time_tag['datetime'][:10]

    # 3. Aggressive text search
    text = " ".join(art_soup.get_text(separator=' ').split()).lower()
    now = datetime.now()
    
    if 'ago' in text:
        nums = re.findall(r'\d+', text)
        if nums:
            n = int(nums[0])
            if 'day' in text: return (now - timedelta(days=n)).strftime("%Y-%m-%d")
        return now.strftime("%Y-%m-%d")

    # Match "March 18, 2026" or "Mar 18 2026"
    match = re.search(r'([a-z]{3,})\s+(\d{1,2}),?\s+(\d{4})', text)
    if match:
        m, d, y = match.groups()
        try:
            dt = datetime.strptime(f"{m[:3].capitalize()} {d} {y}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except: pass
            
    return None

def scrape():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    events = []
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('a', href=re.compile(r'/news/'))
        
        for art in articles:
            title_tag = art.find(['h2', 'h3', 'h4', 'p'])
            if not title_tag: continue
            title = title_tag.get_text().strip()
            slug = art['href']
            
            link = BASE_URL + slug if slug.startswith('/') else slug
            # Fix URL hyphenation
            if "patch" in title.lower(): link = link.replace("-patch-notes", "-patchnotes")

            img_tag = art.find('img')
            img_url = ""
            if img_tag:
                img_url = img_tag.get('src') or img_tag.get('data-src') or ""
                if img_url.startswith('/'): img_url = BASE_URL + img_url

            date_str = parse_date(art, slug) or "2026-03-01"

            events.append({
                "date": date_str, "title": title, "url": link, "image": img_url,
                "type": "patch" if "patch" in title.lower() else "news"
            })

        # Save with mandatory change (timestamp)
        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": events}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success: {len(events)} events saved.")
    except Exception as e:
        print(f"Scrape Error: {e}")

if __name__ == "__main__":
    scrape()
