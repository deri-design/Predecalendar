import json
import requests
import re
from datetime import datetime, timedelta, timezone

def fetch_drops():
    print("--- Suche Predecessor Drops (Multi-Source-Mode) ---")
    
    # --- KONFIGURATION DER AKTUELLEN KAMPAGNE (SICHERHEITSNETZ) ---
    # Falls die automatische Suche scheitert, werden diese Daten genommen.
    current_campaign = {
        "campaign_name": "1.13 Premium Drops",
        "start": "2026-04-07T18:00:00Z",
        "end": "2026-05-04T18:00:00Z",
        "rewards": [
            {"name": "Ion Loot Core", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 60},
            {"name": "Purple Adele Profile Icon", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 120},
            {"name": "Purple Adele Banner", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 240},
            {"name": "Quantum Loot Core", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 360},
            {"name": "Purple Adele Skin Variant", "image": "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png", "minutes": 480}
        ]
    }

    found_campaigns = []
    
    # VERSUCH 1: TwitchDrops.app API (Hidden JSON)
    try:
        url = "https://twitchdrops.app/game/predecessor"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Suche nach JSON im Quelltext
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', response.text)
            if match:
                data = json.loads(match.group(1))
                # Suche rekursiv nach 'items' oder 'drops'
                def find_it(obj):
                    if isinstance(obj, dict):
                        if 'items' in obj and isinstance(obj['items'], list) and len(obj['items']) > 3:
                            return obj
                        for v in obj.values():
                            res = find_it(v)
                            if res: return res
                    elif isinstance(obj, list):
                        for i in obj:
                            res = find_it(i)
                            if res: return res
                    return None
                
                res = find_it(data)
                if res:
                    print("Erfolg: Kampagne in JSON gefunden.")
                    rewards = []
                    for item in res.get('items', []):
                        img = item.get('image', '')
                        if img.startswith('/'): img = "https://twitchdrops.app" + img
                        rewards.append({
                            "name": item.get('name'),
                            "image": img or "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png",
                            "minutes": int(item.get('required_minutes') or 60)
                        })
                    found_campaigns.append({
                        "campaign_name": res.get('name', 'Predecessor Drops'),
                        "start": res.get('starts_at', current_campaign['start']),
                        "end": res.get('ends_at', current_campaign['end']),
                        "rewards": rewards
                    })
    except:
        print("Quelle 1 (TwitchDrops.app) fehlgeschlagen.")

    # VERSUCH 2: Sicherheitsnetz greift ein, wenn keine Daten gefunden wurden
    if not found_campaigns:
        print("Nutze internes Sicherheitsnetz für aktuelle Kampagne...")
        now = datetime.now(timezone.utc)
        start_dt = datetime.strptime(current_campaign['start'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(current_campaign['end'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        
        if start_dt <= now <= end_dt:
            found_campaigns.append(current_campaign)

    # CEST Zeitstempel (+2h)
    german_time = datetime.now(timezone.utc) + timedelta(hours=2)
    output = {
        "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
        "active": len(found_campaigns) > 0,
        "campaigns": found_campaigns
    }
    
    with open('drops.json', 'w') as f:
        json.dump(output, f, indent=4)
    print(f"Update abgeschlossen. Aktiv: {output['active']}")

if __name__ == "__main__":
    fetch_drops()
