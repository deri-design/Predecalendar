import json
import requests
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

def fetch_drops():
    print("--- Beziehe Daten von TwitchDrops.app (Predecessor) ---")
    
    url = "https://twitchdrops.app/game/predecessor"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Fehler beim Laden der Seite: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Wir suchen nach dem versteckten Datenblock von Next.js, der alle Kampagnen enthält
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        
        active_campaigns = []
        
        if next_data_script:
            data = json.loads(next_data_script.string)
            # Wir navigieren durch die JSON-Struktur der Seite
            # Die Struktur liegt meist unter props -> pageProps
            page_props = data.get('props', {}).get('pageProps', {})
            game_data = page_props.get('game', {})
            campaigns = game_data.get('drop_campaigns', []) or page_props.get('campaigns', [])

            # Falls wir im JSON nichts finden, nutzen wir eine gezielte HTML-Suche
            if not campaigns:
                print("JSON-Block leer, versuche direkte HTML-Extraktion...")
                # Suche nach den Belohnungs-Karten (wie im Screenshot zu sehen)
                reward_elements = soup.find_all(class_=re.compile(r'reward|item|drop', re.I))
                
                temp_rewards = []
                for el in reward_elements:
                    name_tag = el.find(['h3', 'p', 'span'], class_=re.compile(r'title|name', re.I))
                    time_tag = el.find(string=re.compile(r'Watch \d+', re.I))
                    img_tag = el.find('img')

                    if name_tag and time_tag:
                        name = name_tag.get_text().strip()
                        # Extrahiere Minuten aus "Watch 2h" -> 120
                        time_str = time_tag.strip()
                        minutes = 60
                        time_match = re.search(r'(\d+)', time_str)
                        if time_match:
                            val = int(time_match.group(1))
                            minutes = val * 60 if 'h' in time_str.lower() else val
                        
                        img_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else ""
                        if img_url.startswith('/'): img_url = "https://twitchdrops.app" + img_url

                        temp_rewards.append({
                            "name": name,
                            "image": img_url,
                            "minutes": minutes
                        })
                
                if temp_rewards:
                    active_campaigns.append({
                        "campaign_name": "1.13 Premium Drops",
                        "rewards": temp_rewards
                    })
            else:
                # JSON-Verarbeitung (falls verfügbar)
                for camp in campaigns:
                    if camp.get('status') == 'ACTIVE' or camp.get('active'):
                        rewards = []
                        for r in camp.get('items', []):
                            rewards.append({
                                "name": r.get('name'),
                                "image": r.get('image'),
                                "minutes": r.get('requiredMinutes', 60)
                            })
                        active_campaigns.append({
                            "campaign_name": camp.get('name'),
                            "rewards": rewards
                        })

        # Zeitstempel für Deutschland (CEST)
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_campaigns) > 0,
            "campaigns": active_campaigns
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
            
        print(f"Erfolg! Aktiv: {output['active']} | {len(active_campaigns)} Kampagnen gefunden.")

    except Exception as e:
        print(f"Fehler: {e}")
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
