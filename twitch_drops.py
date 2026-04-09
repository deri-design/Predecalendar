import json
import requests
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

def fetch_drops():
    print("--- Beziehe aktive Drops und Zeiträume von TwitchDrops.app ---")
    
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

        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # JSON-Block auslesen für präzise Daten
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data:
            data = json.loads(next_data.string)
            page_props = data.get('props', {}).get('pageProps', {})
            game_obj = page_props.get('game', {})
            raw_campaigns = game_obj.get('drop_campaigns', []) or page_props.get('campaigns', [])
            
            for camp in raw_campaigns:
                if str(camp.get('status', '')).upper() == 'ACTIVE' or camp.get('active'):
                    rewards = []
                    for item in camp.get('items', []):
                        img = item.get('image', '')
                        if img and img.startswith('/'): img = "https://twitchdrops.app" + img
                        rewards.append({
                            "name": item.get('name', 'Belohnung'),
                            "image": img,
                            "minutes": item.get('required_minutes') or item.get('minutes', 60)
                        })
                    
                    if rewards:
                        active_campaigns.append({
                            "campaign_name": camp.get('name', 'Predecessor Drops'),
                            "start": camp.get('starts_at') or camp.get('startAt'),
                            "end": camp.get('ends_at') or camp.get('endAt'),
                            "rewards": rewards
                        })

        # Fallback: Falls JSON nicht geht, versuchen wir das End-Datum aus dem Text zu fischen
        if not active_campaigns and "Predecessor" in html:
            # Suche nach dem Zeitstempel im Text (z.B. May 4, 2026)
            date_match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', html)
            end_date = date_match.group(1) if date_match else "2026-05-04"
            
            active_campaigns.append({
                "campaign_name": "Predecessor Twitch Drops",
                "start": "2026-04-07",
                "end": end_date,
                "rewards": [{"name": "Loot Cores / Skins", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 60}]
            })

    except Exception as e:
        print(f"Fehler: {e}")

    german_time = datetime.now(timezone.utc) + timedelta(hours=2)
    output = {
        "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
        "active": len(active_campaigns) > 0,
        "campaigns": active_campaigns
    }
    
    with open('drops.json', 'w') as f:
        json.dump(output, f, indent=4)
    print(f"Update fertig. Aktiv: {output['active']}")

if __name__ == "__main__":
    fetch_drops()
