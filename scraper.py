import os
import requests
import json
import re
from google import genai
from datetime import datetime

# Configuration from GitHub Secrets
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=20"
    response = requests.get(url, headers=headers)
    return response.json()

def ask_ai_for_roadmap(messages_text):
    # Initialize the new Google GenAI client
    client = genai.Client(api_key=GEMINI_KEY)
    
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today's Date: {today}
    Extract game roadmap dates from these Discord announcements for the game "Predecessor".
    
    Messages:
    ---
    {messages_text}
    ---
    
    TASK:
    1. Identify the ACTUAL event/patch start dates.
    2. Format the output as a strict JSON list of objects.
    3. Categorize as "patch" or "news".
    
    OUTPUT FORMAT:
    [
      {{"date": "YYYY-MM-DD", "title": "Event Name", "type": "patch/news", "url": "link", "image": "img_link"}}
    ]
    """
    
    # Using the latest stable model
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt
    )
    
    # Clean the response text (remove markdown backticks if Gemini adds them)
    raw_text = response.text
    json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    return json.loads(raw_text.strip())

def scrape():
    print("Fetching Discord data...")
    messages = get_discord_messages()
    
    combined_text = ""
    for m in messages:
        combined_text += f"SENT: {m['timestamp']} | MSG: {m['content']}\n---\n"

    print("Gemini AI (1.5-Flash) is processing...")
    try:
        events = ask_ai_for_roadmap(combined_text)
        
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events
        }

        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success! {len(events)} events extracted.")
    except Exception as e:
        print(f"AI Processing Error: {e}")

if __name__ == "__main__":
    scrape()
