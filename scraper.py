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
    """Deep recursion to find the image in Discord's nested forwarded snapshots."""
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj:
            return obj
    if isinstance(obj, dict):
        # Specific Discord keys for images
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return obj[key]
        # Recursively check all values
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    if isinstance(obj, list):
        for i in obj:
            res = find_deep_img(i)
            if res: return res
    return ""

def clean_discord_text(text):
    text = re.sub(r'<@&?\d+>', '', text)
    text = text.replace('🔔', '')
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
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    Identify ACTUAL release/event dates and short titles. 
    Rules: 1. Only return events with specific dates. 2. Format: JSON list only.
    Messages: {messages_text}
    """
    chat = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    raw = chat.choices[0].message.content
    return json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group(0))

def scrape():
    print("Starting Deep Recovery Scrape...")
    messages = get_discord_messages()
    if not messages: return

    intel_pool = {}
    ai_input_list = []
    for m in messages:
        text = extract_full_content(m)
        img = find_deep_img(m) # Stronger recursive search
        if text:
            intel_pool[m['id']] = {
                "text": clean_discord_text(text),
                "img": img, 
                "url": f"https://discord.com/channels/1055546338907017278/{CHANNEL_ID}/{m['id']}"
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        
        # We start with an empty list and use Message ID as the unique key
        # This prevents duplicates like V1.13 and V1.13: Throne of Thorns
        final_registry = {}

        for ae in ai_events:
            mid = ae.get('original_id')
            if mid in intel_pool:
                # Resolve Type
                full_text = intel_pool[mid]['text'].lower()
                etype = ae.get('type', 'news')
                if any(x in full_text for x in ["twitch", "stream"]): etype = "twitch"
                elif "patch" in full_text or "v1." in ae['title'].lower(): etype = "patch"
                
                iso = ae.get('iso_date', ae['date'] + "T18:00:00Z" if etype == "twitch" else ae['date'] + "T00:00:00Z")

                event_obj = {
                    "date": ae['date'], "iso_date": iso, "title": ae['title'].upper(), "type": etype,
                    "desc": intel_pool[mid]['text'], "url": intel_pool[mid]['url'], "image": intel_pool[mid]['img']
                }

                # DEDUPLICATION: If we already have an event for this message ID, 
                # keep the one with the longer (more detailed) title.
                if mid in final_registry:
                    if len(event_obj['title']) > len(final_registry[mid]['title']):
                        final_registry[mid] = event_obj
                else:
                    final_registry[mid] = event_obj

        # Convert back to list and sort
        merged_events = sorted(list(final_registry.values()), key=lambda x: x['date'])

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": merged_events}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success: {len(merged_events)} merged events saved.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
