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
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=20"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"DISCORD ERROR {res.status_code}: {res.text}")
        return []
    return res.json()

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

def extract_all_text_and_links(m):
    text_segments = [m.get('content', '')]
    urls = re.findall(r'(https?://[^\s]+)', m.get('content', ''))
    def process_obj(obj):
        if 'message_snapshots' in obj:
            for snap in obj['message_snapshots']:
                snap_msg = snap.get('message', {})
                text_segments.append(snap_msg.get('content', ''))
                urls.extend(re.findall(r'(https?://[^\s]+)', snap_msg.get('content', '')))
                process_obj(snap_msg)
        if 'embeds' in obj:
            for emb in obj['embeds']:
                text_segments.append(emb.get('title', ''))
                text_segments.append(emb.get('description', ''))
                if emb.get('url'): urls.append(emb['url'])
    process_obj(m)
    return "\n".join(filter(None, text_segments)), [u.rstrip('.,!?"\')') for u in urls]

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Predecessor game announcements. 
    TASK: Extract events with exact times.
    RULES:
    1. Identify START DATE (YYYY-MM-DD).
    2. Identify START TIME (HH:MM) - e.g. "2:00 PM" is 14:00. If none found, use 14:00.
    3. Return ONLY valid JSON list.
    4. "index" MUST match header index.
    Messages:
    {messages_text}
    OUTPUT FORMAT:
    [
      {{"index": 0, "date": "YYYY-MM-DD", "time": "HH:MM", "title": "Title", "type": "patch/news/twitch/hero"}}
    ]
    """
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.0)
        raw = chat.choices[0].message.content
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except: return []

def scrape():
    messages = get_discord_messages()
    if not messages: return
    try:
        with open('events.json', 'r') as f:
            db = json.load(f)
            event_map = {str(e['original_id']): e for e in db.get('events', [])}
    except: event_map = {}

    to_process, ai_input = [], []
    for i, m in enumerate(messages):
        txt, urls = extract_all_text_and_links(m)
        to_process.append({"index": i, "id": m['id'], "raw": txt, "clean": re.sub(r'<@&?\d+>', '', txt).strip(), "urls": urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]})
        ai_input.append(f"INDEX: [{i}]\nCONTENT: {txt}")

    results = ask_groq("\n---\n".join(ai_input))
    for ar in results:
        intel = next((x for x in to_process if x['index'] == ar.get('index')), None)
        if not intel: continue
        
        date = ar.get('date') or intel['posted']
        time = ar.get('time', '14:00')
        iso = f"{date}T{time}:00+02:00" # FORCE CEST OFFSET

        etype = ar.get('type', 'news')
        if "twitch" in intel['raw'].lower(): etype = "twitch"
        if "v1." in intel['raw'].lower() or "patch" in intel['raw'].lower(): etype = "patch"

        event_map[str(intel['id'])] = {
            "original_id": intel['id'], "date": date, "iso_date": iso,
            "title": str(ar.get('title', 'UPDATE')).upper()[:40], "type": etype,
            "desc": intel['clean'], "image": intel['img'],
            "url": next((u for u in intel['urls'] if "playp.red" in u or "predecessor" in u), "https://www.predecessorgame.com/en-US/news")
        }

    with open('events.json', 'w') as f:
        json.dump({"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(event_map.values())}, f, indent=4)

if __name__ == "__main__": scrape()
