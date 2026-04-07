import json
import requests
from datetime import datetime, timedelta, timezone

def fetch_drops():
    print("--- Connecting to Twitch Global Drops API ---")
    
    url = "https://gql.twitch.tv/gql"
    headers = {
        "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
        "Content-Type": "application/json"
    }
    
    # We query ALL active campaigns directly. 
    # This is more reliable for public (non-logged in) requests.
    payload = [{
        "operationName": "ViewerDropsDashboard",
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "e1edcc7790435349e5898d2b0e77d943477e685f060c410427c328905357f89c"
            }
        },
        "variables": {
            "inventory": False
        }
    }]

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        data = res.json()
        
        active_campaigns = []
        # Twitch returns a list for this specific operation
        all_campaigns = data[0].get("data", {}).get("dropCampaigns", [])
        
        print(f"Total Twitch Campaigns Scanned: {len(all_campaigns)}")
        
        for camp in all_campaigns:
            # Filter for Predecessor (Game ID: 515056)
            game_info = camp.get("game", {})
            if game_info.get("id") == "515056" or game_info.get("name") == "Predecessor":
                
                print(f"Match Found: {camp.get('name')} | Status: {camp.get('status')}")
                
                # Only grab Active or Upcoming (Twitch sometimes lags the 'ACTIVE' status)
                if camp.get("status") in ["ACTIVE", "UPCOMING"]:
                    rewards = []
                    # Dig into time-based drops
                    for drop in camp.get("timeBasedDrops", []):
                        # Extract the benefit details
                        for edge in drop.get("benefitEdges", []):
                            benefit = edge.get("benefit", {})
                            rewards.append({
                                "name": benefit.get("name") or drop.get("name"),
                                "image": benefit.get("imageAssetURL"),
                                "minutes": drop.get("requiredMinutesWatched")
                            })
                    
                    active_campaigns.append({
                        "campaign_name": camp.get("name"),
                        "start": camp.get("startAt"),
                        "end": camp.get("endAt"),
                        "rewards": rewards
                    })

        # Generate German Time (UTC+2) for the timestamp
        german_time = datetime.now(timezone.utc) + timedelta(hours=2)
        
        output = {
            "last_updated": german_time.strftime("%Y-%m-%d %H:%M:%S") + " (CEST)",
            "active": len(active_campaigns) > 0,
            "campaigns": active_campaigns
        }
        
        with open('drops.json', 'w') as f:
            json.dump(output, f, indent=4)
            
        print(f"Final Result - Active: {output['active']} | Count: {len(active_campaigns)}")
        
    except Exception as e:
        print(f"Scrape Error: {e}")
        with open('drops.json', 'w') as f:
            json.dump({"active": False, "campaigns": [], "last_updated": "Error"}, f, indent=4)

if __name__ == "__main__":
    fetch_drops()
