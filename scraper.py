import os
import requests
import json
import re
from groq import Groq
from datetime import datetime

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=25"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def find_deep_img(obj):
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
            if 'http' in obj: return obj
    if isinstance(obj, dict):
        if 'image' in obj and isinstance(obj['image'], dict):
            url = obj['image'].get('url')
            if url: return url
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    if isinstance(obj, list):
        for i in obj:
            res = find_deep_img(i)
            if res: return res
    return ""

def clean_discord_text(text):
    # Remove role/user pings
    text = re.sub(r'<@&?\d+>', '', text)
    # Remove notification bell
    text = text.replace('🔔', '')
    # Clean redundant whitespace
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def extract_full_content(m):
    text = m.get('content', '')
    if 'message_snapshots' in m:
        for snap in m['message_snapshots']:
            msg = snap.get('message', {})
            text += f"\n{msg.get('content', '')}"
            for emb in msg.get('embeds', []):
                text += f"\n{emb.get('title', '')}\n{emb.get('description', '')}"
    if 'embeds' in m:
        for emb in m['embeds']:
            text += f"\n{emb.get('title', '')}\n{emb.get('description', '')}"
    return text.strip()

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Identify release dates AND specific start times for events.
    
    CRITICAL TIME RULES:
    1. Look for times like "6PM UTC / 2PM ET".
    2. ALWAYS prioritize the UTC time. Ignore ET/PT/other zones.
    3. CONVERT TO 24-HOUR UTC: 
       - 6PM UTC = 18:00:00Z
       - 2PM UTC = 14:00:00Z
       - 9AM UTC = 09:00:00Z
    4. "iso_date" must be formatted as: YYYY-MM-DDTHH:MM:SSZ
    5. If NO time is mentioned in the text, default to midnight: T00:00:00Z.
    
    Rules:
    - Only return events with specific dates.
    - Categorize as "patch", "hero", "season", or "twitch".
    - Match "original_id" to the provided ID.
    
    Messages:
    {messages_text}

    OUTPUT FORMAT (Strict JSON list only):
    [ 
      {{"date": "YYYY-MM-DD", "iso_date": "YYYY-MM-DDTHH:MM:SSZ", "title": "Name", "original_id": "id", "type": "type"}} 
    ]
    """
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    raw = chat_completion.choices[0].message.content
    json_match = re.search(r'\[.*\]', raw, re.DOTALL)
    return json.loads(json_match.group(0)) if json_match else []

def scrape():
    print("--- Starting High-Precision Temporal Scrape ---")
    messages = get_discord_messages()
    if not messages: return
    
    intel_pool = {}
    ai_input_list = []
    for m in messages:
        text = extract_full_content(m)
        img = find_deep_img(m)
        if text:
            intel_pool[m['id']] = {
                "text": clean_discord_text(text),
                "img": img, 
                "url": f"https://discord.com/channels/1055546338907017278/{CHANNEL_ID}/{m['id']}"
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        final_events = []
        for ae in ai_events:
            mid = ae.get('original_id')
            if mid in intel_pool:
                # Set specific URL for twitch
                event_url = intel_pool[mid]['url']
                if ae['type'] == 'twitch':
                    event_url = "https://www.twitch.tv/predecessorgame"
                
                final_events.append({
                    "date": ae['date'], 
                    "iso_date": ae['iso_date'], 
                    "title": ae['title'], 
                    "type": ae['type'],
                    "desc": intel_pool[mid]['text'], 
                    "url": event_url, 
                    "image": intel_pool[mid]['img']
                })
        
        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": final_events}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print("Success: Timezone-corrected data saved.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
