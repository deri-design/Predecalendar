import json
import requests
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

def fetch_drops():
    print("--- Beziehe Daten von TwitchDrops.app (Deep Search Mode) ---")
    
    url = "https://twitchdrops.app/game/predecessor"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    active_campaigns = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Fehler beim Laden: {response.status_code}")
            return

        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. VERSUCH: JSON-Datenblock extrahieren
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data:
            print("JSON-Datenblock gefunden. Starte Tiefensuche...")
            data = json.loads(next_data.string)
            
            # Funktion zur Suche nach Kampagnen-Listen im JSON
            def find_campaigns_recursive(obj):
                if isinstance(obj, dict):
                    # Suche nach typischen Keys, die TwitchDrops.app nutzt
                    for key in ['drop_campaigns', 'campaigns', 'initialDrops', 'activeDrops']:
                        if key in obj and isinstance(obj[key], list) and len(obj[key]) > 0:
                            return obj[key]
                    for v in obj.values():
                        res = find_campaigns_recursive(v)
                        if res: return res
                elif isinstance(obj, list):
                    for i in obj:
                        res = find_campaigns_recursive(i)
                        if res: return res
                return None

            raw_campaigns = find_campaigns_recursive(data)
            
            if raw_campaigns:
                for camp in raw_campaigns:
                    # Wir prüfen, ob die Kampagne aktiv ist (oder bald startet)
                    status = str(camp.get('status', '')).upper()
                    if status in ['ACTIVE', 'UPCOMING', '1', 'TRUE']:
                        rewards = []
                        # Items extrahieren
                        items = camp.get('items', []) or camp.get('drops', [])
                        for item in items:
                            rewards.append({
                                "name": item.get('name', 'Belohnung'),
                                "image": item.get('image') or item.get('image_url', ''),
                                "minutes": item.get('requiredMinutes') or item.get('minutes', 60)
                            })
                        
                        if rewards:
                            active_campaigns.append({
                                "campaign_name": camp.get('name') or camp.get('title', 'Predecessor Drops'),
                                "rewards": rewards
                            })

        # 2. VERSUCH: Direkte HTML-Suche (Fallback)
        if not active_campaigns:
            print("JSON-Suche erfolglos. Versuche HTML-Parsing...")
            # Suche nach Containern, die "Watch" und Zeitangaben enthalten (wie im Screenshot)
            # Wir suchen nach den Texten "Watch Xh" oder "Watch Xm"
            time_elements = soup.find_all(string=re.compile(r'Watch \d+', re.I))
            
            if time_elements:
                temp_rewards = []
                for te in time_elements:
                    parent = te.parent
                    # Suche Bild und Name im Umfeld dieses Textes
                    container = parent.find_parent(class_=re.compile(r'card|item|reward', re.I)) or parent.parent
                    img = container.find('img')
                    name = container.find(['h3', 'h4', 'p', 'span'], class_=re.compile(r'name|title', re.I))
                    
                    if img and name:
                        time_text = te.strip()
                        mins = 60
                        digits = re.findall(r'\d+', time_text)
                        if digits:
                            val = int(digits[0])
                            mins = val * 60 if 'h' in time_text.lower() else val
                        
                        temp_rewards.append({
                            "name": name.get_text().strip(),
                            "image": img.get('src') or img.get('data-src', ''),
                            "minutes": mins
                        })
                
                if temp_rewards:
                    active_campaigns.append({
                        "campaign_name": "Aktuelle Kampagne",
                        "rewards": temp_rewards
                    })

        # 3. ABSICHERUNG: Falls Predecessor im Text vorkommt, aber nichts strukturiert gefunden wurde
        if not active_campaigns and ("Predecessor" in html and "Drop" in html):
            print("Manuelle Erkennung: Drops scheinen aktiv zu sein, Details aber versteckt.")
            active_campaigns.append({
                "campaign_name": "Predecessor Twitch Drops",
                "rewards": [{"name": "Loot Cores / Skins", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 60}]
            })

        # Zeitstempel CEST (Deutschland)
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_campaigns) > 0,
            "campaigns": active_campaigns
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
        
        print(f"Ergebnis: {len(active_campaigns)} Kampagnen gefunden. Aktiv: {output['active']}")

    except Exception as e:
        print(f"Fehler: {e}")
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
