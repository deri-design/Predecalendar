import os
import requests
import json
import re
from datetime import datetime

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=15"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def ask_gemini(messages_text, model_name):
    """Hits the Gemini API with a specific model name"""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_KEY}"
    
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: Game "Predecessor".
    Extract upcoming event dates, patches, or hero releases from these Discord announcements.
    Rules:
    1. Identify the ACTUAL date the event starts.
    2. Format as a JSON list only.
    3. Include: "date" (YYYY-MM-DD), "title", "type" (patch/news), "url", "image".
    4. If an image link exists in the message, include it.
    
    Messages:
    {messages_text}

    OUTPUT ONLY JSON:
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(api_url, json=payload, timeout=20)
    
    if response.status_code == 200:
        try:
            raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            return json.loads(json_match.group(0))
        except:
            return None
    else:
        print(f"Model {model_name} failed with status {response.status_code}")
        return None

def scrape():
    print("--- AI Agent: Robust Sync Start ---")
    messages = get_discord_messages()
    if not messages:
        print("Could not retrieve Discord messages.")
        return

    combined = ""
    for m in messages:
        combined += f"SENT: {m['timestamp']} | MSG: {m['content']}\n---\n"

    # List of models to try in order of likelihood to have quota
    models_to_try = ["gemini-2.0-flash-lite", "gemini-1.5-flash-8b", "gemini-2.0-flash"]
    events = None

    for model in models_to_try:
        print(f"Trying model: {model}...")
        events = ask_gemini(combined, model)
        if events is not None:
            print(f"SUCCESS: {model} delivered the data.")
            break
    
    if events is not None:
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events
        }
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Final: {len(events)} events saved.")
    else:
        print("CRITICAL: All AI models failed or were rate-limited.")

if __name__ == "__main__":
    scrape()
