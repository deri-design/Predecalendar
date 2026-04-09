import json
import requests
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

def fetch_drops():
    print("--- Synchronisiere Twitch Drops (Detailliert) ---")
    
    url = "https://twitchdrops.app/game/predecessor"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    }

    active_campaigns = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return

        # Trenne HTML bei "PAST DROPS"
        html_parts = re.split(r'PAST DROPS', response.text, flags=re.IGNORECASE)
        active_html = html_parts[0]
        soup = BeautifulSoup(active_html, 'html.parser')
        
        # Suche im JSON-Block nach exakten Zeiträumen
        full_soup = BeautifulSoup(response.text, 'html.parser')
        next_data = full_soup.find('script', id='__NEXT_DATA__')
        
        if next_data:
            data = json.loads(next_data.string)
            page_props = data.get('props', {}).get('pageProps', {})
            game_obj = page_props.get('game', {})
            raw_campaigns = game_obj.get('drop_campaigns', []) or page_props.get('campaigns', [])
            
            for camp in raw_campaigns:
                status = str(camp.get('status', '')).upper()
                if status == 'ACTIVE' or 'Premium' in camp.get('name', ''):
                    rewards = []
                    for item in camp.get('items', []):
                        img = item.get('image', '')
                        if img and img.startswith('/'): img = "https://twitchdrops.app" + img
                        rewards.append({
                            "name": item.get('name', 'Belohnung'),
                            "image": img,
                            "minutes": int(item.get('required_minutes') or item.get('minutes', 60))
                        })
                    
                    if rewards:
                        active_campaigns.append({
                            "campaign_name": camp.get('name'),
                            "start": camp.get('starts_at') or camp.get('startAt') or "2026-04-07T18:00:00Z",
                            "end": camp.get('ends_at') or camp.get('endAt') or "2026-05-04T18:00:00Z",
                            "rewards": rewards
                        })

    except Exception as e:
        print(f"Fehler: {e}")

    # CEST Zeitstempel (+2h von UTC)
    german_time = datetime.now(timezone.utc) + timedelta(hours=2)
    output = {
        "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
        "active": len(active_campaigns) > 0,
        "campaigns": active_campaigns
    }
    
    with open('drops.json', 'w') as f:
        json.dump(output, f, indent=4)
    print("Drops-Update erfolgreich.")

if __name__ == "__main__":
    fetch_drops()
