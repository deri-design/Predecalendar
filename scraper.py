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
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=50"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, dict):
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return obj[key]
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    return ""

def extract_all_text_and_links(m):
    text_segments = [m.get('content', '')]
    urls = re.findall(r'(https?://[^\s]+)', m.get('content', ''))
    def process_obj(obj):
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
    prompt = f"Today is {today}. Predecessor game announcements. Extract events. RULES: 1. Identify DATE (YYYY-MM-DD). 2. Identify TIME (HH:MM) - if '2:00 PM' use 14:00. If none, use 14:00. 3. 'index' must match header. Messages: {messages_text} OUTPUT FORMAT: [{{'index': 0, 'date': 'YYYY-MM-DD', 'time': 'HH:MM', 'title': 'Title', 'type': 'patch/news/twitch/hero'}}] "
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.0)
        return json.loads(re.search(r'\[.*\]', chat.choices[0].message.content, re.DOTALL).group(0))
    except: return []

def scrape():
    messages = get_discord_messages()
    if not messages: return

    # Load existing database to prevent clearing it
    try:
        with open('events.json', 'r') as f:
            db = json.load(f)
            event_map = {str(e['original_id']): e for e in db.get('events', [])}
    except:
        event_map = {}

    to_process, ai_input_list = [], []
    for i, m in enumerate(messages):
        full_text, all_urls = extract_all_text_and_links(m)
        to_process.append({
            "index": i, "id": m['id'], "raw": full_text,
            "clean": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
            "urls": all_urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]
        })
        ai_input_list.append(f"INDEX: [{i}]\nCONTENT: {full_text}")

    ai_results = ask_groq("\n---\n".join(ai_input_list))

    for ar in ai_results:
        intel = next((x for x in to_process if x['index'] == ar['index']), None)
        if not intel: continue
        
        event_date = ar.get('date') or intel['posted']
        event_time = ar.get('time', '14:00')
        iso_date = f"{event_date}T{event_time}:00+02:00" # CEST
        
        etype = ar.get('type', 'news')
        if "twitch" in intel['raw'].lower() or "twitch.tv" in str(intel['urls']): etype = "twitch"
        if "patch" in intel['raw'].lower() or "v1." in intel['raw'].lower(): etype = "patch"

        event_map[str(intel['id'])] = {
            "original_id": intel['id'],
            "date": event_date,
            "iso_date": iso_date,
            "title": str(ar.get('title', 'UPDATE')).upper()[:40],
            "type": etype,
            "desc": intel['clean'],
            "image": intel['img'],
            "url": next((u for u in intel['urls'] if "playp.red" in u or "predecessorgame" in u), "https://www.predecessorgame.com/en-US/news")
        }

    with open('events.json', 'w') as f:
        json.dump({"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(event_map.values())}, f, indent=4)

if __name__ == "__main__": scrape()
