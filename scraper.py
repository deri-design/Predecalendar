import os
import requests
import json
import re
from groq import Groq
from datetime import datetime

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_ID = "1487129767865225261"

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=20"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today is {today}. Context: Game "Predecessor".
    Extract upcoming events from these Discord messages.
    
    RULES:
    1. Find the ACTUAL event start date (YYYY-MM-DD).
    2. Summarize a short title.
    3. Categorize as "patch" or "news".
    4. Extract any image URLs ending in .jpg, .png, or .webp.
    
    Messages:
    {messages_text}

    RETURN ONLY A VALID JSON LIST:
    [
      {{"date": "YYYY-MM-DD", "title": "Name", "type": "patch/news", "url": "link", "image": "img"}}
    ]
    """
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile", # Most powerful free model
        temperature=0.1 # Keep it focused
    )
    
    raw_text = chat_completion.choices[0].message.content
    json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    return json.loads(json_match.group(0)) if json_match else []

def scrape():
    print("Fetching Discord...")
    messages = get_discord_messages()
    if not messages: return

    combined = ""
    for m in messages:
        combined += f"SENT: {m['timestamp']} | MSG: {m['content']}\n---\n"

    print("Consulting Groq Llama-3...")
    try:
        events = ask_groq(combined)
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
