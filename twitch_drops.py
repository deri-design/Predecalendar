import json
import requests
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

def fetch_drops():
    print("--- Beziehe NUR AKTIVE Belohnungen von TwitchDrops.app ---")
    
    url = "https://twitchdrops.app/game/predecessor"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    }

    active_campaigns = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Fehler: Seite konnte nicht geladen werden ({response.status_code})")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- SCHRITT 1: Finde die Grenze zu den alten Drops ---
        # Wir suchen die Überschrift "PAST DROPS"
        past_drops_heading = soup.find(string=re.compile(r'PAST DROPS', re.I))
        
        # --- SCHRITT 2: Versuche JSON-Extraktion mit Status-Check ---
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        if next_data_script:
            print("Analysiere JSON-Daten...")
            data = json.loads(next_data_script.string)
            page_props = data.get('props', {}).get('pageProps', {})
            game_obj = page_props.get('game', {})
            
            # Suche nach Kampagnen im JSON
            raw_campaigns = game_obj.get('drop_campaigns', []) or page_props.get('campaigns', [])
            
            for camp in raw_campaigns:
                # STRENGER CHECK: Nur Kampagnen mit Status 'ACTIVE' zulassen
                status = str(camp.get('status', '')).upper()
                if status == 'ACTIVE':
                    print(f"Aktive Kampagne im JSON gefunden: {camp.get('name')}")
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
                            "campaign_name": camp.get('name'),
                            "rewards": rewards
                        })

        # --- SCHRITT 3: HTML-Fallback (nur falls JSON-Check nichts fand) ---
        if not active_campaigns:
            print("JSON war leer/inaktiv. Nutze gefiltertes HTML-Parsing...")
            # Wir suchen alle "Watch"-Texte
            time_elements = soup.find_all(string=re.compile(r'Watch \d+', re.I))
            
            temp_rewards = []
            for te in time_elements:
                # PRÜFUNG: Liegt dieses Element unterhalb von "PAST DROPS"?
                # Wenn ja, ignorieren wir es komplett.
                if past_drops_heading and te.sourceline > past_drops_heading.parent.sourceline:
                    continue

                parent = te.parent.parent
                img_tag = parent.find('img')
                name_tag = parent.find(['h3', 'h4', 'p', 'span'], string=True)
                
                if img_tag:
                    name = name_tag.get_text().strip() if name_tag else img_tag.get('alt', 'Drop Item')
                    
                    time_str = te.strip()
                    mins = 60
                    nums = re.findall(r'\d+', time_str)
                    if nums:
                        val = int(nums[0])
                        mins = val * 60 if 'h' in time_str.lower() else val

                    img_url = img_tag['src'] if img_tag.has_attr('src') else ""
                    if img_url.startswith('/'): img_url = "https://twitchdrops.app" + img_url

                    temp_rewards.append({
                        "name": name,
                        "image": img_url,
                        "minutes": mins
                    })
            
            if temp_rewards:
                active_campaigns.append({
                    "campaign_name": "Aktuelle Drops",
                    "rewards": temp_rewards
                })

        # Zeitstempel CEST
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_campaigns) > 0,
            "campaigns": active_campaigns
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
        
        print(f"Bereinigung abgeschlossen. Aktiv: {output['active']} | Belohnungen: {len(active_campaigns[0]['rewards']) if active_campaigns else 0}")

    except Exception as e:
        print(f"Fehler: {e}")
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
