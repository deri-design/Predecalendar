import json
import requests
import uuid
from datetime import datetime, timedelta, timezone

def fetch_drops():
    print("--- Connecting to Twitch GraphQL (Advanced Logic) ---")
    
    url = "https://gql.twitch.tv/gql"
    
    # Advanced headers to bypass bot detection
    headers = {
        "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
        "X-Device-Id": uuid.uuid4().hex,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://www.twitch.tv",
        "Referer": "https://www.twitch.tv/drops/campaigns"
    }
    
    # This is the standard public query for all drop campaigns
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
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"Twitch API rejected request: {response.status_code}")
            print(f"Body: {response.text[:200]}")
            return

        data = response.json()
        all_campaigns = data.get("data", {}).get("dropCampaigns", [])
        
        if not all_campaigns:
            print("Twitch returned 0 campaigns. Bot detection likely active.")
            return

        print(f"Total Twitch Campaigns Scanned: {len(all_campaigns)}")
        
        active_predecessor_drops = []
        now = datetime.now(timezone.utc)

        for camp in all_campaigns:
            game = camp.get("game")
            if not game: continue
            
            # Match Predecessor by ID (515056) or Name
            if game.get("id") == "515056" or "Predecessor" in game.get("name", ""):
                
                # Check status and time window
                status = camp.get('status', '').upper()
                is_active = (status == "ACTIVE")
                
                # Fallback: check time manually if status is lagging
                if not is_active:
                    try:
                        start = datetime.strptime(camp['startAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        end = datetime.strptime(camp['endAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        if start <= now <= end:
                            is_active = True
                    except: pass

                if is_active:
                    print(f"Live Campaign Found: {camp['name']}")
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

        # Calculate CEST (German Time)
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_predecessor_drops) > 0,
            "campaigns": active_predecessor_drops
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Scrape Finished. Success: {output['active']}")

    except Exception as e:
        print(f"Scrape Failed: {e}")
        # Always output a valid file
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
