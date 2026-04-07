import json
import requests
from datetime import datetime, timezone

def fetch_drops():
    print("--- Connecting to Twitch Internal GraphQL ---")
    
    url = "https://gql.twitch.tv/gql"
    # kimne78kx3ncx6brgo4mv6wki5h1ko is Twitch's public web client ID
    headers = {
        "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
        "Content-Type": "application/json"
    }
    
    # Using Predecessor's Twitch ID: 515056
    payload = {
        "query": """
        query {
          game(id: "515056") {
            id
            name
            dropCampaigns {
              id
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
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        data = res.json()
        
        active_drops = []
        game_data = data.get("data", {}).get("game")
        
        if not game_data:
            print("Twitch returned no data for Predecessor.")
        elif not game_data.get("dropCampaigns"):
            print("No campaigns found for Predecessor.")
        else:
            now = datetime.now(timezone.utc)
            
            for camp in game_data["dropCampaigns"]:
                c_name = camp.get('name', 'Unknown')
                c_status = camp.get('status', '').upper()
                c_start = camp.get('startAt', '')
                c_end = camp.get('endAt', '')
                
                print(f"Checking Campaign: {c_name} | Status: {c_status}")
                
                is_active = False
                if c_status == "ACTIVE":
                    is_active = True
                elif c_start and c_end:
                    try:
                        start_dt = datetime.strptime(c_start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        end_dt = datetime.strptime(c_end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        if start_dt <= now <= end_dt:
                            print("-> Campaign within time window. Mark as active.")
                            is_active = True
                    except: pass

                if is_active:
                    rewards = []
                    for drop in camp.get("timeBasedDrops", []):
                        for edge in drop.get("benefitEdges", []):
                            benefit = edge.get("benefit", {})
                            rewards.append({
                                "name": benefit.get("name") or drop.get("name", "Reward"),
                                "image": benefit.get("imageAssetURL") or "https://static-cdn.jtvnw.net/drops/assets/predecessor_default.png",
                                "minutes": drop.get("requiredMinutesWatched")
                            })
                    
                    active_drops.append({
                        "campaign_name": c_name,
                        "start": c_start,
                        "end": c_end,
                        "rewards": rewards
                    })
        
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "active": len(active_drops) > 0,
            "campaigns": active_drops
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
            
        print(f"Scrape Complete. Active Drops Found: {output['active']}")
        
    except Exception as e:
        print(f"Error: {e}")
        # Fallback to empty file so the site doesn't break
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
