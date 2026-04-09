import json
import requests
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

def fetch_drops():
    print("--- Beziehe detaillierte Belohnungen von TwitchDrops.app ---")
    
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
        
        # 1. VERSUCH: Auslesen der Daten aus dem Next.js JSON (am genauesten)
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        if next_data_script:
            print("Extrahiere Daten aus JSON-Block...")
            data = json.loads(next_data_script.string)
            
            # Wir suchen tief im JSON-Baum nach der Kampagnen-Liste
            # Meist unter props -> pageProps -> game -> drop_campaigns
            page_props = data.get('props', {}).get('pageProps', {})
            game_obj = page_props.get('game', {})
            
            # Wir nehmen alle Kampagnen, die aktiv oder geplant sind
            raw_campaigns = game_obj.get('drop_campaigns', []) or page_props.get('campaigns', [])
            
            if not raw_campaigns:
                # Falls der Pfad anders ist, suchen wir rekursiv
                def find_list_with_items(obj):
                    if isinstance(obj, dict):
                        if 'items' in obj and isinstance(obj['items'], list) and len(obj['items']) > 0:
                            if 'name' in obj: return [obj] # Es ist eine Kampagne
                        for v in obj.values():
                            res = find_list_with_items(v)
                            if res: return res
                    elif isinstance(obj, list):
                        for i in obj:
                            res = find_list_with_items(i)
                            if res: return res
                    return None
                raw_campaigns = find_list_with_items(data) or []

            for camp in raw_campaigns:
                rewards = []
                # Wir holen jedes einzelne Item (Loot Cores, Skins etc.)
                items = camp.get('items', [])
                for item in items:
                    # Bild-URL korrigieren (oft fehlen Domain-Namen im JSON)
                    img = item.get('image', '')
                    if img and img.startswith('/'): img = "https://twitchdrops.app" + img
                    
                    rewards.append({
                        "name": item.get('name', 'Belohnung'),
                        "image": img,
                        "minutes": item.get('required_minutes') or item.get('minutes', 60)
                    })
                
                if rewards:
                    active_campaigns.append({
                        "campaign_name": camp.get('name', '1.13 Premium Drops'),
                        "rewards": rewards
                    })

        # 2. VERSUCH: HTML-Fallback (Falls JSON nicht funktioniert)
        if not active_campaigns:
            print("JSON fehlgeschlagen, nutze HTML-Parsing für Belohnungen...")
            # Wir suchen die Karten auf der Seite (wie im Screenshot Image 131)
            # Jedes Reward-Item ist meist in einem Container mit Text wie "Watch 1h"
            items_found = soup.find_all(string=re.compile(r'Watch \d+', re.I))
            
            temp_rewards = []
            for item_text in items_found:
                parent = item_text.parent.parent # Zum Container hochgehen
                img_tag = parent.find('img')
                name_tag = parent.find(['h3', 'h4', 'p', 'span'], string=True) # Textinhalt
                
                if img_tag:
                    name = name_tag.get_text().strip() if name_tag else "Drop Item"
                    # Wenn kein Name gefunden, nimm den Alt-Tag des Bildes
                    if name == "Drop Item" and img_tag.has_attr('alt'): name = img_tag['alt']
                    
                    time_str = item_text.strip()
                    mins = 60
                    # Umrechnung: 1h -> 60, 2h -> 120 etc.
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
                    "campaign_name": "Premium Drops",
                    "rewards": temp_rewards
                })

    except Exception as e:
        print(f"Fehler beim Scrapen: {e}")

    # CEST Zeitstempel
    german_time = datetime.now(timezone.utc) + timedelta(hours=2)
    output = {
        "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
        "active": len(active_campaigns) > 0,
        "campaigns": active_campaigns
    }
    
    with open('drops.json', 'w') as f:
        json.dump(output, f, indent=4)
    
    print(f"Abgeschlossen. Aktiv: {output['active']} | Belohnungen gefunden: {len(active_campaigns[0]['rewards']) if active_campaigns else 0}")

if __name__ == "__main__":
    fetch_drops()
