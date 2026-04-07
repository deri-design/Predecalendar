import json
import requests
import uuid
import time
from datetime import datetime, timedelta, timezone

def fetch_drops():
    print("--- Connecting to Twitch GraphQL (Targeted Game Mode) ---")
    
    url = "https://gql.twitch.tv/gql"
    
    # Generate unique session IDs
    device_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex

    headers = {
        "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
        "X-Device-Id": device_id,
        "Client-Session-Id": session_id,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://www.twitch.tv",
        "Referer": "https://www.twitch.tv/directory/category/predecessor"
    }
    
    # We ask specifically for Predecessor (ID: 515056)
    # This query mimics the sidebar/overlay request on Twitch
    query = """
    query {
        game(id: "515056") {
            dropCampaigns {
                name
                status
                startAt
                endAt
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
    }
    """
    
    payload = {"query": query}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"Twitch API Error: {response.status_code}")
            return

        data = response.json()
        game_data = data.get("data", {}).get("game")
        
        if not game_data:
            print("Twitch found the game, but returned no game object. Shielding active.")
            return

        campaigns = game_data.get("dropCampaigns", [])
        print(f"Campaigns found for Predecessor: {len(campaigns)}")
        
        active_predecessor_drops = []
        now = datetime.now(timezone.utc)

        for camp in campaigns:
            c_name = camp.get('name', 'Unknown')
            status = camp.get('status', '').upper()
            print(f"Checking: {c_name} | Status: {status}")
            
            # Check time window (Twitch status can be ACTIVE, UPCOMING, or EXPIRED)
            is_live = (status == "ACTIVE")
            
            # Manual time check fallback
            try:
                start = datetime.strptime(camp['startAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                end = datetime.strptime(camp['endAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if start <= now <= end:
                    is_live = True
            except: pass

            if is_live:
                print(f"-> Verified ACTIVE: {c_name}")
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
                    "campaign_name": c_name,
                    "rewards": rewards
                })

        # Final Timestamp in German Time (CEST)
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_predecessor_drops) > 0,
            "campaigns": active_predecessor_drops
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"File Updated. Active Drops Found: {output['active']}")

    except Exception as e:
        print(f"Connection Error: {e}")
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
