import os
import requests
import json
import re
from google import genai
from datetime import datetime

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=15"
    response = requests.get(url, headers=headers)
    return response.json()

def ask_ai_for_roadmap(messages_text):
    # Initialize the NEW modern client
    client = genai.Client(api_key=GEMINI_KEY)
    
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today is {today}. I am providing Discord announcements for the game "Predecessor".
    Extract the ACTUAL start dates for upcoming events, patches, or community news.
    
    Messages:
    ---
    {messages_text}
    ---
    
    Rules:
    1. Identify the event/patch start date.
    2. Format the output as a strict JSON list of objects.
    3. Categorize as "patch" or "news".
    
    Output Format:
    [
      {{"date": "YYYY-MM-DD", "title": "Event Name", "type": "patch/news", "url": "link", "image": "img_url"}}
    ]
    """
    
    # Use the new generate_content syntax
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt
    )
    
    # Robust JSON extraction
    raw_text = response.text
    json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    return json.loads(raw_text.strip())

def scrape():
    print("--- AI Roadmap: New SDK Sync ---")
    
    try:
        messages = get_discord_messages()
        combined_text = ""
        for m in messages:
            combined_text += f"TIME: {m['timestamp']} | MSG: {m['content']}\n---\n"

        print("Consulting Gemini 1.5-Flash via New SDK...")
        events = ask_ai_for_roadmap(combined_text)
        
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events
        }

        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"SUCCESS: {len(events)} events processed.")

    except Exception as e:
        print(f"ERROR: {e}")
        # Ensure file exists to avoid workflow failure
        if not os.path.exists('events.json'):
            with open('events.json', 'w') as f:
                json.dump({"events": []}, f)

if __name__ == "__main__":
    scrape()
