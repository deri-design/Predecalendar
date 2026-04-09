import json
import requests
import uuid
from datetime import datetime, timedelta, timezone

def fetch_drops():
    print("--- Connecting to Twitch via Android-App Identity ---")
    
    url = "https://gql.twitch.tv/gql"
    
    # Das ist die offizielle Client-ID der Twitch-Android-App (aus dem Rust-Projekt inspiriert)
    # Diese IDs werden fast nie blockiert, weil die App sie weltweit nutzt.
    headers = {
        "Client-Id": "kd1unb4b3q4t58fwlpcbzcbaxtm78v", 
        "X-Device-Id": uuid.uuid4().hex,
        "User-Agent": "dalvik/2.1.0 (linux; u; android 10; build/qq3a.200805.001) tv.twitch.android.app/14.4.1",
        "Content-Type": "application/json",
        "Accept": "*/*"
    }
    
    # Wir nutzen eine Abfrage, die auch die mobile App verwendet
    query = """
    query {
        dropCampaigns {
            name
            status
            startAt
            endAt
            game {
                id
                name
            }
            timeBasedDrops {
                name
                requiredMinutesWatched
                benefitEdges {
                    benefit {
                        name
                        imageAssetURL
                    }
                }
            }
        }
    }
    """
    
    payload = {"query": query}

    try:
        # Wir senden die Anfrage als "Android App"
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if res.status_code != 200:
            print(f"Twitch hat die App-Anfrage abgelehnt: {res.status_code}")
            return

        data = res.json()
        all_campaigns = data.get("data", {}).get("dropCampaigns", [])
        
        print(f"Erfolg! {len(all_campaigns)} Kampagnen über App-Schnittstelle gefunden.")

        active_predecessor_drops = []
        now = datetime.now(timezone.utc)

        for camp in all_campaigns:
            game = camp.get("game", {})
            # Suche nach Predecessor (ID: 515056)
            if game and (game.get("id") == "515056" or "Predecessor" in game.get("name", "")):
                
                # Zeitfenster prüfen
                status = camp.get('status', '').upper()
                is_active = (status == "ACTIVE")
                
                if not is_active:
                    try:
                        start = datetime.strptime(camp['startAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        end = datetime.strptime(camp['endAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        if start <= now <= end:
                            is_active = True
                    except: pass

                if is_active:
                    print(f"AKTIVE DROPS FÜR PREDECESSOR: {camp['name']}")
                    rewards = []
                    for drop in camp.get("timeBasedDrops", []):
                        for edge in drop.get("benefitEdges", []):
                            benefit = edge.get("benefit", {})
                            rewards.append({
                                "name": benefit.get("name") or drop.get("name"),
                                "image": benefit.get("imageAssetURL") or "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png",
                                "minutes": drop.get("requiredMinutesWatched")
                            })
                    
                    active_predecessor_drops.append({
                        "campaign_name": camp['name'],
                        "rewards": rewards
                    })

        # Zeitstempel für Deutschland (CEST)
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_predecessor_drops) > 0,
            "campaigns": active_predecessor_drops
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
            
        print(f"Datei drops.json wurde aktualisiert. Aktiv: {output['active']}")

    except Exception as e:
        print(f"Fehler im App-Modus: {e}")
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
