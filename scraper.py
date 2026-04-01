import os
import requests
import json
import re
from groq import Groq
from datetime import datetime

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    print(f"Connecting to Discord channel {CHANNEL_ID}...")
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=25"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"DISCORD ERROR: {res.status_code} - {res.text}")
        return []
    messages = res.json()
    print(f"Found {len(messages)} messages.")
    return messages

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj:
            return obj
    if isinstance(obj, dict):
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return obj[key]
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
    return re.sub(r'\n\s*\n', '\n', text).strip()

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
    print("Consulting Groq AI...")
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today is {today}. Context: Predecessor Game Discord.
    Identify ACTUAL release/event dates and short titles. 
    
    RULES:
    1. Output a JSON list only.
    2. "date": YYYY-MM-DD.
    3. "original_id": You MUST include the exact ID string provided for each message.
    
    Messages:
    {messages_text}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.1
        )
        raw = chat.choices[0].message.content
        print(f"AI Response received ({len(raw)} chars)")
        return json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group(0))
    except Exception as e:
        print(f"AI ERROR: {e}")
        return []

def scrape():
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
                "url": f"https://discord.com/channels/1055546338907017278/1487129767865225261/{m['id']}"
            }
            # Give the AI the ID very clearly
            ai_input_list.append(f"MESSAGE_ID: {m['id']} \n CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        master_list = []

        for ae in ai_events:
            mid = ae.get('original_id') or ae.get('MESSAGE_ID')
            if mid and mid in intel_pool:
                full_text = intel_pool[mid]['text'].lower()
                etype = ae.get('type', 'news')
                if any(x in full_text for x in ["twitch", "stream"]): etype = "twitch"
                
                eurl = "https://www.twitch.tv/predecessorgame" if etype == "twitch" else intel_pool[mid]['url']
                iso = ae['date'] + ("T18:00:00Z" if etype == "twitch" else "T00:00:00Z")

                master_list.append({
                    "date": ae['date'],
                    "iso_date": iso,
                    "title": ae['title'].upper(),
                    "type": etype,
                    "desc": intel_pool[mid]['text'],
                    "image": intel_pool[mid]['img'],
                    "url": eurl,
                    "original_id": mid
                })

        # Deduplication logic
        unique_map = {}
        for e in sorted(master_list, key=lambda x: len(x['title']), reverse=True):
            fingerprint = f"{e['date']}_{e['original_id']}"
            if fingerprint not in unique_map:
                unique_map[fingerprint] = e

        final_events = list(unique_map.values())
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": final_events
        }
        
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"SUCCESS: Saved {len(final_events)} events.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
