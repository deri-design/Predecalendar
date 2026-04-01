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
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=25"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return []
    return res.json()

def find_deep_img(obj):
    """Recursively search for any image in standard msg, snapshots, or embeds."""
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
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: Predecessor Game Discord announcements.
    Identify every upcoming event, patch, or stream.
    
    RULES:
    1. EXTRACT UNIQUE TITLES: Do not use 'UPDATE'. Use names like 'V1.13 Patch' or 'Adele Reveal'.
    2. Identify ACTUAL release dates (YYYY-MM-DD). If it says 'April 7th', use 2026-04-07.
    3. Return ONLY a JSON list of objects.
    
    Messages: {messages_text}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.1
        )
        raw = chat.choices[0].message.content
        return json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group(0))
    except: return []

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
                "posted": m['timestamp'],
                "url": f"https://discord.com/channels/1055546338907017278/1487129767865225261/{m['id']}"
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        master_list = []
        for ae in ai_events:
            if not isinstance(ae, dict): continue # THE FIX: Skips strings that caused the error
            mid = ae.get('original_id')
            if mid in intel_pool:
                date = ae.get('date', intel_pool[mid]['posted'][:10])
                title = ae.get('title', 'NEW UPDATE').upper()
                etype = "patch" if "patch" in title.lower() else "news"
                if "twitch" in intel_pool[mid]['text'].lower() or "stream" in intel_pool[mid]['text'].lower(): etype = "twitch"
                
                eurl = "https://www.twitch.tv/predecessorgame" if etype == "twitch" else intel_pool[mid]['url']
                iso = date + ("T18:00:00Z" if etype == "twitch" else "T15:00:00Z")

                master_list.append({
                    "date": date, "iso_date": iso, "title": title, "type": etype,
                    "desc": intel_pool[mid]['text'], "image": intel_pool[mid]['img'], "url": eurl
                })

        # Final Deduplication: Merge items on the same day with similar titles
        unique_map = {}
        for e in sorted(master_list, key=lambda x: len(x['title']), reverse=True):
            fingerprint = f"{e['date']}_{re.sub(r'[^A-Z]', '', e['title'][:8])}"
            if fingerprint not in unique_map: unique_map[fingerprint] = e

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(unique_map.values())}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print("Success")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
