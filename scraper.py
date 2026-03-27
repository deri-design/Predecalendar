import os
import requests
import json
import re
from datetime import datetime, timedelta

# Config
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_ID = "1487129767865225261"

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=15"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def ask_gemini(messages_text):
    # Use the stable V1 endpoint directly
    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"Today is {today}. Extract game events for 'Predecessor' from these Discord messages into a JSON list with 'date' (YYYY-MM-DD), 'title', 'type' (patch/news), 'url', and 'image'. Text: {messages_text}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    response = requests.post(api_url, json=payload)
    data = response.json()
    
    if "candidates" not in data:
        print(f"Gemini API Error: {data}")
        return []

    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    # Extract JSON list from response
    json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    return json.loads(json_match.group(0)) if json_match else []

def scrape():
    print("--- Direct API Sync Start ---")
    messages = get_discord_messages()
    if not messages:
        print("Could not read Discord messages.")
        return

    combined = ""
    for m in messages:
        combined += f"SENT: {m['timestamp']} | MSG: {m['content']}\n---\n"

    print(f"Sending {len(messages)} messages to Gemini V1...")
    try:
        events = ask_gemini(combined)
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events
        }
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"SUCCESS: {len(events)} events saved.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
