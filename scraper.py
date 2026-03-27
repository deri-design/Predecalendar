import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta

URL = "https://www.predecessorgame.com/en-US/news"
BASE_URL = "https://www.predecessorgame.com"

def parse_date(text):
    text = text.lower().strip()
    if 'ago' in text:
        num = re.findall(r'\d+', text)
        n = int(num[0]) if num else 0
        return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
    match = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})', text)
    if match:
        try:
            dt = datetime.strptime(f"{match.group(1)[:3].capitalize()} {match.group(2)} {match.group(3)}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except: pass
    return datetime.now().strftime("%Y-%m-%d")

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
            if len(title) < 4: continue

            link = BASE_URL + art['href'] if art['href'].startswith('/') else art['href']
            
            img_tag = art.find('img')
            img_url = ""
            if img_tag:
                img_url = img_tag.get('src') or img_tag.get('data-src') or ""
                if img_url.startswith('/'): img_url = BASE_URL + img_url

            date_str = parse_date(art.get_text())

            events.append({
                "date": date_str,
                "title": title,
                "url": link,
                "image": img_url,
                "type": "patch" if "patch" in title.lower() else "news"
            })
    except Exception as e:
        print(f"Error during scrape: {e}")

    # ALWAYS write the file so the Action doesn't fail
    output = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "events": events
    }
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)

if __name__ == "__main__":
    scrape()
