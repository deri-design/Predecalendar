import os
import requests
import json
import re
import time
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
    """Deepest possible recursion to find images in nested Discord forwarded objects."""
    if not obj: return ""
    # If it's a URL string, check if it's an image
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj:
            return obj
    if isinstance(obj, dict):
        # Target specific Discord image keys
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return obj[key]
        # Check specific containers
        if 'image' in obj and isinstance(obj['image'], dict):
            res = find_deep_img(obj['image'])
            if res: return res
        # Recursively check everything else
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
    Today is {today}. Context: "Predecessor" announcements.
    Identify ACTUAL release/event dates and short titles. 
    RULES:
    1. If a message mentions multiple distinct features for the SAME date, create ONE event for each.
    2. If a message mentions ONE date for ONE thing, create ONE event.
    3. JSON list only. date: YYYY-MM-DD. title: short. original_id: match to ID. type: patch/hero/season/twitch.
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
    print("Executing Deep Deduplication Scrape...")
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
        
        # Load Existing
        try:
            with open('events.json', 'r') as f:
                old_data = json.load(f)
                master_list = old_data.get('events', [])
        except: master_list = []

        # Process new AI events
        for ae in ai_events:
            mid = ae.get('original_id')
            if mid in intel_pool:
                # Type and URL logic
                full_text = intel_pool[mid]['text'].lower()
                etype = ae['type']
                eurl = intel_pool[mid]['url']
                if any(x in full_text for x in ["twitch", "stream"]):
                    etype, eurl = "twitch", "https://www.twitch.tv/predecessorgame"
                
                iso = ae.get('iso_date', ae['date'] + "T18:00:00Z" if etype == "twitch" else ae['date'] + "T00:00:00Z")

                new_obj = {
                    "date": ae['date'], "iso_date": iso, "title": ae['title'].upper(), "type": etype,
                    "desc": intel_pool[mid]['text'], "url": eurl, "image": intel_pool[mid]['img']
                }

                # Check for existing match
                exists = next((i for i, x in enumerate(master_list) if x['title'] == new_obj['title'] and x['date'] == new_obj['date']), -1)
                if exists > -1: master_list[exists] = new_obj
                else: master_list.append(new_obj)

        # --- CRITICAL DEDUPLICATION ---
        # 1. Filter out exact date/title duplicates
        master_list = { (e['date'], e['title']): e for e in master_list }.values()
        master_list = list(master_list)

        # 2. String-Match Purge (e.g. Remove "V1.13" if "V1.13: THRONE OF THORNS" exists)
        final_list = []
        master_list.sort(key=lambda x: len(x['title']), reverse=True) # Check longest titles first
        
        for e in master_list:
            is_redundant = False
            for other in final_list:
                if e['date'] == other['date']:
                    # If this title is just a shorter version of another on the same day
                    if e['title'] in other['title'] and e['title'] != other['title']:
                        is_redundant = True
                        break
            if not is_redundant:
                final_list.append(e)

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": final_list}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success: {len(final_list)} unique events saved.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
